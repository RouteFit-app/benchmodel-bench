#!/usr/bin/env python3
"""run_controls.py -- run the anti-cheat NEGATIVE CONTROLS through each reviewer.

Each control (controls.json) is SAFE code that looks like a famous vulnerability.
We scrub any CVE/advisory tells out of the diff, hand it to each model with a
neutral "review this diff" prompt (no hint that it's clean), and save the
findings. score_controls.py then grades false alarms.

Runs the provider APIs directly with local keys, the same way the lifecycle /
correctness / red-team runners do: ANTHROPIC_API_KEY / OPENAI_API_KEY /
GEMINI_API_KEY (or GOOGLE_API_KEY) / DEEPSEEK_API_KEY, in the env or backend/.env.

Usage (from benchmark/anti_cheat/):
    python run_controls.py                              # default 5 models, 1 run each
    python run_controls.py --models claude-opus-4-8 gpt-4o
    python run_controls.py --runs 3                     # repeat each control 3x (recall is consistent; this exposes flaky flags)
    python run_controls.py --no-scrub                   # submit raw diffs (to A/B the scrubber's effect)
Then:
    python score_controls.py
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
RESULTS = HERE / "results"

# Reuse the proven direct-call helpers (load_env / key_for / call) from the
# lifecycle runner rather than duplicating provider plumbing.
sys.path.insert(0, str(BENCH / "lifecycle"))
from lifecycle_runner import load_env, key_for, call  # noqa: E402

from scrub import scrub_diff  # noqa: E402

DEFAULT_MODELS = [
    "claude-opus-4-8", "claude-sonnet-4-6", "gemini-2.5-pro", "gpt-4o", "deepseek-chat",
]

# Neutral reviewer prompt -- intentionally gives NO hint that the code might be
# clean, so a model's own tendency to pattern-match a remembered vuln shows
# through. Asks for the same finding schema the product uses so the scorer's
# polarity guard (status / issue / suggested_fix) has the fields it needs.
REVIEW_SYSTEM = (
    "You are a senior security code reviewer. Review the diff you are given and "
    "report genuine security or correctness problems in the CHANGED code.\n\n"
    "Respond with STRICT JSON only, no markdown fences, in this shape:\n"
    '{"summary": "<one sentence>", "findings": [\n'
    '  {"file": "<path>", "line_range": "<e.g. 12-14 or N/A>", '
    '"severity": "high|medium|low", "status": "open|resolved|informational", '
    '"issue": "<what is wrong>", "suggested_fix": "<how to fix, or empty>"}\n'
    "]}\n"
    "If the changed code is correct and safe, return an empty findings list. "
    "Only report a problem that is actually present in the code shown."
)

TASK_FRAMING = (
    "Review the following pending change. Report any security or correctness "
    "issues you find.\n\n```diff\n{diff}\n```"
)

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_findings(text: str) -> dict:
    """Best-effort parse of a model's JSON review. Returns {summary, findings:[...]}.
    A response we can't parse yields an empty finding list (which scores as 'no
    false alarm') but is flagged with parse_error so it's visible, never silently
    counted as a clean pass."""
    if not text:
        return {"summary": "", "findings": [], "parse_error": "empty response"}
    stripped = _FENCE_RE.sub("", text.strip())
    # Try the whole thing, then the outermost {...} slice.
    for candidate in (stripped, _outer_object(stripped)):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict):
            obj.setdefault("findings", [])
            if not isinstance(obj["findings"], list):
                obj["findings"] = []
            return obj
        if isinstance(obj, list):  # model returned a bare findings array
            return {"summary": "", "findings": obj}
    return {"summary": "", "findings": [], "parse_error": "unparseable JSON", "raw": text[:2000]}


def _outer_object(s: str) -> str | None:
    i, j = s.find("{"), s.rfind("}")
    return s[i:j + 1] if 0 <= i < j else None


def safe(s: str) -> str:
    return "".join(ch if (ch.isalnum() or ch in "-_.") else "-" for ch in s)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--controls", type=Path, default=HERE / "controls.json")
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--runs", type=int, default=1, help="Repeat each control N times per model.")
    ap.add_argument("--no-scrub", action="store_true", help="Submit raw diffs (A/B the scrubber).")
    args = ap.parse_args()

    load_env()
    spec = json.loads(args.controls.read_text(encoding="utf-8"))
    controls = spec["controls"]
    args.out.mkdir(parents=True, exist_ok=True)

    keys = {m: key_for(m) for m in args.models}
    usable = [m for m in args.models if keys[m][0]]
    for m in args.models:
        if not keys[m][0]:
            print(f"  SKIP {m}: set {keys[m][1]}")
    if not usable:
        sys.exit("No usable models: set at least one provider key in env or backend/.env.")

    print(f"Controls: {len(controls)} | models: {', '.join(usable)} | runs: {args.runs} | "
          f"scrub: {'off' if args.no_scrub else 'on'}\n")

    for c in controls:
        diff_path = args.controls.parent / c["diff_file"]
        raw_diff = diff_path.read_text(encoding="utf-8")
        if args.no_scrub:
            diff, removed = raw_diff, []
        else:
            diff, removed = scrub_diff(raw_diff)
        user_msg = TASK_FRAMING.format(diff=diff)

        for m in usable:
            for r in range(1, args.runs + 1):
                try:
                    text = call(m, keys[m][0], REVIEW_SYSTEM, user_msg)
                except Exception as e:
                    print(f"  ERROR {m} on {c['id']} (run {r}): {e}")
                    continue
                parsed = parse_findings(text)
                record = {
                    "run_at": datetime.now(timezone.utc).isoformat(),
                    "suite": spec.get("suite", "Anti-Cheat Negative Controls"),
                    "control_id": c["id"],
                    "trap_class": c.get("trap_class"),
                    "resembles": c.get("resembles"),
                    "model": m,
                    "run": r,
                    "scrub_removed": removed,
                    "result": {"summary": parsed.get("summary", ""), "findings": parsed.get("findings", [])},
                    "parse_error": parsed.get("parse_error"),
                    "raw_text": text,
                }
                suffix = f"__run{r}" if args.runs > 1 else ""
                out_path = args.out / f"{c['id']}__{safe(m)}{suffix}.json"
                out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
                n = len(record["result"]["findings"])
                flag = " [PARSE ERROR]" if parsed.get("parse_error") else ""
                print(f"  {m:22} {c['id']:22} findings={n}{flag} -> {out_path.name}")

    print(f"\nDone. Now: python score_controls.py --results-dir {args.out}")


if __name__ == "__main__":
    main()
