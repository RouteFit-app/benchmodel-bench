# Suite: langflow-realbugs (real regressions)

**Status:** `authored, runs pending` — reverses **CVE-2025-3248 (CVSS 9.8)**, the
unauthenticated RCE in Langflow's `/api/v1/validate/code` endpoint (actively
exploited in the wild by the Flodrix botnet). No synthetic bugs. The find was
verified to match current `main` exactly once and the reversal reproduces the
buggy state. Groups under the **AI Frameworks** tab.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | validate.py · post_validate_code | CVE-2025-3248 (fixed in Langflow 1.3.0) | high* | deletes `dependencies=[Depends(get_current_active_user)]` from POST /validate/code, so an anonymous caller reaches `validate_code()`, which `exec()`s the body, unauth RCE |

\* Advisory rates it **CVSS 9.8**; the board's scale tops out at `high`, so it's
weighted at the ceiling, not inflated.

## Why this one is interesting (not just another control)

Unlike the eval() and path-traversal suites, the dangerous sink is **not in the
diff**. The diff shows only the auth dependency being removed from the route
decorator. To rate it correctly the reviewer has to know that `post_validate_code`
feeds the body to `validate_code()`, which `exec()`s it (and that Python evaluates
decorator expressions at parse time, so `@exec("...")` fires on submission). A
reviewer that says "you removed an auth check" gets a partial catch; the real
severity is unauthenticated RCE. The sibling `/validate/prompt` endpoint **keeps**
its auth dependency, so the diff is a selective strip on the one route that
reaches code execution, a good test of whether the model reads endpoint intent,
not just the line that changed.

## Method

After removing the `/code` dependency, `get_current_active_user` and `Depends`
remain referenced by `/prompt`, so there's no orphaned-import tell, the only
change is the missing auth on the exec route. Verified find-once against `main`.

## Running (from `benchmark/`)

```
# 0. clone langflow (monorepo; sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/langflow-ai/langflow.git langflow-repo
git -C langflow-repo sparse-checkout set src/backend/base/langflow/api/v1

# 1. fresh buggy branch off clean main, then inject (expect 1 applied block)
git -C langflow-repo checkout -b benchmark/real-regression
python apply_bugs.py langflow-repo --bug-index suites/langflow-realbugs/bug_index.json
git -C langflow-repo add -A && git -C langflow-repo commit -m "benchmark langflow real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = AI Frameworks)
python runner.py langflow-repo --bug-index suites/langflow-realbugs/bug_index.json \
    --results-dir results-langflow/ --project-id <ai-frameworks-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-langflow/ \
    --bug-index suites/langflow-realbugs/bug_index.json --out-dir results-langflow/scored/
python publish_leaderboard.py --scoreboard results-langflow/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `main` drifted on this line, ping me and
I'll re-anchor.
