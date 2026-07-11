# Suite: semantic-kernel-realbugs (real regressions)

**Status:** `authored, runs pending` — the third AI-framework-CVE real-regression
suite (after Starlette and Transformers). Reverses the fix for **CVE-2026-26030
(CVSS 9.8)**, the `eval()`-based RCE in Microsoft Semantic Kernel's Python
`InMemoryVectorStore`. No synthetic bugs. The find was verified to match current
`main` exactly once and the reversal reproduces the buggy state.

## Why this suite (and why NOT the .NET one)

Semantic Kernel shipped two critical CVEs in the "When prompts become shells"
disclosure. We first targeted the .NET **CVE-2026-25592** (a host-side
`DownloadFileAsync` accidentally exposed via `[KernelFunction]`), but that is a
**poor diff-review target**: re-adding `[KernelFunction]` to expose a method is
Semantic Kernel's normal, intended pattern, so from the diff alone it is
indistinguishable from a feature. A trial run confirmed it: every frontier model
read it as a benign tool addition (Claude literally called it "correct and
low-risk"). That's a real methodology insight, tool-registry exposures are
invisible to diff-only review, but it is not a fair model ranking.

The Python **CVE-2026-26030** is the fair test: an `eval()` on a filter string
that can be sourced from untrusted vector-store content is a glaring, diff-visible
code-injection sink. A competent reviewer should flag it on sight.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | in_memory.py · _parse_and_validate_filter | CVE-2026-26030 (fixed in Python 1.39.4) | high* | inserts `return eval(filter_str)` at the top of the safe parser, bypassing the AST allowlist, eval() on an attacker-influenceable filter, RAG-record injection to RCE |

\* Advisory rates it **CVSS 9.8**; the board's scale tops out at `high`, so it's
weighted at the ceiling, not inflated.

## Method

The fix replaced a vulnerable `eval()` of the filter lambda with a restricted AST
evaluator (`_SafeFilterEvaluator`: allowlisted node types, blocked dunder
attributes, name/literal limits). The reversal inserts `return eval(filter_str)`
right after the length check, short-circuiting the whole validation and running
the untrusted filter through `eval()` again. The unreachable safe code remains
below (legal Python), so the branch imports and runs; the defect is the RCE sink.

## Needs a dedicated project

Create a BenchModel project with `tech_stack = "Python / Semantic Kernel"` and
`is_benchmark_project = true`, pass its id as `--project-id`. Groups under a
`Python / Semantic Kernel` tab.

## Running (from `benchmark/`)

```
# 0. clone semantic-kernel (large; blobless keeps it lighter)
git clone --filter=blob:none https://github.com/microsoft/semantic-kernel.git semantic-kernel-repo

# 1. fresh buggy branch off clean main, then inject (expect 1 applied block)
git -C semantic-kernel-repo checkout main && git -C semantic-kernel-repo checkout -b benchmark/real-regression
python apply_bugs.py semantic-kernel-repo --bug-index suites/semantic-kernel-realbugs/bug_index.json
git -C semantic-kernel-repo add -A && git -C semantic-kernel-repo commit -m "benchmark semantic kernel real regression: reintroduced"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py semantic-kernel-repo --bug-index suites/semantic-kernel-realbugs/bug_index.json \
    --results-dir results-semantickernel/ --project-id <sk-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-semantickernel/ \
    --bug-index suites/semantic-kernel-realbugs/bug_index.json --out-dir results-semantickernel/scored/
python publish_leaderboard.py --scoreboard results-semantickernel/scored/scoreboard.json
```

Pinned to `main` as of the clone (`82f2442`). If `apply_bugs` reports a count
mismatch, `main` drifted on this block, ping me and I'll re-anchor.
