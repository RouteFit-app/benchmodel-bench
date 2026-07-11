# Suite: gogs-realbugs (real regressions)

**Status:** `authored, runs pending` — the auth-logic / "hardcoded trust
assumption" track that Google's GTIG AI Threat Tracker (May 2026) flagged as the
highest-signal bug class for LLM reviewers. Reverses **CVE-2025-64175 (High)**,
the 2FA-bypass-via-recovery-code in Gogs, itself discovered by OpenAI using GPT-5.
No synthetic bugs. The find was verified to match current `main` exactly once and
the reversal reproduces the buggy state. Groups under the **Go** tab (alongside
the Gin suite).

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | two_factors.go · UseRecoveryCode | CVE-2025-64175 (fixed in Gogs 0.13.4) | high | drops the `user_id = ?` constraint from the recovery-code lookup, so any unused recovery code clears any victim's 2FA, cross-account bypass / account takeover |

## Why this is the GTIG class

GTIG's standout finding was an AI-discovered 2FA bypass that stemmed "not from
common implementation errors like memory corruption or improper input
sanitization, but a high-level semantic logic flaw where the developer hardcoded a
trust assumption." This is exactly that: the fixed code scopes the recovery-code
query to the authenticating user; the regression removes the user scope so the
lookup matches *any* user's unused code. The function still **accepts** `userID`,
it just no longer **uses** it, the dormant logic error that "appears functionally
correct to traditional scanners but is strategically broken from a security
perspective." A diff-only reviewer sees a `WHERE` clause lose `user_id = ?`; the
test is whether the model connects that to a cross-account 2FA bypass, or waves it
through as a harmless query simplification.

## Method

The fixed query is `tx.Where("user_id = ? AND code = ? AND is_used = ?", userID,
code, false)`. The reversal is `tx.Where("code = ? AND is_used = ?", code, false)`.
`userID` remains in the function signature (Go permits unused parameters), so the
code still compiles, and the now-unused `userID` is the tell a sharp reviewer
catches. Verified find-once against `main`.

## Running (from `benchmark/`)

```
# 0. clone gogs (sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/gogs/gogs.git gogs-repo
git -C gogs-repo sparse-checkout set internal/database

# 1. fresh buggy branch off clean main, then inject (expect 1 applied block)
git -C gogs-repo checkout -b benchmark/real-regression
python apply_bugs.py gogs-repo --bug-index suites/gogs-realbugs/bug_index.json
git -C gogs-repo add -A && git -C gogs-repo commit -m "benchmark gogs real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = Go)
python runner.py gogs-repo --bug-index suites/gogs-realbugs/bug_index.json \
    --results-dir results-gogs/ --project-id <go-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-gogs/ \
    --bug-index suites/gogs-realbugs/bug_index.json --out-dir results-gogs/scored/
python publish_leaderboard.py --scoreboard results-gogs/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `main` drifted on this line, ping me and
I'll re-anchor.
