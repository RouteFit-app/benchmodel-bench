# Suite: fastapi-hardmode (Hard Mode, FastAPI)

**Status:** `authored, runs pending` — 6 blended security + correctness +
framework-semantics bugs injected 1:1 into a **fresh upstream clone** of
`fastapi/full-stack-fastapi-template`. All 6 verified to match exactly once
against clean `master` (commit `248d7d1`), each a clean one-line diff.

## Why a fresh upstream clone (important)

This suite does NOT use the local `benchmodel-fastapi-template`. That fork's
`master` already contains several baked-in vulnerabilities (an inverted
`read_item` ownership check, access tokens minted without an `exp`, the
non-superuser item list returning all users' rows, a password-update path that
ignores the verify result). Those would land in the diff context and cause good
reviewers to be penalized for flagging real bugs that aren't in this suite's
answer key. Authoring against the clean upstream avoids that contamination.

Same `tech_stack` (`Python / FastAPI`) as the existing FastAPI suites, so it
groups as a new benchmark family under that tab.

## Why Hard Mode here

The Spring Hard Mode flagship proved the thesis: signature-matchable vulns
saturate the leaders; it's the **framework-scope subtlety** that ranks them
(there, which fields a Spring `WebDataBinder` blocks). This suite aims the same
seam at FastAPI/SQLModel: which fields a `response_model` actually serializes,
what `exclude_unset` dumps, how an FK `ondelete` interacts with `nullable`, and
the auth lifecycle. The bugs are chosen to be hard to *see*, not just hard to
rate: BUG_001 (a `response_model` swapped from `UserPublic` to `User`) only reads
as a vuln if you know `User` carries `hashed_password`, a fact that lives in
models.py, not in the changed line.

(An earlier draft used a `UserUpdateMe`->`UserUpdate` privilege-escalation and a
reset-password enumeration bug; both saturated detection, every model caught
them, so they were swapped for the response-model leak and a token-TTL unit bug
that require more cross-file/semantic reasoning to spot.)

## Target

- **Repo:** https://github.com/fastapi/full-stack-fastapi-template (clone fresh)
- **base_branch:** `master`
- **buggy_branch:** `benchmark/hardmode-fastapi`
- Python, 4-space indent, one bug per file across 6 files.

## Bug set (6 bugs)

2 high / 4 medium, all `hard`. 4 security, 2 correctness/framework.

| ID | File | Category | Sev | What's hard about it |
| -- | ---- | -------- | --- | -------------------- |
| BUG_001 | users.py | sensitive_data_exposure | high | `/users/me` `response_model` `UserPublic` -> `User`, serializes the caller's `hashed_password` (leak depends on models.py) |
| BUG_002 | deps.py | broken_access_control | high | `is_active` check removed from `get_current_user`, deactivation becomes a no-op |
| BUG_003 | crud.py | broken_authentication | medium | `sqlmodel_update(user_data, update=extra_data)` -> drops `update=`, password change silently no-ops |
| BUG_004 | models.py | data_integrity | medium | FK `ondelete` `CASCADE` -> `SET NULL` while `nullable=False`, user-delete integrity error |
| BUG_005 | items.py | data_loss | medium | `model_dump(exclude_unset=True)` -> `False`, partial update nulls unsent fields |
| BUG_006 | login.py | broken_authentication | medium | access-token TTL `timedelta(minutes=...)` -> `days`, tokens effectively never expire |

Verified with `apply_bugs.py` (each find matches exactly once; mismatch aborts).
No v2, Hard Mode is the hard set.

## Needs a dedicated project

Reuse the `tech_stack = "Python / FastAPI"` benchmark project (must have
`is_benchmark_project = true` in Supabase, and be passed as `--project-id`).
Groups under the existing FastAPI tab as a new benchmark family.

## Running this suite (from `benchmark/`)

```
# 0. clone the clean upstream once
git clone https://github.com/fastapi/full-stack-fastapi-template.git <fork>

# 1. fresh buggy branch off clean master, then inject (expect 6 applied lines)
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/hardmode-fastapi
python apply_bugs.py <fork> --bug-index suites/fastapi-hardmode/bug_index.json
git -C <fork> add -A && git -C <fork> commit -m "benchmark fastapi hardmode: injected bugs"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py <fork> --bug-index suites/fastapi-hardmode/bug_index.json \
    --results-dir results-fastapi-hard/ --project-id <fastapi-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-fastapi-hard/ \
    --bug-index suites/fastapi-hardmode/bug_index.json --out-dir results-fastapi-hard/scored/
python publish_leaderboard.py --scoreboard results-fastapi-hard/scored/scoreboard.json
```
