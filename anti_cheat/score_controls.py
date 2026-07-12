#!/usr/bin/env python3
"""score_controls.py -- grade the anti-cheat negative controls.

Every control is SAFE code. So any finding that (a) is framed as a live problem
and (b) names the vulnerability class the code resembles is a FALSE ALARM: the
model pattern-matched a remembered vuln instead of reasoning about the actual
(safe) code. That is the memorization / recall signal a CVE-based benchmark
cannot otherwise measure.

We deliberately reuse the MAIN scorer's polarity guard (_endorses_change) so a
model that correctly says "this now uses safe_load, good" is NOT counted as a
false alarm -- only a model that raises the vuln as an open problem is.

    false-alarm rate = (# controls where the model raised the phantom vuln)
                       / (# controls the model reviewed)
Lower is better.

Usage (from benchmark/anti_cheat/):
    python score_controls.py
    python score_controls.py --results-dir results/ --controls controls.json
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent

# Reuse the exact polarity guard the main benchmark uses, so "this is fine /
# already safe" endorsements are treated identically here.
sys.path.insert(0, str(BENCH))
from scorer import _endorses_change  # noqa: E402


def _text(finding: dict) -> str:
    return (f"{finding.get('issue') or ''} {finding.get('suggested_fix') or ''}").lower()


# A trap keyword often appears inside a phrase that DENIES the vuln: "safe from
# arbitrary code execution", "not vulnerable to SQL injection", "command
# injection is prevented". A naive substring match would score those good, safe
# observations as false alarms. So for each occurrence of a keyword we check for
# a negation cue just before it (pre) or just after it (post); an occurrence in
# a negated context does not count. Only a keyword that appears at least once in
# a plain, asserted-as-present context is a real false alarm.
_PRE_NEG = (
    "safe from", "safe against", "not vulnerable", "not susceptible",
    "not exposed", "protected against", "protected from", "immune to",
    "guards against", "guard against", "prevents", "prevent ", "avoids",
    "avoid ", "mitigates", "mitigate ", "no longer", "not an issue",
    "not a concern", "free from", "does not allow", "doesn't allow",
    "cannot execute", "won't execute", "not a risk", "eliminates",
    "resistant to", "defends against", "is safe", "are safe", "isn't a",
    "is not a", "no risk of", "not open to", "closes the", "removes the",
    "disables", "disable ", "disabling", "disabled", "turn off", "turns off",
    "turned off", "rejects", "refuses", "no longer allows", "blocks",
)
_POST_NEG = (
    "is prevented", "are prevented", "is not possible", "isn't possible",
    "is mitigated", "is blocked", "cannot occur", "can't occur", "is avoided",
    "is eliminated", "does not apply", "no longer possible", "is not a risk",
    "is handled", "is now safe", "is addressed", "risk is removed",
    "is disabled", "are disabled", "is turned off", "are turned off",
    "is rejected", "are rejected", "is not allowed", "are not allowed",
)
# Subjunctive / hypothetical cues (added after June Kim's audit, July 2026).
# On safe control code, models routinely explain the SAFE pattern by contrast
# with the unsafe one: "using safe_load prevents the arbitrary code execution
# that yaml.load WOULD ALLOW", "pickle COULD ENABLE RCE, but this uses json".
# The trap keyword then sits right after a subjunctive verb -- it's describing a
# hypothetical, not asserting the vuln is present. The flat-negation cues above
# don't catch that ("prevents" is often outside the pre-window), so the mention
# slipped past and scored as a false alarm. A subjunctive lead-in within the
# pre-window means the keyword is NOT asserted as a live problem.
_PRE_HYPO = (
    "would allow", "would enable", "would permit", "would expose",
    "would introduce", "would make", "would result", "would be", "would have",
    "would let", "could allow", "could enable", "could permit", "could expose",
    "could introduce", "could be", "could let", "if it were", "were it",
    "if this were", "if unsafe", "in theory", "hypothetical", "otherwise allow",
    "otherwise be", "used to allow", "used to be",
)
_PRE_WINDOW = 55
_POST_WINDOW = 45


def _has_unnegated(text: str, kw: str) -> bool:
    """True if kw appears at least once NOT wrapped in a negation or subjunctive
    ("would allow <kw>") phrase."""
    start = 0
    while True:
        i = text.find(kw, start)
        if i == -1:
            return False
        pre = text[max(0, i - _PRE_WINDOW):i]
        post = text[i + len(kw): i + len(kw) + _POST_WINDOW]
        negated = (
            any(c in pre for c in _PRE_NEG)
            or any(c in pre for c in _PRE_HYPO)
            or any(c in post for c in _POST_NEG)
        )
        if not negated:
            return True  # a plainly-asserted occurrence -> real match
        start = i + len(kw)


def false_alarm(finding: dict, trap_keywords: list[str]) -> list[str]:
    """Return the trap keywords this finding raises AS A PRESENT problem. Empty
    list = not a false alarm: either the finding endorses the change as safe/
    fixed, the keyword isn't there, or every mention is inside a negation ("safe
    from <vuln>")."""
    if _endorses_change(finding):
        return []
    text = _text(finding)
    return [k for k in trap_keywords if k and k.lower() in text and _has_unnegated(text, k.lower())]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", type=Path, default=HERE / "results")
    ap.add_argument("--controls", type=Path, default=HERE / "controls.json")
    ap.add_argument("--out", type=Path, default=HERE / "results" / "control_scoreboard.json")
    args = ap.parse_args()

    spec = json.loads(args.controls.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in spec["controls"]}

    files = sorted(args.results_dir.glob("*.json"))
    files = [f for f in files if f.name != args.out.name]
    if not files:
        sys.exit(f"No result files in {args.results_dir}. Run run_controls.py first.")

    # per model: totals + which controls tripped
    per_model = defaultdict(lambda: {"controls": 0, "false_alarms": 0, "other_flags": 0,
                                     "parse_errors": 0, "tripped": [], "detail": []})
    # per control: which models raised the phantom vuln
    per_control = defaultdict(list)

    for fp in files:
        rec = json.loads(fp.read_text(encoding="utf-8"))
        cid = rec.get("control_id")
        model = rec.get("model")
        ctrl = by_id.get(cid)
        if not ctrl or not model:
            continue
        traps = ctrl.get("trap_keywords", [])
        findings = (rec.get("result") or {}).get("findings") or []

        pm = per_model[model]
        pm["controls"] += 1
        if rec.get("parse_error"):
            pm["parse_errors"] += 1

        matched_any = []
        other = 0
        for f in findings:
            hits = false_alarm(f, traps)
            if hits:
                matched_any.extend(hits)
            elif not _endorses_change(f):
                other += 1  # flagged something else on safe code (noise, not the trap)

        if matched_any:
            pm["false_alarms"] += 1
            pm["tripped"].append(cid)
            per_control[cid].append(model)
        pm["other_flags"] += other
        pm["detail"].append({
            "control": cid, "trap_class": ctrl.get("trap_class"),
            "false_alarm": bool(matched_any), "matched": sorted(set(matched_any)),
            "other_flags": other, "run": rec.get("run", 1),
        })

    # ---- print scoreboard ----
    models = sorted(per_model, key=lambda m: (per_model[m]["false_alarms"] / max(per_model[m]["controls"], 1), m))
    print("\nAnti-Cheat Negative Controls -- false-alarm scoreboard")
    print("(lower false-alarm rate = more reasoning, less memorized recall)\n")
    hdr = f"{'MODEL':24}{'CONTROLS':>9}{'FALSE ALARMS':>14}{'RATE':>8}{'OTHER':>7}{'PARSE ERR':>11}"
    print(hdr)
    print("-" * len(hdr))
    board = []
    for m in models:
        d = per_model[m]
        rate = d["false_alarms"] / d["controls"] if d["controls"] else 0.0
        print(f"{m:24}{d['controls']:>9}{d['false_alarms']:>14}{rate*100:>7.1f}%{d['other_flags']:>7}{d['parse_errors']:>11}")
        board.append({
            "model": m, "controls": d["controls"], "false_alarms": d["false_alarms"],
            "false_alarm_rate": round(rate, 4), "other_flags": d["other_flags"],
            "parse_errors": d["parse_errors"], "tripped_controls": sorted(set(d["tripped"])),
            "detail": d["detail"],
        })

    print("\nPer-control -- which models raised the phantom vulnerability:")
    for cid, ctrl in by_id.items():
        who = sorted(set(per_control.get(cid, [])))
        label = f"{cid} ({ctrl.get('trap_class')})"
        print(f"  {label:42} {', '.join(who) if who else 'none (all reasoned correctly)'}")

    args.out.write_text(json.dumps({
        "suite": spec.get("suite"), "version": spec.get("version"),
        "scoreboard": board,
        "per_control": {cid: sorted(set(per_control.get(cid, []))) for cid in by_id},
    }, indent=2), encoding="utf-8")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
