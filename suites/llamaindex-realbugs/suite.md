# Suite: llamaindex-realbugs (real regressions)

**Status:** `authored + validated, runs pending` — extends the AI-framework-CVE
track to **LlamaIndex**, the most-used RAG/data framework for LLM apps. Reverses
part of the fix for **CVE-2025-1793 (Critical, CVSS 9.8 / CWE-89)**, the SQL
injection across LlamaIndex's vector-store integrations, in the **ClickHouse**
store. No synthetic bugs. The find was verified to match current `main` exactly
once and the reversal compiles and reproduces the buggy state. Groups under the
**AI Frameworks** tab.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | clickhouse/base.py · `_append_meta_filter_condition` | CVE-2025-1793 (PR #18316, commit 201d3f540, fixed 0.12.28) | high | drops `escape_str()` on the metadata-filter key/value, so a query-time filter value is interpolated raw into a `JSONExtractString(...) = '...'` SQL fragment, reopening SQL injection |

## The attack the escaping stops

`_append_meta_filter_condition` builds the `WHERE` clause for metadata filters by
formatting each filter into:

```
JSONExtractString(<metadata_column>, '<key>') = '<value>'
```

The `key`/`value` come from the caller's `MetadataFilters` (query time). In any
app that lets users search with their own filters, those are attacker-influenced.
The fix wrapped both in `escape_str()`; without it a value such as
`' OR 1=1 --` closes the quoted string literal and injects arbitrary SQL into the
generated query — the CWE-89 SQL injection the advisory describes, allowing
unauthorized read/write of the backing store.

## Why it's a fair-but-medium target

This is an **asymmetry**, not a deleted line a reviewer can spot by absence:
`escape_str` is defined in this same file and applied on **nine** other paths
(text search, hybrid search, list/value escaping). Only this one metadata-filter
path stops using it. The work is noticing that user-controlled `filter_item.key`
/ `filter_item.value` reach a SQL string with no parameterization or escaping,
while every sibling method escapes — and naming SQL injection, not a generic
"unsanitized input." The misleading `# Use JSONExtractString function with
properly escaped keys and values` comment added by the fix is removed in the
reversal (faithful to the pre-fix state), so there's no comment tell.

## Running (from `benchmark/`)

```
# 0. clone llama_index (large; blobless + sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/run-llama/llama_index.git llama_index-repo
git -C llama_index-repo sparse-checkout set \
    llama-index-integrations/vector_stores/llama-index-vector-stores-clickhouse

# 1. fresh buggy branch off clean main, then inject (expect 1 applied block)
git -C llama_index-repo checkout -b benchmark/real-regression
python apply_bugs.py llama_index-repo --bug-index suites/llamaindex-realbugs/bug_index.json
git -C llama_index-repo add -A && git -C llama_index-repo commit -m "benchmark llamaindex real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = AI Frameworks)
python runner.py llama_index-repo --bug-index suites/llamaindex-realbugs/bug_index.json \
    --results-dir results-llamaindex/ --project-id <ai-frameworks-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-llamaindex/ \
    --bug-index suites/llamaindex-realbugs/bug_index.json --out-dir results-llamaindex/scored/
python publish_leaderboard.py --scoreboard results-llamaindex/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `main` drifted on this block, ping me
and I'll re-anchor.
