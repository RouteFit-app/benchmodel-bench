"""
probe_boilerplate.py -- June Kim's audit probe, made reproducible.

The audit (Issue #1) showed the scorer credited a bug as "detected" whenever a
finding brushed a SINGLE keyword from that bug's answer key. So ~20 lines of
generic review boilerplate -- the kind of thing a model says about ANY diff,
with no knowledge of the actual bugs -- scored a large fraction of detection
across every suite, at zero model cost.

This script reruns exactly that attack against every suite's answer key, with
the oracle gate OFF (min_hints_without_file=1, the old behavior) and ON
(min_hints_without_file=2, the fix), and prints the before/after. A model-free
boilerplate reviewer should score near zero. If it doesn't, the metric is
measuring vocabulary, not detection.

    python probe_boilerplate.py
"""

import json
from pathlib import Path

from scorer import score_record

ROOT = Path(__file__).resolve().parent
SUITES = ROOT / "suites"

# 20 lines of generic review boilerplate. Every line is something a model emits
# about almost any code review, with file="general" so it never matches a real
# bug's file. It knows nothing about the injected bugs; it just talks the talk.
BOILERPLATE = [
    "Ensure all database queries are parameterized to prevent SQL injection.",
    "Validate and sanitize all user input before processing.",
    "Verify authorization and access control on every endpoint.",
    "Avoid hardcoded secrets and credentials in source code.",
    "Do not log sensitive data such as passwords or tokens.",
    "Check for missing authentication on protected routes.",
    "Ensure JWT signatures are properly verified before trusting claims.",
    "Handle errors and exceptions gracefully and fail closed.",
    "Add null checks to avoid null pointer dereferences.",
    "Guard against race conditions in concurrent code paths.",
    "Escape output to prevent cross-site scripting (XSS).",
    "Use constant-time comparison when checking secrets.",
    "Validate object ownership to prevent IDOR / object-level authorization gaps.",
    "Avoid deserializing untrusted data.",
    "Set secure and httpOnly flags on session cookies.",
    "Rate-limit authentication and login endpoints.",
    "Ensure proper input validation to prevent injection attacks.",
    "Review permission checks for privilege escalation.",
    "Avoid weak or predictable cryptographic material and default secrets.",
    "Pin dependencies and check for known vulnerable versions.",
]

# Shape the boilerplate as a runner-style result record: generic findings, no
# file targeting.
BOILERPLATE_RECORD = {
    "reviewer_ai": "boilerplate-probe",
    "writer_ai": "n/a",
    "result": {
        "findings": [
            {"file": "general", "severity": "medium", "issue": line, "suggested_fix": line}
            for line in BOILERPLATE
        ]
    },
}


def _keys():
    for bi in sorted(SUITES.glob("*/bug_index.json")):
        if "_template" in bi.parts:
            continue
        try:
            data = json.loads(bi.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "bugs" not in data or "scoring" not in data:
            continue
        yield bi, data


def _run(gate: int):
    total_bugs = 0
    total_detected = 0
    positive_keys = 0
    for _bi, data in _keys():
        data = json.loads(json.dumps(data))  # deep copy per run
        data["scoring"]["min_hints_without_file"] = gate
        scored = score_record(BOILERPLATE_RECORD, data)
        t = scored["totals"]
        total_bugs += t["bugs_total"]
        total_detected += t["bugs_detected"]
        if t["raw_score"] > 0:
            positive_keys += 1
    pct = round(total_detected / total_bugs * 100, 1) if total_bugs else 0.0
    return total_detected, total_bugs, pct, positive_keys


def main():
    n_keys = sum(1 for _ in _keys())
    print(f"Suites scanned: {n_keys}")
    print("Feeding 20 lines of model-free generic boilerplate to every answer key.\n")

    for label, gate in (("OLD (single-keyword = catch)", 1), ("NEW (file OR 2+ hints)", 2)):
        detected, bugs, pct, pos = _run(gate)
        print(f"{label:32}  detected {detected:4}/{bugs:<4}  =  {pct:5}%   (positive raw score on {pos}/{n_keys} keys)")

    print("\nA model-free reviewer should score near zero. The gate is what makes that true.")


if __name__ == "__main__":
    main()
