#!/usr/bin/env python3
"""score_tiered.py -- grade a tiered run against its suite and show cost-per-caught-bug.

Reuses the main benchmark grader (scorer.score_record), so the pipeline is judged by
the exact same answer key and matching logic as every model on the leaderboard. Then
it divides the run's char-based cost by the number of bugs caught -- the money metric.

Run the same thing for single-model baselines to compare (see README): a lone cheap
model and a lone strong model over the whole diff. The tiered run wins if it lands
near the strong model's catch rate at a fraction of the cost, with fewer false alarms.

Usage (from benchmark/tiered/):
  python score_tiered.py --result results/owasp.json --bug-index ../suites/security-owasp/bug_index.json
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
from scorer import score_record, load_bug_index  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--result", type=Path, required=True, help="run_tiered.py output JSON")
    ap.add_argument("--bug-index", type=Path, required=True, help="the suite's bug_index(.vN).json")
    a = ap.parse_args()

    rec = json.loads(a.result.read_text(encoding="utf-8"))
    bug_index = load_bug_index(a.bug_index)
    scored = score_record(rec, bug_index)

    t = scored["totals"]
    caught, total, fp = t["bugs_detected"], t["bugs_total"], t["false_positive_count"]
    run_meta = rec.get("run_meta") or {}
    run_cost = run_meta.get("total_cost", 0.0)
    cpb = run_cost / caught if caught else 0.0

    ms = run_meta.get("models", {})
    print(f"\n=== {rec.get('benchmark_name')} :: tiered pipeline ===")
    print(f"models: scout={ms.get('scout')}  verify={ms.get('verify')}  adversarial={ms.get('adversarial')}")
    print(f"bugs caught:          {caught}/{total}  ({t['detection_rate_pct']}%)")
    print(f"severity-weighted:    {scored['weighted_score']['pct']}%")
    print(f"false positives:      {fp}")
    print(f"run cost:             ${run_cost:.4f}")
    print(f"COST PER CAUGHT BUG:  ${cpb:.4f}")
    print("\nfunnel (where the money went):")
    for stage in ("scout", "verify", "adversarial"):
        s = run_meta.get("stages", {}).get(stage)
        if s:
            print(f"  {stage:12} calls={s['calls']:>3}  cost=${s['cost']:.4f}")


if __name__ == "__main__":
    main()
