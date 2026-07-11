# Suite: transformers-realbugs (real regressions)

**Status:** `authored, runs pending` — the second AI-framework-CVE real-regression
suite (after Starlette). Reverses the fix for **CVE-2026-4372**, the *critical
unauthenticated RCE* in Hugging Face Transformers, the most-used AI/ML library
(2.2B+ installs). No synthetic bugs. The single find was verified to match
current `main` exactly once, and the reversal was applied to a clean checkout to
confirm it reproduces the buggy state.

## Why this suite

This is the most-installed library your audience builds on, and CVE-2026-4372 is
the kind of bug that should terrify them: load a poisoned model with the standard
`from_pretrained()` and you get RCE, no `trust_remote_code=True` required. The
question "would your AI reviewer have caught the config-injection sink before it
shipped?" is about as on-point as the benchmark gets. Groups under a
`Python / Transformers` tab.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | configuration_utils.py · PretrainedConfig.__init__ | PR #44395 (**CVE-2026-4372**, fixed in 5.3.0) | high* | drops the denylist on `_attn_implementation_internal`, untrusted config `setattr` → `importlib.import_module` → unauthenticated RCE on `from_pretrained()` |

\* The advisory rates it **CRITICAL**; the board's scale tops out at `high`, so it's
weighted at the ceiling, not inflated (see `severity_note` in bug_index.json).

## Method

The fix added `if key not in ("_attn_implementation_internal",
"_experts_implementation_internal")` to the leftover-kwargs `setattr` loop in
`PretrainedConfig.__init__`, so a poisoned `config.json` can't set those private
internal attributes (which flow into `importlib.import_module`). Reverting removes
the denylist, the dangerous key is `setattr`'d from untrusted input again.

## Note on scope

Single-bug suite for now. The second half of PR #44395 (gating external kernel
loading behind `trust_remote_code=True` for repos outside `kernels-community`)
lives in a 268 KB `modeling_utils.py` and is multi-line; it can be added as BUG_002
later for a richer suite. The config-injection denylist is the part that is the
actual RCE sink, so it stands alone as the headline.

## Needs a dedicated project

Create a BenchModel project with `tech_stack = "Python / Transformers"` and
`is_benchmark_project = true`, pass its id as `--project-id`. Groups under a
`Python / Transformers` tab.

## Running (from `benchmark/`)

```
# 0. clone transformers (large; blobless keeps it lighter)
git clone --filter=blob:none https://github.com/huggingface/transformers.git transformers-repo

# 1. fresh buggy branch off clean main, then inject (expect 1 applied line-block)
git -C transformers-repo checkout main && git -C transformers-repo checkout -b benchmark/real-regression
python apply_bugs.py transformers-repo --bug-index suites/transformers-realbugs/bug_index.json
git -C transformers-repo add -A && git -C transformers-repo commit -m "benchmark transformers real regression: reintroduced"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py transformers-repo --bug-index suites/transformers-realbugs/bug_index.json \
    --results-dir results-transformers/ --project-id <transformers-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-transformers/ \
    --bug-index suites/transformers-realbugs/bug_index.json --out-dir results-transformers/scored/
python publish_leaderboard.py --scoreboard results-transformers/scored/scoreboard.json
```

Pinned to `main` as of the clone (`c21da1b`). If `apply_bugs` reports a count
mismatch, `main` drifted on this block, ping me and I'll re-anchor.
