# Suite: litellm-realbugs (real regressions)

**Status:** `authored + validated, runs pending` — extends the AI-framework-CVE
track to **LiteLLM** (BerriAI, 44k+ stars), the AI gateway most production stacks
put in front of their models. Reverses the fix for the LiteLLM Proxy
**API-key-verification SQL injection (GHSA-r75f-5x8p-qvmc, Critical CVSS 9.3 /
CWE-89)**. No synthetic bugs. The find was verified to match current `main`
exactly once and the reversal compiles and reproduces the buggy state. Groups
under the **AI Frameworks** tab.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | proxy/utils.py · `PrismaClient` combined_view token lookup | GHSA-r75f-5x8p-qvmc (commit 4dc416ee74, fixed v1.83.7) | high | restores the f-string that interpolates the raw caller-supplied `token` into `WHERE v.token = '{token}'` and removes the bound `$1` parameter, reopening SQL injection in the key-verification path |

## The attack the parameter binding stops

LiteLLM Proxy verifies every request by checking the `Authorization: Bearer`
key. Inside `PrismaClient`, the `combined_view` branch builds a SQL string to
look the token up across the verification/team/org/budget tables and runs it via
`_query_first_with_cached_plan_fallback`. The fix binds the value:

```python
sql_query = """ ... WHERE v.token = $1 """
response = await self._query_first_with_cached_plan_fallback(sql_query, hashed_token)
```

The regression reverts it to the vulnerable form — an f-string that drops the
raw caller-supplied `token` straight into the query text:

```python
sql_query = f""" ... WHERE v.token = '{token}' """
response = await self._query_first_with_cached_plan_fallback(sql_query)
```

An unauthenticated attacker sends a crafted `Authorization: Bearer` value that
closes the quoted literal and injects arbitrary SQL; per the advisory the query
is reachable through the proxy's error-handling path, allowing read/modify of the
proxy's own database — the API keys, budgets, and spend it manages.

## Why it's a fair-but-medium target

The sink is **disguised**, which is the point. The injected value flows from an
auth header through a key-verification helper, not an obvious `request.args`
input, and a sibling variable named `hashed_token` sits right beside it — so a
shallow read assumes "it's hashed, it's safe." The catch requires noticing that
the **raw** `token` (not the hash) is interpolated via an f-string where the
fixed code used a bound parameter (`$1`). The diff the reviewer sees is three
lines: the `f` prefix returns, `$1` becomes `'{token}'`, and the parameter
argument is removed.

## Running (from `benchmark/`)

```
# 0. clone litellm (large; blobless keeps it light)
# NOTE: LiteLLM's default branch is `litellm_internal_staging`, NOT `main`, so
# bug_index.json sets base_branch accordingly. The clone checks that branch out.
git clone --filter=blob:none https://github.com/BerriAI/litellm.git litellm-repo

# 1. fresh buggy branch off the default (litellm_internal_staging), then inject
git -C litellm-repo checkout -b benchmark/real-regression
python apply_bugs.py litellm-repo --bug-index suites/litellm-realbugs/bug_index.json
git -C litellm-repo add -A && git -C litellm-repo commit -m "benchmark litellm real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = AI Frameworks)
python runner.py litellm-repo --bug-index suites/litellm-realbugs/bug_index.json \
    --results-dir results-litellm/ --project-id <ai-frameworks-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-litellm/ \
    --bug-index suites/litellm-realbugs/bug_index.json --out-dir results-litellm/scored/
python publish_leaderboard.py --scoreboard results-litellm/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `main` drifted on this block, ping me
and I'll re-anchor.
