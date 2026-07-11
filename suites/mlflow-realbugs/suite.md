# Suite: mlflow-realbugs (real regressions)

**Status:** `authored, runs pending` — extends the AI-framework-CVE track to
**MLflow**, the standard ML lifecycle/experiment-tracking platform. Reverses
**CVE-2026-2033 (High, CVSS 8.1 / ZDI-CAN-26649)**, the artifact-handler path
traversal in the FileStore. No synthetic bugs. The find was verified to match
current `master` exactly once and the reversal compiles and reproduces the buggy
state. Groups under the **AI Frameworks** tab.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | file_store.py · _find_run_root | CVE-2026-2033 (PR #19260, fixed 3.8.0) | high | deletes the run-directory-structure validation, so a `meta.yaml` planted in a run's `artifacts/` folder is treated as a run and its attacker-controlled `artifact_uri` enables path traversal / arbitrary file access |

## The attack the guard stops

`_find_run_root` maps a run id to a directory. The fix only accepts a directory
as a run if it has the real run subdirectories (`metrics/`, `params/`,
`artifacts/`). Without that check, an attacker who can write into a run's
`artifacts/` folder plants a `meta.yaml` with `run_id: artifacts` and an arbitrary
`artifact_uri`, then asks for the run id `artifacts`; the artifacts folder is
accepted as a run, its `artifact_uri` is trusted, and artifact reads/writes land
on arbitrary host paths (CVE-2026-2033, escalating to RCE).

## Why it's a fair-but-medium target

The deleted block is clearly a guard, and the removed comment literally says
"prevent path traversal via malicious meta.yaml in artifact folders
(ZDI-CAN-26649)", a fair tell for a reviewer who reads what protection was
stripped. The work is connecting "removed a run-directory check" to "arbitrary
file access via a planted meta.yaml". The `validate_structure` parameter stays in
the signature, so the `_hard_delete_run` caller still compiles; the only change is
the missing validation.

## Running (from `benchmark/`)

```
# 0. clone mlflow (large; blobless + sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/mlflow/mlflow.git mlflow-repo
git -C mlflow-repo sparse-checkout set mlflow/store

# 1. fresh buggy branch off clean master, then inject (expect 1 applied block)
git -C mlflow-repo checkout -b benchmark/real-regression
python apply_bugs.py mlflow-repo --bug-index suites/mlflow-realbugs/bug_index.json
git -C mlflow-repo add -A && git -C mlflow-repo commit -m "benchmark mlflow real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = AI Frameworks)
python runner.py mlflow-repo --bug-index suites/mlflow-realbugs/bug_index.json \
    --results-dir results-mlflow/ --project-id <ai-frameworks-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-mlflow/ \
    --bug-index suites/mlflow-realbugs/bug_index.json --out-dir results-mlflow/scored/
python publish_leaderboard.py --scoreboard results-mlflow/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `master` drifted on this block, ping me
and I'll re-anchor.
