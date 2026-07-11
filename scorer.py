"""
scorer.py -- RouteFit Bug Injection benchmark scorer.

Takes one or more result JSON files written by runner.py (each one review
submission for a given reviewer_ai/writer_ai combo) and grades the findings
against the answer key in bug_index.json. Unlike runner.py, this script DOES
read the full bug list (the answer key) -- that's the whole point of a
grading step that only runs after submission.

For each finding in a review result, a bug is considered "detected" if the
finding's issue/suggested_fix text mentions at least one of that bug's
detection_hints.must_mention_any keywords. Points are awarded per the
`scoring` block read live from bug_index.json on disk -- nothing about the
weights is hardcoded here, so editing bug_index.json changes scoring
behavior automatically (same rule runner.py follows for benchmark metadata).

Leaderboard support (on top of the original per-bug/per-finding grading):
  - severity_breakdown: detected/total counts for exactly the three severity
    tiers that exist in bug_index.json today -- high, medium, low. There is
    no "critical" tier; do not add one here without first auditing
    bug_index.json's actual severities (see bug_index.json's bugs[]).
  - security_relevant: detected/total counts restricted to bugs tagged
    security_relevant=true in bug_index.json (resource/memory leaks, crash
    bugs, data loss -- see that file for the per-bug tagging).
  - high_severity_missed_count: how many High-severity bugs were never
    detected. This is what the Leaderboard's "N high severity missed" badge
    is keyed on.
  - weighted_score: a severity-weighted variant of the existing raw_score/
    max_possible_score/score_pct, using bug_index.json's scoring.severity_weight
    block (e.g. high=1.5x, medium=1.0x, low=0.5x) so that detecting a
    High-severity bug counts for more than detecting a Medium one. This is
    what the Leaderboard ranks/sorts on by default. The false-positive
    penalty is NOT weighted (it isn't tied to any one bug's severity).
  - bug_index_commit_hash: the most recent git commit that touched
    bug_index.json, captured once per scoring run, so a published Leaderboard
    row can be pinned to the exact answer-key version it was graded against.
    Best-effort -- None if this isn't a git checkout or git isn't available.

Output per input file: a `scored_<name>.json` with a full per-bug and
per-finding breakdown, plus a `scoreboard.json` / `scoreboard.txt` comparing
every file processed in the same run side by side (one row per model combo).
Each input file is still scored independently and 1:1 -- aggregating
multiple runs of the same writer/reviewer combo into one Leaderboard entry
(mean score, variance, run_count, pooled severity/security detection) is a
separate step, done by benchmark/publish_leaderboard.py against this
script's scoreboard.json output. That keeps this script's contract
(one input file -> one scored row) unchanged and avoids duplicating grading
logic in two places.

Usage:
    python scorer.py path/to/result.json [more results...]
    python scorer.py --results-dir benchmark/results/
    python scorer.py --results-dir benchmark/results/ --out-dir benchmark/scored/
    python scorer.py benchmark/smoke_test/checkbeachconditions__smoke.json   # dry run

Smoke test note: benchmark/smoke_test/checkbeachconditions__smoke.json is a
real review result for an unrelated app (CheckBeachConditions), not part of
the RouteFit bug_index.json bug set. Scoring it is expected to produce 0
detected bugs and several false positives -- that's not a bug in this
script, it's just confirmation that the parsing/matching logic runs cleanly
on a real-world finding format without crashing, before trusting it on the
actual RouteFit benchmark data.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
DEFAULT_BUG_INDEX = BENCHMARK_DIR / "bug_index.json"
DEFAULT_RESULTS_DIR = BENCHMARK_DIR / "results"

REQUIRED_SCORING_KEYS = [
    "detect_points",
    "correct_file_bonus",
    "correct_severity_bonus",
    "false_positive_penalty",
]

# The only severity tiers that exist in bug_index.json today. Fixed on
# purpose: an earlier Leaderboard mockup implied a 4th "critical" tier, but
# bug_index.json's bugs only ever use high/medium (no low bugs exist yet
# either). Don't invent a tier here to match a mockup -- if bug_index.json
# ever legitimately needs a "critical" tier, that's a deliberate, separate
# taxonomy change to this constant plus an audit of every existing bug.
SEVERITY_TIERS = ["high", "medium", "low"]

TABLE_COLUMNS = [
    ("Reviewer AI", 20),
    ("Writer AI", 22),
    ("Detected", 10),
    ("File Acc", 9),
    ("Sev Acc", 8),
    ("False Pos", 10),
    ("Dup", 5),
    ("Score", 8),
    ("Max", 6),
    ("%", 7),
    ("W.Score%", 9),
]


def load_bug_index(path: Path) -> dict:
    """Read bug_index.json in full, including the answer key (bugs[]) and
    the live scoring weights. Raises a clear error if the expected schema
    isn't there, rather than silently defaulting/mis-scoring."""
    if not path.is_file():
        raise SystemExit(f"bug_index.json not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))

    for key in ("benchmark_name", "scoring", "bugs"):
        if key not in data:
            raise SystemExit(f"bug_index.json ({path}) is missing required top-level key '{key}'")

    missing = [k for k in REQUIRED_SCORING_KEYS if k not in data["scoring"]]
    if missing:
        raise SystemExit(
            f"bug_index.json's 'scoring' block ({path}) is missing key(s) {missing}. "
            f"Found keys: {list(data['scoring'].keys())}"
        )
    return data


def get_bug_index_commit_hash(bug_index_path: Path) -> str | None:
    """Best-effort: the most recent git commit that touched bug_index.json,
    so a scored result can be pinned to the exact answer-key version it was
    graded against. Returns None (not an error) if this isn't a git
    checkout, git isn't installed, or the file isn't tracked yet -- the
    Leaderboard should render that as 'unknown provenance' rather than fail
    the whole scoring/publish run over it."""
    try:
        repo_root = subprocess.run(
            ["git", "-C", str(bug_index_path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        rel_path = bug_index_path.resolve().relative_to(Path(repo_root).resolve())
        result = subprocess.run(
            ["git", "-C", repo_root, "log", "-1", "--format=%H", "--", str(rel_path)],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _norm(s) -> str:
    return (s or "").lower()


def _basename(s) -> str:
    return (s or "").replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


# A reviewer sometimes flags the right code but frames the change as a FIX or an
# intentional improvement rather than a bug (e.g. "a vulnerability was fixed",
# "this is a deliberate change to allow ..."). Keyword matching alone over-credits
# that as a detection. These patterns catch clear ENDORSEMENTS of the changed code
# so such findings don't count as catching the bug. Deliberately conservative:
# only strong, unambiguous "this is correct / intended / already fixed" phrasing,
# so a genuine problem report ("... is incorrect", "... will cause a crash") is
# never suppressed.
_ENDORSE_RE = re.compile(
    r"\b(?:was|is|has been|been|already|now)\s+(?:correctly\s+)?"
    r"(?:fixed|resolved|addressed|corrected|patched)\b"
    r"|\bdeliberate\b|\bintentional(?:ly)?\b|\bby design\b"
    r"|\bas intended\b|\bworking as intended\b"
    r"|\bno (?:action|change|fix)\s+(?:is\s+)?(?:needed|required)\b"
    r"|\bnot (?:a|an)\s+(?:bug|issue|problem|vulnerab\w*)\b"
    r"|\b(?:is|looks|seems|appears)\s+correct\b",
    re.IGNORECASE,
)


# A finding's own status field is an explicit endorsement signal the reviewer
# set: "open" = a live problem; "resolved"/"informational"/etc = "this is fine /
# already handled / just FYI". A finding that names the right code but files it
# under any of these is the reviewer declining to flag it as a bug, which the
# polarity guard must treat as a non-catch (same as the text-based endorsements).
_ENDORSE_STATUSES = {
    "resolved", "informational", "fixed", "dismissed", "wontfix",
    "accepted", "not_an_issue", "no_action", "intended",
}


def _endorses_change(finding: dict) -> bool:
    """True if the finding frames the changed (buggy) code as a fix / intended /
    correct rather than identifying it as a problem. Such a finding should NOT
    count as detecting the injected bug, even if it mentions the right keywords.
    Triggers on either an explicit non-open status or clear endorsement phrasing."""
    status = (finding.get("status") or "open").strip().lower()
    if status in _ENDORSE_STATUSES:
        return True
    text = f"{finding.get('issue') or ''} {finding.get('suggested_fix') or ''}"
    return bool(_ENDORSE_RE.search(text))


def find_matching_bug(finding: dict, bugs: list[dict]) -> tuple[dict | None, list[str]]:
    """Pick the best bug match for a finding: most matched keywords wins;
    ties broken in favor of a matching file. Returns (bug_or_None, matched_keywords)."""
    text = _norm(finding.get("issue")) + " " + _norm(finding.get("suggested_fix"))
    finding_file = _basename(finding.get("file"))

    best_bug = None
    best_hints: list[str] = []
    best_file_match = False

    for bug in bugs:
        hints = bug.get("detection_hints", {}).get("must_mention_any", [])
        matched = [h for h in hints if h and h.lower() in text]
        if not matched:
            continue
        file_match = finding_file == _basename(bug.get("file"))
        # A file match is the STRONGEST signal: the same finding text often shares
        # keywords with bugs in other files (e.g. "is_superuser"/"superuser" appear
        # in two different bugs, and "logic" substring-matches "logical error"), so
        # a finding in deps.py must not be claimed by a users.py bug just because it
        # racked up more keyword hits. Rank file-match first, then keyword count.
        better = (
            best_bug is None
            or (file_match and not best_file_match)
            or (file_match == best_file_match and len(matched) > len(best_hints))
        )
        if better:
            best_bug, best_hints, best_file_match = bug, matched, file_match

    return best_bug, best_hints


def _matches_distractor(finding: dict, distractors: list[dict]) -> dict | None:
    """A distractor is a benign change deliberately added to create 'routine
    cleanup' cover for the real bug. A reviewer flagging one is being cautious,
    not wrong, so such a finding must NOT count as a false positive. Match on the
    distractor's keywords (file-agnostic, since consolidated findings often set
    file='general' but name the change in prose); a file match is a bonus signal
    but not required. Returns the matched distractor, or None."""
    text = _norm(finding.get("issue")) + " " + _norm(finding.get("suggested_fix"))
    finding_file = _basename(finding.get("file"))
    best = None
    best_n = 0
    for d in distractors:
        kws = d.get("match_keywords", [])
        matched = [k for k in kws if k and k.lower() in text]
        if not matched:
            continue
        # Prefer the distractor whose file also matches, then most keywords.
        file_match = bool(finding_file) and finding_file == _basename(d.get("file"))
        score = len(matched) + (100 if file_match else 0)
        if score > best_n:
            best, best_n = d, score
    return best


def score_record(record: dict, bug_index: dict, bug_index_commit_hash: str | None = None) -> dict:
    bugs = bug_index["bugs"]
    distractors = bug_index.get("distractors", [])
    weights = bug_index["scoring"]
    detect_points = weights["detect_points"]
    correct_file_bonus = weights["correct_file_bonus"]
    correct_severity_bonus = weights["correct_severity_bonus"]
    false_positive_penalty = weights["false_positive_penalty"]
    severity_weight = weights.get("severity_weight", {})

    def _weight_for(severity) -> float:
        # Bugs with a severity not present in severity_weight (or no
        # severity_weight block at all, for an older bug_index.json) score
        # at a neutral 1.0x rather than erroring.
        return severity_weight.get(_norm(severity), 1.0)

    findings = ((record.get("result") or {}).get("findings")) or []

    bug_status = {
        bug["id"]: {
            "id": bug["id"],
            "file": bug.get("file"),
            "category": bug.get("category"),
            "difficulty": bug.get("difficulty"),
            "severity": bug.get("severity"),
            "security_relevant": bool(bug.get("security_relevant", False)),
            "description": bug.get("description"),
            "detected": False,
            "matched_finding_index": None,
            "file_correct": False,
            "severity_correct": False,
            "reviewer_severity": None,
            "provenance": bug.get("provenance"),
            "points": 0,
        }
        for bug in bugs
    }

    finding_results = []
    claimed_ids: set[str] = set()

    for idx, finding in enumerate(findings):
        bug, matched_hints = find_matching_bug(finding, bugs)

        base = {
            "index": idx,
            "file": finding.get("file"),
            "severity": finding.get("severity"),
            "issue": finding.get("issue"),
            "confidence": finding.get("confidence"),
        }

        if bug is None:
            # Before calling it a false positive, see if the finding is about a
            # benign distractor. If so it's neutral: the reviewer flagged a real
            # (but harmless) cleanup, which is caution, not noise. No points, no
            # penalty -- the only thing this suite scores is the real bug.
            distractor = _matches_distractor(finding, distractors)
            if distractor is not None:
                finding_results.append({
                    **base,
                    "matched_bug_id": None,
                    "matched_distractor_id": distractor.get("id"),
                    "matched_keywords": [],
                    "is_false_positive": False,
                    "is_distractor": True,
                    "is_duplicate": False,
                    "points": 0,
                })
                continue
            finding_results.append({
                **base,
                "matched_bug_id": None,
                "matched_keywords": [],
                "is_false_positive": True,
                "is_duplicate": False,
                "points": false_positive_penalty,
            })
            continue

        bug_id = bug["id"]
        file_correct = _basename(finding.get("file")) == _basename(bug.get("file"))
        severity_correct = _norm(finding.get("severity")) == _norm(bug.get("severity"))

        if _endorses_change(finding):
            # The finding cites the right code but calls the change a fix / an
            # intentional improvement, not a bug. Don't credit detection; it's not
            # a false positive either (the reviewer did look at the right place).
            # The bug stays uncredited, a later genuine finding can still claim it.
            finding_results.append({
                **base,
                "matched_bug_id": bug_id,
                "matched_keywords": matched_hints,
                "is_false_positive": False,
                "is_duplicate": False,
                "is_endorsement": True,
                "points": 0,
            })
            continue

        if bug_id in claimed_ids:
            # Already credited via an earlier finding -- this is a correct but
            # redundant re-mention. Don't double-award points, but don't treat
            # it as a false positive either.
            finding_results.append({
                **base,
                "matched_bug_id": bug_id,
                "matched_keywords": matched_hints,
                "is_false_positive": False,
                "is_duplicate": True,
                "points": 0,
            })
            continue

        claimed_ids.add(bug_id)
        points = detect_points
        if file_correct:
            points += correct_file_bonus
        if severity_correct:
            points += correct_severity_bonus

        bug_status[bug_id].update({
            "detected": True,
            "matched_finding_index": idx,
            "file_correct": file_correct,
            "severity_correct": severity_correct,
            "reviewer_severity": finding.get("severity"),
            "points": points,
        })
        finding_results.append({
            **base,
            "matched_bug_id": bug_id,
            "matched_keywords": matched_hints,
            "is_false_positive": False,
            "is_duplicate": False,
            "points": points,
        })

    # ── Pair-aware credit (cross-hunk suites) ────────────────────────────────
    # A bug may carry a "pair_id". A cross-hunk vulnerability is split across two
    # files on purpose; a reviewer who correctly consolidates it into ONE finding
    # that names both hunks (the right senior-reviewer behavior) would otherwise
    # be scored as detecting only half the pair. Here, if one bug of a pair is
    # detected and the SAME finding's text also satisfies the partner bug's
    # detection hints, credit the partner too (matched to that finding). We also
    # upgrade file_correct when the finding text names the bug's file (consolidated
    # findings often set file="general" but name the files in prose). Only bugs
    # with a pair_id are touched, so non-paired suites score exactly as before.
    pair_groups: dict[str, list[dict]] = {}
    for bug in bugs:
        pid = bug.get("pair_id")
        if pid:
            pair_groups.setdefault(pid, []).append(bug)

    for pair_bugs in pair_groups.values():
        seed = next(
            (b for b in pair_bugs if bug_status[b["id"]]["detected"]
             and bug_status[b["id"]]["matched_finding_index"] is not None),
            None,
        )
        if seed is None:
            continue
        src_idx = bug_status[seed["id"]]["matched_finding_index"]
        if not (0 <= src_idx < len(findings)):
            continue
        src = findings[src_idx]
        ftext = _norm(src.get("issue")) + " " + _norm(src.get("suggested_fix"))
        for b in pair_bugs:
            st = bug_status[b["id"]]
            bfile = _basename(b.get("file"))
            if st["detected"]:
                # Consolidated finding named this file in prose -> grant file bonus.
                if not st["file_correct"] and bfile and bfile in ftext:
                    st["file_correct"] = True
                    st["points"] += correct_file_bonus
                continue
            hints = b.get("detection_hints", {}).get("must_mention_any", [])
            if not any(h and h.lower() in ftext for h in hints):
                continue
            file_correct = (_basename(src.get("file")) == bfile) or (bool(bfile) and bfile in ftext)
            severity_correct = _norm(src.get("severity")) == _norm(b.get("severity"))
            pts = detect_points
            if file_correct:
                pts += correct_file_bonus
            if severity_correct:
                pts += correct_severity_bonus
            st.update({
                "detected": True,
                "matched_finding_index": src_idx,
                "file_correct": file_correct,
                "severity_correct": severity_correct,
                "reviewer_severity": src.get("severity"),
                "points": pts,
                "pair_credited": True,
            })

    bugs_total = len(bugs)
    bugs_detected = sum(1 for b in bug_status.values() if b["detected"])
    file_correct_count = sum(1 for b in bug_status.values() if b["detected"] and b["file_correct"])
    severity_correct_count = sum(1 for b in bug_status.values() if b["detected"] and b["severity_correct"])
    false_positive_count = sum(1 for f in finding_results if f["is_false_positive"])
    duplicate_count = sum(1 for f in finding_results if f["is_duplicate"])
    distractor_flag_count = sum(1 for f in finding_results if f.get("is_distractor"))

    bug_points_total = sum(b["points"] for b in bug_status.values())
    penalty_total = sum(f["points"] for f in finding_results if f["is_false_positive"])
    raw_score = bug_points_total + penalty_total
    max_possible = bugs_total * (detect_points + correct_file_bonus + correct_severity_bonus)
    score_pct = round((raw_score / max_possible * 100), 1) if max_possible else 0.0

    # Severity-weighted score: same point system, but each bug's contribution
    # is scaled by its severity_weight. The false-positive penalty is left
    # unweighted since it isn't tied to any one bug's severity.
    weighted_raw = round(
        sum(b["points"] * _weight_for(b["severity"]) for b in bug_status.values()) + penalty_total,
        2,
    )
    weighted_max = round(
        sum(
            (detect_points + correct_file_bonus + correct_severity_bonus) * _weight_for(bug.get("severity"))
            for bug in bugs
        ),
        2,
    )
    weighted_pct = round((weighted_raw / weighted_max * 100), 1) if weighted_max else 0.0

    # Per-severity-tier detected/total -- fixed to SEVERITY_TIERS (high/medium/low).
    severity_breakdown = {tier: {"detected": 0, "total": 0} for tier in SEVERITY_TIERS}
    for bug in bugs:
        tier = _norm(bug.get("severity"))
        if tier not in severity_breakdown:
            # An unexpected severity value showed up in bug_index.json that
            # isn't one of the 3 known tiers. Still count it (so totals add
            # up and nothing is silently dropped) without retroactively
            # treating it as one of the fixed tiers above.
            severity_breakdown.setdefault(tier, {"detected": 0, "total": 0})
        severity_breakdown[tier]["total"] += 1
        if bug_status[bug["id"]]["detected"]:
            severity_breakdown[tier]["detected"] += 1

    high_severity_missed_count = sum(
        1 for b in bug_status.values() if _norm(b["severity"]) == "high" and not b["detected"]
    )

    security_relevant_total = sum(1 for bug in bugs if bug.get("security_relevant"))
    security_relevant_detected = sum(
        1 for bug in bugs if bug.get("security_relevant") and bug_status[bug["id"]]["detected"]
    )

    return {
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "bug_index_benchmark_name": bug_index.get("benchmark_name"),
        "bug_index_version": bug_index.get("version", 1),
        "bug_index_commit_hash": bug_index_commit_hash,
        "scoring_weights_used": {
            "detect_points": detect_points,
            "correct_file_bonus": correct_file_bonus,
            "correct_severity_bonus": correct_severity_bonus,
            "false_positive_penalty": false_positive_penalty,
            "severity_weight": severity_weight,
        },
        "model_combo": {
            "reviewer_ai": record.get("reviewer_ai"),
            "writer_ai": record.get("writer_ai"),
        },
        # tech_stack powers the Leaderboard's tab filter and is part of the
        # (tech_stack, writer_ai, reviewer_ai) grouping key publish_leaderboard.py
        # rolls runs up by. Sourced from the runner.py result record, which in
        # turn pulled it from the BenchModel project's configured tech_stack.
        # May be None for older result files saved before this field existed.
        "tech_stack": record.get("tech_stack"),
        "task": record.get("task"),
        "overall_score_reported": (record.get("result") or {}).get("overall_score"),
        "totals": {
            "bugs_total": bugs_total,
            "bugs_detected": bugs_detected,
            "detection_rate_pct": round(bugs_detected / bugs_total * 100, 1) if bugs_total else 0.0,
            "file_correct_count": file_correct_count,
            "severity_correct_count": severity_correct_count,
            "false_positive_count": false_positive_count,
            "duplicate_count": duplicate_count,
            "distractor_flag_count": distractor_flag_count,
            "raw_score": raw_score,
            "max_possible_score": max_possible,
            "score_pct": score_pct,
        },
        "weighted_score": {
            "raw": weighted_raw,
            "max": weighted_max,
            "pct": weighted_pct,
        },
        "severity_breakdown": severity_breakdown,
        "high_severity_missed_count": high_severity_missed_count,
        "security_relevant": {
            "detected": security_relevant_detected,
            "total": security_relevant_total,
        },
        "bugs": list(bug_status.values()),
        "findings": finding_results,
        "source_file": None,  # filled in by caller
    }


def _fit(value, width: int) -> str:
    s = str(value)
    return s if len(s) <= width else s[: width - 1] + "…"


def format_table(rows: list[dict]) -> str:
    header = " | ".join(name.ljust(w) for name, w in TABLE_COLUMNS)
    sep = "-+-".join("-" * w for _, w in TABLE_COLUMNS)
    lines = [header, sep]
    for r in rows:
        t = r["totals"]
        combo = r["model_combo"]
        detected = t["bugs_detected"]
        cells = [
            combo.get("reviewer_ai") or "-",
            combo.get("writer_ai") or "-",
            f"{detected}/{t['bugs_total']}",
            f"{t['file_correct_count']}/{detected}" if detected else "0/0",
            f"{t['severity_correct_count']}/{detected}" if detected else "0/0",
            t["false_positive_count"],
            t["duplicate_count"],
            t["raw_score"],
            t["max_possible_score"],
            f"{t['score_pct']}%",
            f"{r['weighted_score']['pct']}%",
        ]
        lines.append(" | ".join(_fit(c, w).ljust(w) for c, (_, w) in zip(cells, TABLE_COLUMNS)))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="*", type=Path, help="runner.py result JSON file(s) to score.")
    parser.add_argument(
        "--results-dir", type=Path, default=None,
        help="Score every *.json file in this directory instead of explicit files "
             "(default: benchmark/results/, if no input files are given).",
    )
    parser.add_argument("--bug-index", type=Path, default=DEFAULT_BUG_INDEX,
                         help="Path to bug_index.json (default: benchmark/bug_index.json next to this script).")
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Where to write scored_*.json + scoreboard files (default: <input file's dir>/scored/).",
    )
    args = parser.parse_args()

    if args.inputs:
        input_paths = args.inputs
    else:
        results_dir = args.results_dir or DEFAULT_RESULTS_DIR
        if not results_dir.is_dir():
            raise SystemExit(
                f"No input files given and {results_dir} doesn't exist. "
                "Pass result file(s) explicitly, use --results-dir, or run runner.py first."
            )
        input_paths = sorted(results_dir.glob("*.json"))
        if not input_paths:
            raise SystemExit(f"No *.json files found in {results_dir}.")

    bug_index = load_bug_index(args.bug_index)
    weights = bug_index["scoring"]
    bug_index_commit_hash = get_bug_index_commit_hash(args.bug_index)
    print(f"Loaded bug_index.json: {bug_index['benchmark_name']} ({len(bug_index['bugs'])} known bugs)")
    print(f"bug_index.json commit hash: {bug_index_commit_hash or '(unknown -- not a git checkout or file not committed yet)'}")
    print(
        "Scoring weights (live from bug_index.json): "
        f"detect_points={weights['detect_points']}, "
        f"correct_file_bonus={weights['correct_file_bonus']}, "
        f"correct_severity_bonus={weights['correct_severity_bonus']}, "
        f"false_positive_penalty={weights['false_positive_penalty']}, "
        f"severity_weight={weights.get('severity_weight', '(none -- all tiers scored 1.0x)')}"
    )

    out_dir = args.out_dir or (input_paths[0].parent / "scored")
    out_dir.mkdir(parents=True, exist_ok=True)

    scored_rows = []
    for path in input_paths:
        if not path.is_file():
            print(f"Skipping {path}: not a file.", file=sys.stderr)
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Skipping {path}: invalid JSON ({e})", file=sys.stderr)
            continue

        scored = score_record(record, bug_index, bug_index_commit_hash=bug_index_commit_hash)
        scored["source_file"] = str(path)

        out_path = out_dir / f"scored_{path.stem}.json"
        out_path.write_text(json.dumps(scored, indent=2), encoding="utf-8")
        t = scored["totals"]
        print(
            f"Scored {path.name}: {t['bugs_detected']}/{t['bugs_total']} bugs detected, "
            f"{t['false_positive_count']} false positive(s), score {t['raw_score']}/{t['max_possible_score']} "
            f"({t['score_pct']}%, weighted {scored['weighted_score']['pct']}%) -> {out_path}"
        )
        scored_rows.append(scored)

    if not scored_rows:
        raise SystemExit("No files were scored (all inputs failed to parse).")

    table = format_table(scored_rows)
    print("\n" + table + "\n")

    scoreboard_json_path = out_dir / "scoreboard.json"
    scoreboard_json_path.write_text(json.dumps(scored_rows, indent=2), encoding="utf-8")
    scoreboard_txt_path = out_dir / "scoreboard.txt"
    scoreboard_txt_path.write_text(table + "\n", encoding="utf-8")
    print(f"Scoreboard -> {scoreboard_json_path}")
    print(f"Scoreboard table -> {scoreboard_txt_path}")


if __name__ == "__main__":
    main()
