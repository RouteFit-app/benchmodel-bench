# Suite: langchain-deser-realbugs (real regressions)

**Status:** `authored, runs pending` — reverses part of **CVE-2025-68664
("LangGrinch", CVSS 9.3)**, the serialization-injection RCE in `langchain-core`.
Separate row from the LangChain path-traversal suite (different file, different
CVE); both group under the **AI Frameworks** tab. No synthetic bugs. The
find was verified to match current `master` exactly once and the reversal compiles
and reproduces the buggy state.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | load.py · _block_jinja2_templates | CVE-2025-68664 (jinja2-block half of the fix) | high* | the guard compares `template_format` against `"jinja"` instead of `"jinja2"`, so the real value never matches and jinja2 templates pass unblocked during deserialization, SSTI/RCE |

\* LangGrinch is rated **CVSS 9.3**; the board's scale tops out at `high`, so it's
weighted at the ceiling, not inflated.

## Why this one (and why a defeated condition, not a deletion)

LangGrinch's fix added several layers (`'lc'`-key escaping, a load-time allowlist,
`secrets_from_env=False`, and a default init-validator that blocks
`template_format='jinja2'`). The jinja2 block is the cleanest single-point,
diff-visible piece: jinja2 templates execute arbitrary code, so removing the block
reopens SSTI. We defeat it by changing the comparison string `"jinja2"` -> `"jinja"`
rather than deleting the `if` block, because a deletion would leave `kwargs`
unused, a lint smell a reviewer might flag as a separate finding (a false
positive against the single answer-key bug). The string-defeat keeps every
variable used and no symbol orphaned, the only defect is that the guard silently
stops matching.

It's a fair, **medium-difficulty** target: the function name
(`_block_jinja2_templates`), its docstring, and its raise message all say
`jinja2`, so a careful reviewer sees the comparison value is wrong and the guard
never fires. Expect this to sit between the saturated visible-sink controls and
the Langflow hidden-sink splitter, weaker reviewers may read the `if` as "still
blocking jinja2" and miss that the string no longer matches.

## Running (from `benchmark/`)

```
# 0. clone langchain (monorepo; sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/langchain-ai/langchain.git langchain-deser-repo
git -C langchain-deser-repo sparse-checkout set libs/core/langchain_core/load

# 1. fresh buggy branch off clean master, then inject (expect 1 applied block)
git -C langchain-deser-repo checkout -b benchmark/real-regression-deser
python apply_bugs.py langchain-deser-repo --bug-index suites/langchain-deser-realbugs/bug_index.json
git -C langchain-deser-repo add -A && git -C langchain-deser-repo commit -m "benchmark langchain deser real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = AI Frameworks)
python runner.py langchain-deser-repo --bug-index suites/langchain-deser-realbugs/bug_index.json \
    --results-dir results-langchain-deser/ --project-id <ai-frameworks-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-langchain-deser/ \
    --bug-index suites/langchain-deser-realbugs/bug_index.json --out-dir results-langchain-deser/scored/
python publish_leaderboard.py --scoreboard results-langchain-deser/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `master` drifted on this line, ping me
and I'll re-anchor.
