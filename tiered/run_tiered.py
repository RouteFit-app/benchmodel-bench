#!/usr/bin/env python3
"""run_tiered.py -- DoorDash-style staged reviewer, run against one bug suite.

  Scout (cheap)  -> flags anything that could be off, over the whole diff (1 call)
  Verify (strong)-> confirms/drops each flag against the REAL code (1 call/flag)
  Adversary (diff arch) -> tries to prove each survivor is a false positive (1 call/confirmed)

Expensive tokens only fire on what the scout flagged, so cost scales with the number
of candidates, not the diff size. Provider calls run at temperature 0 so the pipeline
is deterministic. Reuses your real infra: lifecycle key handling (key_for/load_env),
model_pricing.json for a char-based cost estimate (your reviewer calls don't return
token counts, so we estimate exactly like estimate_cost.py does), and a git-diff
loader like runner.py's.

Usage (from benchmark/tiered/):
  python run_tiered.py \
      --bug-index ../suites/security-owasp/bug_index.json \
      --repo /path/to/benchmodel-fastapi-template \
      --out results/owasp.json

Keys (BYOK): ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY (or GOOGLE_API_KEY)
/ DEEPSEEK_API_KEY, in the environment or backend/.env.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH / "lifecycle"))
from lifecycle_runner import load_env, key_for  # noqa: E402

from code_slice import code_slice  # noqa: E402

PRICING = json.loads((BENCH / "model_pricing.json").read_text(encoding="utf-8"))

STAGES = {
    "scout": "deepseek-chat",       # cheap, high recall
    "verify": "claude-opus-4-8",    # strong, precise
    "adversarial": "gpt-4o",        # different architecture, skeptical
}

SCOUT_SYS = (
    "You are a fast triage reviewer. Read the diff and list EVERY change that could be "
    "a bug, security issue, or regression. Cast a wide net and err toward flagging; a "
    "later stage will confirm or drop each one. Do NOT try to confirm anything here.\n"
    "Return STRICT JSON only:\n"
    '{ "candidates": [ { "file": "<path>", "line_range": "<e.g. 20-24>", '
    '"issue": "<one sentence>", "severity_guess": "high|medium|low", '
    '"reason": "<why it looks off>" } ] }'
)
VERIFY_SYS = (
    "You are a senior reviewer verifying ONE flagged issue. You are given the exact code "
    "and a single candidate finding. Decide whether it is a REAL problem in THIS code. "
    "Quote the specific line(s) that prove your verdict. If the code is actually correct, "
    "or the concern does not apply here, mark it dismissed. Do NOT raise any new issue; "
    "judge only the one given.\n"
    "Return STRICT JSON only:\n"
    '{ "verdict": "confirmed|dismissed", "confidence": 0.0, "severity": "high|medium|low", '
    '"evidence": "<quoted code + reasoning>" }'
)
ADV_SYS = (
    "You are a skeptical reviewer whose job is to PROVE the given finding is a false "
    "positive. Make the strongest case that the code is actually fine: a guard exists "
    "elsewhere, the input is validated upstream, it is intended behavior, the caller "
    "handles it, etc. Quote code to support your case. If, after your best effort, you "
    "cannot disprove it, concede that it stands.\n"
    "Return STRICT JSON only:\n"
    '{ "survives": true, "counterargument": "<best case it is fine>", '
    '"residual_risk": "<what still worries you, or none>" }'
)
# Single-pass baseline: one strong-model review over the whole diff, to compare
# cost and finding count against the tiered pipeline.
SINGLE_SYS = (
    "You are a senior code reviewer. Review the diff and report the real bugs, security issues, and "
    "regressions in the changed code (skip pure style nits). Return STRICT JSON only:\n"
    '{ "findings": [ { "file": "<path>", "line_range": "<range>", "severity": "high|medium|low", '
    '"issue": "<what is wrong>" } ] }'
)

# Same artifact exclusions runner.py uses, so a stray review dump can't leak in.
DIFF_EXCLUDE = ["**/*_diff_review.txt", "**/buggy_diff*.txt", "**/*.orig", "**/*.rej"]


def git_diff(repo: Path, base: str, buggy: str) -> str:
    cmd = ["git", "-C", str(repo), "diff", f"{base}...{buggy}", "--", "."]
    cmd += [f":(exclude,glob){p}" for p in DIFF_EXCLUDE]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"git diff failed in {repo} ({base}...{buggy}):\n{r.stderr}")
    return r.stdout


def _temp_deprecated(e: Exception) -> bool:
    return "temperature" in str(e).lower()


def _call(model: str, key: str, system: str, user: str, temp: float = 0.0) -> str:
    """Provider call at a fixed temperature (deterministic). Some newer models
    (e.g. claude-opus-4-8) now REJECT a temperature param; if a provider says
    temperature is deprecated/unsupported, we retry once without it."""
    m = model.lower()
    if "claude" in m:
        import anthropic
        c = anthropic.Anthropic(api_key=key, timeout=120.0)

        def go(**extra):
            r = c.messages.create(model=model, max_tokens=1500, system=system,
                                  messages=[{"role": "user", "content": user}], **extra)
            return "".join(getattr(b, "text", "") for b in (r.content or []) if getattr(b, "type", None) == "text")
        try:
            return go(temperature=temp)
        except Exception as e:
            if _temp_deprecated(e):
                return go()
            raise
    if "gemini" in m:
        from google import genai
        from google.genai import types
        c = genai.Client(api_key=key)

        def go(cfg):
            return c.models.generate_content(model=model, contents=user, config=cfg).text or ""
        try:
            return go(types.GenerateContentConfig(system_instruction=system, temperature=temp))
        except Exception as e:
            if _temp_deprecated(e):
                return go(types.GenerateContentConfig(system_instruction=system))
            raise
    from openai import OpenAI
    c = OpenAI(api_key=key, base_url=("https://api.deepseek.com" if "deepseek" in m else None), timeout=120.0)

    def go(**extra):
        r = c.chat.completions.create(model=model, messages=[
            {"role": "system", "content": system}, {"role": "user", "content": user}], **extra)
        return r.choices[0].message.content or ""
    try:
        return go(temperature=temp)
    except Exception as e:
        if _temp_deprecated(e):
            return go()
        raise


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def parse_json(text: str):
    if not text:
        return None
    s = _FENCE.sub("", text.strip())
    cands = [s]
    if "{" in s and "}" in s:
        cands.append(s[s.find("{"): s.rfind("}") + 1])
    for c in cands:
        try:
            return json.loads(c)
        except Exception:
            continue
    return None


def cost(model: str, in_chars: int, out_chars: int) -> float:
    est = PRICING["_estimation"]
    cpt = est["chars_per_token"]
    scaffold = est.get("scaffold_tokens", 0)
    p = PRICING["models"].get(model, {})
    in_tok = in_chars / cpt + scaffold
    out_tok = out_chars / cpt
    return in_tok / 1e6 * p.get("input_per_mtok", 0) + out_tok / 1e6 * p.get("output_per_mtok", 0)


def key_or_die(model: str) -> str:
    k, name = key_for(model)
    if not k:
        sys.exit(f"Missing API key for {model}: set {name} (env or backend/.env).")
    return k


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bug-index", type=Path, default=None,
                    help="Suite mode: bug_index(.vN).json (reads base/buggy branches; enables scoring).")
    ap.add_argument("--repo", type=Path, required=True, help="Local checkout of the repo")
    ap.add_argument("--base", default=None, help="Raw mode: base git ref (with --head; any big repo, no answer key)")
    ap.add_argument("--head", default=None, help="Raw mode: head/changed git ref (the side being reviewed)")
    ap.add_argument("--out", type=Path, default=HERE / "results" / "tiered.json")
    ap.add_argument("--models", nargs=3, metavar=("SCOUT", "VERIFY", "ADV"), default=None,
                    help="override the scout / verify / adversarial models")
    ap.add_argument("--baseline", action="store_true",
                    help="Also run ONE pass with the verify model over the whole diff, for a cost/finding comparison.")
    ap.add_argument("--max-candidates", type=int, default=None,
                    help="Cap how many scout candidates go through the (expensive) verify/adversarial stages. "
                         "Use on big raw diffs so the bill can't run away.")
    a = ap.parse_args()
    load_env()
    if a.models:
        STAGES["scout"], STAGES["verify"], STAGES["adversarial"] = a.models

    if a.bug_index:
        bi = json.loads(a.bug_index.read_text(encoding="utf-8"))
        base, head, label = bi["base_branch"], bi["buggy_branch"], bi["benchmark_name"]
    elif a.base and a.head:
        bi = None
        base, head, label = a.base, a.head, f"{a.repo.name} {a.base}..{a.head}"
    else:
        sys.exit("Provide either --bug-index (suite mode) or --base and --head (raw mode).")

    diff = git_diff(a.repo, base, head)
    if not diff.strip():
        sys.exit(f"Empty diff for {base}...{head}. Check the refs exist in the repo.")
    print(f"{label} | diff: {len(diff)} chars | "
          f"scout={STAGES['scout']} verify={STAGES['verify']} adversarial={STAGES['adversarial']}\n")

    meta = {"models": dict(STAGES), "stages": {}}

    def track(stage, model, in_chars, out_chars):
        s = meta["stages"].setdefault(stage, {"calls": 0, "in_chars": 0, "out_chars": 0, "cost": 0.0})
        s["calls"] += 1
        s["in_chars"] += in_chars
        s["out_chars"] += out_chars
        s["cost"] += cost(model, in_chars, out_chars)

    # STAGE 1 -- scout
    m = STAGES["scout"]
    key = key_or_die(m)
    resp = _call(m, key, SCOUT_SYS, f"Review this diff:\n\n{diff}")
    track("scout", m, len(SCOUT_SYS) + len(diff), len(resp))
    candidates = (parse_json(resp) or {}).get("candidates", []) or []
    print(f"Scout flagged {len(candidates)} candidate(s).")
    if a.max_candidates and len(candidates) > a.max_candidates:
        print(f"  (capping to first {a.max_candidates} for the verify/adversarial stages)")
        candidates = candidates[:a.max_candidates]

    # STAGE 2 -- verify
    m = STAGES["verify"]
    key = key_or_die(m)
    confirmed = []
    verify_trace = []
    for c in candidates:
        sl = code_slice(a.repo, c.get("file", ""), c.get("line_range"), context=25, ref=head)
        user = f"Candidate finding: {json.dumps(c)}\n\nCode under review:\n```\n{sl}\n```"
        resp = _call(m, key, VERIFY_SYS, user)
        track("verify", m, len(VERIFY_SYS) + len(user), len(resp))
        v = parse_json(resp)
        verdict = str((v or {}).get("verdict", "")).lower()
        verify_trace.append({
            "file": c.get("file"), "line_range": c.get("line_range"), "issue": c.get("issue"),
            "slice_ok": not sl.startswith("[code_slice"),
            "slice_head": sl[:200],
            "parse_ok": v is not None,
            "verdict": verdict or None,
            "evidence": (v or {}).get("evidence") if v else None,
            "raw_head": (resp or "")[:300],
        })
        if verdict == "confirmed":
            confirmed.append({**c, **(v or {})})
    print(f"Verifier confirmed {len(confirmed)}.")

    # STAGE 3 -- adversarial
    m = STAGES["adversarial"]
    key = key_or_die(m)
    final = []
    for f in confirmed:
        wide = code_slice(a.repo, f.get("file", ""), whole_file=True, ref=head)
        user = f"Confirmed finding: {json.dumps(f)}\n\nBroader context:\n```\n{wide}\n```"
        resp = _call(m, key, ADV_SYS, user)
        track("adversarial", m, len(ADV_SYS) + len(user), len(resp))
        adv = parse_json(resp) or {}
        if adv.get("survives") is True:
            final.append({**f, **adv})
    print(f"Survived adversarial: {len(final)}.")
    print(f"funnel: scout {len(candidates)} -> verify {len(confirmed)} -> final {len(final)}\n")

    # Optional single-model baseline over the whole diff (cost/finding comparison).
    if a.baseline:
        bm = STAGES["verify"]
        bresp = _call(bm, key_or_die(bm), SINGLE_SYS, f"Review this diff and report the real issues.\n\n{diff}")
        bfind = (parse_json(bresp) or {}).get("findings", []) or []
        bcost = cost(bm, len(SINGLE_SYS) + len(diff), len(bresp))
        meta["baseline"] = {"model": bm, "findings": len(bfind), "cost": round(bcost, 5)}
        print(f"baseline: single {bm} over the whole diff -> {len(bfind)} findings, ${bcost:.4f}\n")

    total_cost = round(sum(s["cost"] for s in meta["stages"].values()), 5)
    meta["total_cost"] = total_cost

    # Shape survivors into the finding schema scorer.score_record expects.
    findings = [{
        "file": f.get("file"),
        "line_range": f.get("line_range"),
        "severity": (f.get("severity") or f.get("severity_guess") or "low"),
        "issue": f.get("issue"),
        "suggested_fix": f.get("evidence", ""),
        "status": "open",
        "confidence": f.get("confidence"),
    } for f in final]

    out = {
        "benchmark_name": label,
        "reviewer_ai": "tiered",
        "run_meta": meta,
        "scout_candidates": candidates,
        "verify_trace": verify_trace,
        "final_verdict": final,
        "result": {"findings": findings},
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    st = meta["stages"]
    print(f"cost: scout ${st.get('scout', {}).get('cost', 0):.4f} | "
          f"verify ${st.get('verify', {}).get('cost', 0):.4f} | "
          f"adversarial ${st.get('adversarial', {}).get('cost', 0):.4f} | "
          f"TOTAL ${total_cost:.4f}")
    print(f"-> {a.out}")
    print(f"Now score it:\n  python score_tiered.py --result {a.out} --bug-index {a.bug_index}")


if __name__ == "__main__":
    main()
