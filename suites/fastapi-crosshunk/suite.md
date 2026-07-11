# Suite: fastapi-crosshunk (cross-hunk experiment)

**Status:** `authored, runs pending` — an experiment to test one hypothesis:
does a **cross-hunk** bug design separate the leaders where single-line bugs
saturate? 4 bugs / 2 coordinated pairs, injected into clean upstream
`fastapi/full-stack-fastapi-template` (master @ `248d7d1`). All 4 finds verified
to match exactly once.

## The idea

Single-line hard bugs saturated detection on FastAPI (every frontier model
caught all 6). The untested lever: **defense-in-depth removals split across two
files.** Each removal, read alone, looks like reasonable de-duplication ("this
check is redundant, the other layer handles it"); only by connecting BOTH hunks
do you see the protection is gone entirely. The bet is that pattern-matchers
rationalize each hunk and miss both, while models that reason across the diff
catch the pair, producing detection-level separation.

## The two pairs

**Pair 1 — `is_active` enforcement (high).** `get_current_user` (deps.py) and
`login_access_token` (login.py) both reject inactive users (defense in depth).
BUG_001 removes the deps copy, BUG_002 removes the login copy. Either alone is
"redundant"; together, account deactivation is fully bypassed (disabled users
log in and keep using tokens).

**Pair 2 — email uniqueness (medium).** The DB `email` column is `unique=True`
AND `create_user` does a pre-check. BUG_003 drops `unique=True` (looks like the
app still guards it); BUG_004 drops the route pre-check (looks like the DB still
guards it). Together, duplicate-email accounts become possible.

| ID | File | Pair | Sev | Alone it looks like... |
| -- | ---- | ---- | --- | ---------------------- |
| BUG_001 | deps.py | 1 (is_active) | high | removing a redundant check (login still has it) |
| BUG_002 | login.py | 1 (is_active) | high | removing a redundant check (deps still has it) |
| BUG_003 | models.py | 2 (email unique) | medium | a minor schema tweak (route still pre-checks) |
| BUG_004 | users.py | 2 (email unique) | medium | trusting the DB unique constraint |

## Result (n=1) — saturated, but it caught a scoring bias

Cross-hunk did NOT separate the models on reasoning. Once scored fairly, all four
detect both pairs. The first scoring pass *looked* like a huge split (Gemini 37%
vs ~95%), but that was a scorer artifact: Gemini wrote the best review, it
consolidated each pair into ONE root-cause finding naming both files (correct
senior-reviewer behavior), and the per-bug scorer counted one finding as catching
one bug, scoring the consolidation as a half-miss on every pair.

Fix: bugs now carry a `pair_id`, and `scorer.py` was made pair-aware, if one
finding detects a bug in a pair and also satisfies the partner bug's hints,
credit both (and grant file credit when the finding names the file in prose).
Gated to bugs with a `pair_id`, so no other suite is re-scored. That put Gemini
back at the top with everyone else.

Takeaways:
1. The real yield was **finding and fixing a scoring bias** that had been quietly
   penalizing good consolidated reviews on every suite.
2. This four-model set does not separate on FastAPI by any design tried
   (single-line, hard-to-see, or cross-hunk). **Spring Hard Mode's separation
   came from a genuinely ambiguous framework corner and remains the exception.**

Tagged `Python / FastAPI`, groups under that tab as its own benchmark family.

## Running (from `benchmark/`)

```
git clone https://github.com/fastapi/full-stack-fastapi-template.git <fork>   # if not already cloned
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/crosshunk-fastapi
python apply_bugs.py <fork> --bug-index suites/fastapi-crosshunk/bug_index.json   # expect 4 applied
git -C <fork> add -A && git -C <fork> commit -m "benchmark fastapi crosshunk: injected pairs"

python runner.py <fork> --bug-index suites/fastapi-crosshunk/bug_index.json \
    --results-dir results-fastapi-xh/ --project-id <fastapi-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-fastapi-xh/ \
    --bug-index suites/fastapi-crosshunk/bug_index.json --out-dir results-fastapi-xh/scored/
python publish_leaderboard.py --scoreboard results-fastapi-xh/scored/scoreboard.json
```
