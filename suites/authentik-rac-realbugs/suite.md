# Suite: authentik-rac-realbugs (real regressions)

**Status:** `authored, runs pending` — the *hard* auth-logic bug, designed to
separate the field where the deactivated-user check (CVE-2025-53942) saturated.
Reverses **CVE-2025-52553**, authentik's RAC connection-token session hijack. No
synthetic bugs. The find was verified to match current `main` exactly once and the
reversal compiles and reproduces the buggy state. Groups under **Python / Django**.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | views.py · RACInterface.dispatch | CVE-2025-52553 (PR #15289, fixed 2025.4.3 / 2025.6.3) | medium | drops `session__session__session_key=request.session.session_key` from the connection-token lookup, so the token is matched by value alone and anyone with the URL can hijack the remote session |

## Why this one should split where the last one saturated

The deactivated-user bug deleted a `return` and the field caught it every time:
once a guard is visibly gutted, models spot it. This bug is different, **nothing
looks missing**. The token lookup still filters by token, which reads exactly like
proper validation. The only change is that the query no longer also constrains on
the requesting session. Catching it requires a conceptual leap the diff doesn't
hand you: a connection token that rides in the URL must be bound to the session
that authorized it, or possession of the URL equals access (the screenshare attack
in the advisory). A reviewer reading the line sees "look up the token", fine; a
reviewer reading intent sees "the token is no longer tied to a session", session
hijack. That gap, between reading the line and reading the system, is where we
expect the models to separate.

## Method

The reversal restores the exact pre-fix one-liner (token-only filter). No symbol is
orphaned and the module compiles; the defect is purely the absent session
constraint. We reverse the HTTP dispatch path (`views.py`); the websocket consumer
carries the same fix but one clean entry point is enough for a single-bug suite.
Verified find-once against `main`.

## Running (from `benchmark/`)

```
# 0. clone authentik (large; sparse + blobless keeps it light)
git clone --filter=blob:none --sparse https://github.com/goauthentik/authentik.git authentik-rac-repo
git -C authentik-rac-repo sparse-checkout set authentik/providers/rac

# 1. fresh buggy branch off clean main, then inject (expect 1 applied block)
git -C authentik-rac-repo checkout -b benchmark/real-regression-rac
python apply_bugs.py authentik-rac-repo --bug-index suites/authentik-rac-realbugs/bug_index.json
git -C authentik-rac-repo add -A && git -C authentik-rac-repo commit -m "benchmark authentik RAC real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = Python / Django)
python runner.py authentik-rac-repo --bug-index suites/authentik-rac-realbugs/bug_index.json \
    --results-dir results-authentik-rac/ --project-id <django-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-authentik-rac/ \
    --bug-index suites/authentik-rac-realbugs/bug_index.json --out-dir results-authentik-rac/scored/
python publish_leaderboard.py --scoreboard results-authentik-rac/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `main` drifted on this block, ping me and
I'll re-anchor.
