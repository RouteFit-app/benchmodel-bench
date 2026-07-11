# Suite: react-frontend

**Status:** `live` — bugs authored 1:1 against the React/TypeScript frontend of
`RouteFit-app/benchmodel-fastapi-template` (the same fork the FastAPI suite uses
— "two stacks for one fork"). All 10 injections verified to match their target
source exactly once against clean `master`.

## Why this suite

Third independent stack, added to test whether the v2 reviewer ranking
(DeepSeek > Claude > Gemini > GPT) **repeats** across stacks. One stack
separating the models is a result; the same order holding across Kotlin,
Python, and now React/TS is a much stronger claim. This suite deliberately
leans on React-specific failure modes a backend-only benchmark can't surface:
React Query cache invalidation, a missing `await`, a `useEffect` dependency
array, zod client validation, and render-time pagination math.

## Target

- **Repo:** https://github.com/RouteFit-app/benchmodel-fastapi-template
- **Code under test:** `frontend/` only (React 18 + Vite + TypeScript, TanStack
  Query + Router, react-hook-form + zod, shadcn/ui).
- **base_branch:** `master`
- **buggy_branch:** `benchmark/buggy-react` (its own branch so it never clashes
  with the Python suite's `benchmark/buggy` / `benchmark/buggy-v2`).

## Bug set (v1 — 10 bugs)

Severity 4 high / 4 medium / 2 low. Difficulty 7 hard / 3 medium (hard-leaning
on purpose — this is meant to separate, not to be passed 10/10 by everyone).

| ID | File | Category | Sev | Diff | What's wrong |
| -- | ---- | -------- | --- | ---- | ------------ |
| BUG_001 | Items/AddItem.tsx | stale_cache | high | medium | invalidates `["users"]` instead of `["items"]` — new item never appears |
| BUG_002 | hooks/useAuth.ts | missing_await | high | hard | `await` dropped on `loginAccessToken` — `access_token` is undefined, login silently fails |
| BUG_003 | hooks/useAuth.ts | broken_conditional | high | hard | currentUser query `enabled: !isLoggedIn()` — user data fetched only when logged out |
| BUG_004 | theme-provider.tsx | stale_closure | medium | hard | `theme` removed from `useEffect` deps — theme switch never re-applies DOM class |
| BUG_005 | UserSettings/ChangePassword.tsx | validation_gap | medium | hard | zod `.refine()` password-match check removed |
| BUG_006 | Common/DataTable.tsx | off_by_one | low | medium | `+ 1` dropped from "Showing X to Y" 0-based start |
| BUG_007 | UserSettings/UserInformation.tsx | inverted_conditional | medium | medium | Save `disabled` inverted — can't submit edits |
| BUG_008 | Admin/EditUser.tsx | data_loss | high | hard | empty-password guard inverted — drops a set password / sends empty one |
| BUG_009 | routes/_layout/items.tsx | incomplete_fetch | medium | hard | items query `limit` cut 100 → 10 |
| BUG_010 | Admin/AddUser.tsx | stale_state | low | hard | `form.reset()` removed — dialog reopens pre-filled |

Two are security-relevant (BUG_003 auth gating, BUG_008 password handling).

**v1 result (run 2026-06-19): saturated.** All four reviewers (gpt-4o,
gemini-2.5-pro, claude-sonnet-4-6, deepseek-chat) detected **10/10** with 0 false
positives; the only separation was severity accuracy (gemini 5, claude/deepseek
4, gpt 3). Conclusion: these bugs are within every frontline model's competence
in a small focused diff — a useful *floor* result, but it doesn't rank. Hence v2.

## Bug set (v2 — 8 bugs, `bug_index.v2.json`)

Same `benchmark_name`, `version: 2`, branch `benchmark/buggy-react-v2`. These are
deliberately **hard to detect**: each changed line reads as plausible code and
only breaks under cross-render / cache-matching / cleanup / null-vs-undefined
reasoning. 3 high / 3 medium / 2 low; 7 hard / 1 medium.

| ID | File | Category | Sev | What's subtle |
| -- | ---- | -------- | --- | ------------- |
| BUG_001 | hooks/useAuth.ts | broken_auth | high | `isLoggedIn` compares to `undefined` not `null` — getItem never returns undefined, so it's always true |
| BUG_002 | Items/EditItem.tsx | stale_cache | medium | invalidates `["items", item.id]` — too specific; list keyed `["items"]` is never matched |
| BUG_003 | UserSettings/UserInformation.tsx | inverted_logic | high | changed-field guard flipped `!==`→`===` — edits silently dropped |
| BUG_004 | hooks/useMobile.ts | resource_leak | medium | effect cleanup `removeEventListener` removed — listener leak, works in normal use |
| BUG_005 | theme-provider.tsx | resource_leak | low | media-query listener cleanup removed; effect re-runs per theme change → leak |
| BUG_006 | Common/DataTable.tsx | off_by_one | low | `Math.min(..., data.length)` clamp removed — "to" overshoots on last page |
| BUG_007 | Admin/EditUser.tsx | validation_logic | medium | refine `\|\|`→`&&` — schema can never pass once a password is typed |
| BUG_008 | Items/AddItem.tsx | error_handling | high | `onError` bound to `showSuccessToast` — failures show a green success toast |

Verified 8/8 against clean `master` blobs (`git show master:<path>`). Note: the
working tree may be sitting on a buggy branch — always cut v2 from clean
`master`, not from `benchmark/buggy-react`.

Run it the same way as v1 but with the v2 index, branch, and a separate results
dir:

```
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/buggy-react-v2
python apply_bugs.py <fork> --bug-index suites/react-frontend/bug_index.v2.json   # expect 8 applied
git -C <fork> add -A && git -C <fork> commit -m "benchmark react v2: subtle bug set"
python runner.py <fork> --bug-index suites/react-frontend/bug_index.v2.json \
    --results-dir results-react-v2/ --project-id <react-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-react-v2/ --bug-index suites/react-frontend/bug_index.v2.json \
    --out-dir results-react-v2/scored/
python publish_leaderboard.py --scoreboard results-react-v2/scored/scoreboard.json
```

**v2 result (run 2026-06-19): separated the laggard, not the leaders.** Claude,
Gemini, and DeepSeek all detected **8/8** (weighted 96.9 / 95.3 / 92.2); GPT-4o
detected **6/8** with 2 duplicate findings and severity accuracy **1/6**
(weighted 72.2). GPT missed exactly the two bugs needing cross-mechanism
reasoning -- BUG_002 (React Query invalidation matches by key *prefix*, so the
narrowed `["items", item.id]` key never clears the list) and BUG_006 (the removed
`Math.min` clamp that only overshoots on the last page) -- and rated the
high-severity always-logged-in auth bypass (BUG_001) as `low`.

Takeaway: even the subtle v2 set is within the top models' detection range, so
React **ranks the laggard but not the front-runners** -- this template's frontend
lacks the cross-file/architectural depth needed to separate the leaders. It does,
however, replicate the cross-stack signal (RouteFit v2 + FastAPI v2 + React v2):
**GPT-4o is the weakest reviewer and the worst at severity calibration.** To rank
the leaders, a deeper stack (Spring, or a larger multi-module app) is needed.

## Needs a dedicated project

Runs are tagged with the **project's** `tech_stack`, not this suite's. Create a
BenchModel project with `tech_stack = "React / Frontend"` and
`is_benchmark_project = true`, and pass its id as `--project-id`. Without it the
runs inherit whatever project you point at and get mis-tagged on the
leaderboard. (`"React / Frontend"` is already in the tech-stack dropdown under
the JavaScript / TypeScript group.)

## Running this suite (from `benchmark/`)

```
# 1. fresh buggy branch off clean master, then inject
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/buggy-react
python apply_bugs.py <fork> --bug-index suites/react-frontend/bug_index.json
#    expect 10 "applied BUG_00X" lines

# 2. commit (local diff is what the runner reads; push is optional)
git -C <fork> add -A && git -C <fork> commit -m "benchmark react v1: injected bugs"
#    if a pre-push review hook blocks you: git push --no-verify  (benchmark branch)

# 3. run / score / publish — own results dir so it never grades against another suite
python runner.py <fork> --bug-index suites/react-frontend/bug_index.json \
    --results-dir results-react/ --project-id <react-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-react/ --bug-index suites/react-frontend/bug_index.json \
    --out-dir results-react/scored/
python publish_leaderboard.py --scoreboard results-react/scored/scoreboard.json
```

`<fork>` = the local checkout of `benchmodel-fastapi-template`
(`C:\Users\sahlu\AndroidStudioProjects\benchmodel-fastapi-template`).
