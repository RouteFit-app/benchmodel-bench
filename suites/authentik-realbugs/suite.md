# Suite: authentik-realbugs (real regressions)

**Status:** `authored, runs pending` — second entry in the auth-logic /
"hardcoded trust assumption" track (after Gogs), diversifying it to Python and to
an actual identity provider. Reverses **CVE-2025-53942** (GHSA-9g4j-v8w5-7x42),
authentik's OAuth/SAML deactivated-user bypass. No synthetic bugs. The find was
verified to match current `main` exactly once and the reversal compiles and
reproduces the buggy state. Groups under the **Python / Django** tab (authentik is
a Django application).

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | stage.py · do_login | CVE-2025-53942 (PR #15719, fixed 2025.4.4 / 2025.6.4) | medium | deletes `return self.executor.stage_invalid()` from the `if not user.is_active` branch, so the stage warns "login will not work" but logs the deactivated user in anyway |

## Why this is the sharpest "reads intent" test on the board

Most guards, when broken, *look* broken. This one looks **fine**: `do_login`
reads the pending user, checks `if not user.is_active`, and logs a warning that
"login will not work." A reviewer skimming the diff sees an is_active check and a
warning and moves on. But the fix's `return self.executor.stage_invalid()` is
gone, so the branch falls through and the deactivated user is logged in, the
warning is toothless. The catch requires reading what the branch *does* (nothing)
versus what it *appears* to do (block inactive users). It's the GTIG
"dormant logic error that appears functionally correct to traditional scanners but
is strategically broken" in its purest form, the warning literally narrates the
intended behavior the code no longer performs.

## Method

The fixed branch is three lines (check, warning, return). The reversal drops only
the `return`, leaving the check and the now-misleading warning intact, so there's
no missing-symbol or compile tell; the file imports and runs. `stage_invalid()`
still appears once elsewhere (the missing-pending-user guard), so its presence in
the file isn't a hint. Verified find-once against `main`.

## Running (from `benchmark/`)

```
# 0. clone authentik (large; sparse + blobless keeps it light)
git clone --filter=blob:none --sparse https://github.com/goauthentik/authentik.git authentik-repo
git -C authentik-repo sparse-checkout set authentik/stages/user_login

# 1. fresh buggy branch off clean main, then inject (expect 1 applied block)
git -C authentik-repo checkout -b benchmark/real-regression
python apply_bugs.py authentik-repo --bug-index suites/authentik-realbugs/bug_index.json
git -C authentik-repo add -A && git -C authentik-repo commit -m "benchmark authentik real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = Python / Django)
python runner.py authentik-repo --bug-index suites/authentik-realbugs/bug_index.json \
    --results-dir results-authentik/ --project-id <django-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-authentik/ \
    --bug-index suites/authentik-realbugs/bug_index.json --out-dir results-authentik/scored/
python publish_leaderboard.py --scoreboard results-authentik/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `main` drifted on this block, ping me and
I'll re-anchor.
