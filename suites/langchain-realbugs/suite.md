# Suite: langchain-realbugs (real regressions)

**Status:** `authored, runs pending` — extends the AI-framework-CVE track to the
most-installed AI framework. Reverses the fix for **CVE-2026-34070 (HIGH)**, the
path-traversal in `langchain-core`'s legacy `load_prompt` loaders. No synthetic
bugs. The find was verified to match current `master` exactly once and the
reversal reproduces the buggy state. Groups under the **AI Frameworks**
tab.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | loading.py · _load_template | CVE-2026-34070 (fixed in langchain-core 1.2.22) | high | deletes the `_validate_path(template_path)` guard, so a path from a user-influenced prompt config flows straight into `.resolve()` / `.read_text()`, arbitrary host-file read |

## Why it's a fair diff-review target

The fix (commit `27add91`) added `_validate_path()`, which rejects absolute paths
and `..` components before any file is opened. The reversal deletes that call from
the primary template-loading path. In the diff the reviewer sees a path-traversal
guard removed immediately before a file `.resolve()` + `.read_text()`, a textbook
CWE-22 arbitrary-file-read. Same shape as the Starlette StaticFiles bug, and a
clean separator: a competent reviewer flags it; a weak one waves it through.

## Method

`_validate_path` stays referenced at the `_load_examples` call site (and in the
function def), so removing the template-side call leaves no orphaned/unused-symbol
tell, the only change is the missing guard. Verified find-once against `master`.

## Running (from `benchmark/`)

```
# 0. clone langchain (monorepo; sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/langchain-ai/langchain.git langchain-repo
git -C langchain-repo sparse-checkout set libs/core/langchain_core/prompts

# 1. fresh buggy branch off clean master, then inject (expect 1 applied block)
git -C langchain-repo checkout -b benchmark/real-regression
python apply_bugs.py langchain-repo --bug-index suites/langchain-realbugs/bug_index.json
git -C langchain-repo add -A && git -C langchain-repo commit -m "benchmark langchain real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = AI Frameworks)
python runner.py langchain-repo --bug-index suites/langchain-realbugs/bug_index.json \
    --results-dir results-langchain/ --project-id <ai-frameworks-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-langchain/ \
    --bug-index suites/langchain-realbugs/bug_index.json --out-dir results-langchain/scored/
python publish_leaderboard.py --scoreboard results-langchain/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `master` drifted on this block, ping me
and I'll re-anchor.
