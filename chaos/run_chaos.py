#!/usr/bin/env python3
"""run_chaos.py -- Chaos Audit validation: inject bugs into YOUR code, see which
models catch them, and check whether the models actually SEPARATE.

For each target .py file we generate single-mutation diffs (mutate.py), then have
each model review each diff blind. Grading is dead simple and needs no answer key
beyond the mutation itself: each diff contains exactly ONE injected change, so if a
model returns any real finding, it caught the bug; an empty review means it missed.

The number that matters is the SPREAD across models. If every model catches
everything (or nothing), a per-codebase audit tells a customer nothing and the idea
is dead -- the same "no discrimination" failure the curated suites had. If models
land at meaningfully different catch rates on your code, the audit has signal.

Runs the provider APIs directly with local keys (BYOK), like the other benchmark
runners: ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY (or GOOGLE_API_KEY) /
DEEPSEEK_API_KEY, in the env or backend/.env.

Usage (from benchmark/chaos/):
  python run_chaos.py --target ../../backend --max-mutations 15
  python run_chaos.py --target ../../backend --models claude-opus-4-8 gpt-4o deepseek-chat
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH / "lifecycle"))
sys.path.insert(0, str(BENCH))
from lifecycle_runner import load_env, key_for, call  # noqa: E402
from scorer import _endorses_change  # noqa: E402

from mutate import generate_mutations  # noqa: E402

DEFAULT_MODELS = ["claude-opus-4-8", "gpt-4o", "gemini-2.5-pro", "deepseek-chat"]
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "migrations", "tests", "test", ".venv", "venv"}

REVIEW_SYS = (
    "You are a senior code reviewer. Review this diff and report any real bug, security issue, or "
    "regression the change introduces. If the change is harmless, return an empty list.\n"
    'Return STRICT JSON only: { "findings": [ { "issue": "<what is wrong>", '
    '"severity": "high|medium|low", "status": "open" } ] }'
)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def parse_json(text):
    if not text:
        return None
    s = _FENCE.sub("", text.strip())
    for c in (s, s[s.find("{"): s.rfind("}") + 1] if "{" in s else ""):
        try:
            return json.loads(c)
        except Exception:
            continue
    return None


def caught(resp) -> bool:
    """A review counts as a catch if it returns at least one finding that is framed
    as a real problem (not an 'this is fine' endorsement)."""
    findings = (parse_json(resp) or {}).get("findings") or []
    return any(not _endorses_change(f) for f in findings)


def collect_mutations(target: Path, cap: int, seed: int = 7):
    files = []
    if target.is_file():
        files = [target]
    else:
        for p in sorted(target.rglob("*.py")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.name.endswith((".stale_bak", ".stale_bak1", ".stale_bak3")) or ".bak" in p.name:
                continue
            files.append(p)
    muts = []
    for p in files:
        try:
            src = p.read_text(encoding="utf-8")
            for mu in generate_mutations(src, p.name):
                mu["path"] = str(p)
                muts.append(mu)
        except Exception:
            continue
    random.Random(seed).shuffle(muts)
    return muts[:cap]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=Path, required=True, help="File or directory of .py code to audit")
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--max-mutations", type=int, default=15)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "chaos.json")
    a = ap.parse_args()
    load_env()

    muts = collect_mutations(a.target, a.max_mutations)
    if not muts:
        sys.exit("No mutations generated (no parseable .py files under target?).")
    keys = {m: key_for(m) for m in a.models}
    usable = [m for m in a.models if keys[m][0]]
    for m in a.models:
        if not keys[m][0]:
            print(f"  SKIP {m}: set {keys[m][1]}")
    if not usable:
        sys.exit("No usable models: set at least one provider key.")

    print(f"Injected {len(muts)} bugs into {a.target} | models: {', '.join(usable)}\n")
    scores = {m: {"caught": 0, "total": 0} for m in usable}
    detail = []
    for i, mu in enumerate(muts, 1):
        row = {"type": mu["type"], "detail": mu["detail"], "file": mu["file"], "caught_by": []}
        for m in usable:
            try:
                resp = call(m, keys[m][0], REVIEW_SYS, f"Review this diff:\n\n{mu['diff']}")
            except Exception as e:
                print(f"  ERROR {m} on mutation {i}: {e}")
                continue
            hit = caught(resp)
            scores[m]["total"] += 1
            if hit:
                scores[m]["caught"] += 1
                row["caught_by"].append(m)
        detail.append(row)
        print(f"  [{i:>2}/{len(muts)}] {mu['type']:14} caught by: {', '.join(row['caught_by']) or 'NONE'}")

    print("\n=== catch rate per model (on YOUR code) ===")
    rates = {}
    for m in usable:
        s = scores[m]
        pct = 100 * s["caught"] / s["total"] if s["total"] else 0
        rates[m] = pct
        print(f"  {m:22} {s['caught']:>2}/{s['total']:<2}  {pct:5.1f}%")
    spread = (max(rates.values()) - min(rates.values())) if rates else 0
    print(f"\nSPREAD (max - min): {spread:.1f} points")
    if spread < 15:
        print("  -> LOW spread: models barely differ on your code. A per-codebase audit"
              "\n     would tell a customer little. This is the kill signal.")
    else:
        print("  -> Real spread: the audit separates models on your own code. Signal worth pursuing.")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"target": str(a.target), "models": usable,
                                 "rates": rates, "spread": spread, "detail": detail}, indent=2), encoding="utf-8")
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
