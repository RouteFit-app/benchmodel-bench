# Suite: distractor-rac (review under noise)

**Status:** `authored + validated, runs pending` — a **new axis** the board
didn't have: *review under noise*. Does a reviewer still catch a real,
high-severity bug when it's bundled with a plausible-looking but **benign**
"cleanup" change? Built on **authentik**, reusing the RAC session-hijack
(CVE-2025-52553) as the one real bug. Groups under the **Python / Django** tab.

## What's in the diff

| Kind | File · func | What it is | Scored? |
| ---- | ----------- | ---------- | ------- |
| **Real bug** (BUG_001) | `rac/views.py` · `RACInterface.dispatch` | Reverses CVE-2025-52553: drops `session__session__session_key=...` from the `ConnectionToken` lookup, so a token is matched by value alone → cross-session token reuse / session hijack into remote desktop. **High.** | **Yes** — detection of this is the only thing scored |
| **Distractor** (DISTRACTOR_001) | `rac/views.py` · `RACFinalStage.dispatch` | Removes an `if all_tokens.filter(...).exists(): msg.append(...)` block. Looks like dropping an access check; actually only deletes a cosmetic *"(You are already connected in another tab/window)"* message. The connection is still rejected via `stage_invalid` either way. **Benign.** | **No** — a finding on it is scored **neutral**, never a false positive |

The `writer_summary` frames the whole thing as routine maintenance, so both
changes read as "tidying up redundant checks."

## Why this measures something new

Every other suite scores one diff. This one asks whether a *second, guard-shaped
removal* changes the reviewer's behavior on the first. We saw this happen by
accident: when the RAC bug was once run on a contaminated branch that also
carried a second security-relevant removal, GPT-4o and DeepSeek pattern-matched
the whole thing as "routine cleanup, removing redundant checks" and endorsed
**both** changes (rating the diff 8.5/10), where on the clean single-change diff
they caught the RAC bug more often. This suite turns that accident into a
controlled test.

- **Detection of BUG_001** is the headline metric. Compare it to the model's
  catch rate on the standalone `authentik-rac-realbugs` suite (same bug, no
  distractor). A drop = the **rubber-stamp / dilution effect**.
- The distractor is **never scored**. `scorer.py` matches a finding to the
  distractor by keyword and marks it neutral, so a cautious reviewer who flags
  the benign change is not penalized. This keeps the signal clean: the only
  question is whether the *real* bug survived the noise.
- `distractor_flag_count` is reported per run for visibility (how many reviewers
  bit on the cosmetic change), but it does not affect the score.

## Fairness notes

- The distractor is **benign by construction** (documented in
  `bug_index.json → distractors[].why_benign`): it removes only a user-facing
  message, with no change to any access decision or control flow. A human can
  verify this from the diff.
- The real bug's answer key, severity (high), and detection hints are identical
  to the standalone RAC suite, so the two are directly comparable.

## Running (from `benchmark/`)

```
# 0. clone authentik (large; blobless + sparse keeps it light)
git clone --filter=blob:none --sparse https://github.com/goauthentik/authentik.git authentik-repo
git -C authentik-repo sparse-checkout set authentik/providers/rac

# 1. fresh buggy branch off clean main, then inject (expect 1 bug + 1 distractor)
git -C authentik-repo checkout -b benchmark/distractor-rac
python apply_bugs.py authentik-repo --bug-index suites/distractor-rac/bug_index.json
git -C authentik-repo add -A && git -C authentik-repo commit -m "benchmark distractor-rac: real bug + benign distractor"

# 2. run n=3 / score / publish (project tech_stack = Python / Django)
python runner.py authentik-repo --bug-index suites/distractor-rac/bug_index.json \
    --results-dir results-distractor-rac/ --project-id <python-django-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-distractor-rac/ \
    --bug-index suites/distractor-rac/bug_index.json --out-dir results-distractor-rac/scored/
python publish_leaderboard.py --scoreboard results-distractor-rac/scored/scoreboard.json
```

`apply_bugs.py` applies `bugs[]` then `distractors[]`; expect one applied bug and
one applied distractor. If a count mismatch is reported, `main` drifted on that
block, re-anchor before running.
