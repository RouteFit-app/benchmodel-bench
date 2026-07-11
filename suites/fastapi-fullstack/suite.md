# Suite: fastapi-fullstack

**Status:** `live` — fork `RouteFit-app/benchmodel-fastapi-template`, all
injections verified 1:1 against clean `master`.

## Versions

- **v1** — `bug_index.json` (`version: 1`, branch `benchmark/buggy`). 10 bugs,
  6 high / 4 medium, difficulties 2 easy / 3 medium / 5 hard. First run:
  gemini/claude/deepseek 10/10, gpt-4o 9/10 (missed BUG_002).
- **v2** — `bug_index.v2.json` (`version: 2`, branch `benchmark/buggy-v2`).
  Same `benchmark_name`. Drops the two easy sign-flips (old BUG_004 `is_active`,
  BUG_005 `is_superuser`) and adds two hard bugs:
  - **BUG_011** mass-assignment / privilege escalation — `update_user_me` bound
    to `UserUpdate` instead of `UserUpdateMe`, letting any user PATCH
    `is_superuser: true` on themselves.
  - **BUG_012** ORM data-bleed — `delete_user` cascade filter inverted
    (`owner_id == user_id` → `!=`), wiping every *other* user's items.
  Difficulties: 0 easy / 3 medium / 7 hard. Run it against a fresh `benchmark/buggy-v2`
  checkout into `results-fastapi-v2/` (see suites/README.md "Versioning a suite").

## Target

- **Repo:** https://github.com/fastapi/full-stack-fastapi-template
- **License:** MIT (fork + modify freely)
- **Stacks covered (two for one fork):**
  - Python backend — FastAPI, SQLModel (ORM), Pydantic, PostgreSQL
  - TypeScript frontend — React, Vite, hooks
- **Why this one:** real auth, real API layer, real DB access, real tests, CI
  via GitHub Actions — the surface where reviewer models actually separate.

## Planned bug surface (Track A)

Candidate categories to mine once the code is readable (aim ~10 bugs, mixed
severity, each with exact find/replace + keyword hints):

- **auth_bypass** — drop a permission/ownership check on a protected route.
- **api_contract** — wrong status code, or response schema/field mismatch.
- **orm_query_error** — missing `.where(...)` filter (leaks other users' rows),
  or wrong join — a security-relevant data-exposure bug.
- **validation_gap** — Pydantic field made optional / constraint removed.
- **caching_bug** — stale cache not invalidated on write.
- **null_safety / error handling** — unhandled `None` or swallowed exception.
- **race_condition** — non-atomic read-modify-write on a counter/balance.
- **react/async** (frontend) — missing `await`, stale closure in a hook,
  optimistic update not rolled back on error.

## Fork + branch plan

1. Fork → clone locally → open/mount the folder here.
2. Branches: keep `master` as base; create `benchmark/buggy`.
3. Copy `../_template/bug_index.template.json` → `./bug_index.json`; fill
   `file_locations` with real paths and author the bugs against real source.
4. Commit `benchmark/buggy`; the `master..benchmark/buggy` diff is what the
   runner submits to reviewers.

## Running this suite

Keep this suite's runs and scored output in their **own** dirs so they never get
graded against another suite's answer key (see suites/README.md "Per-suite
isolation"). Run from `benchmark/`:

```
python apply_bugs.py /path/to/benchmodel-fastapi-template --bug-index suites/fastapi-fullstack/bug_index.json
# commit + push benchmark/buggy in the fork
python runner.py /path/to/benchmodel-fastapi-template --bug-index suites/fastapi-fullstack/bug_index.json \
    --results-dir results-fastapi/ --project-id <fastapi-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-fastapi/ --bug-index suites/fastapi-fullstack/bug_index.json \
    --out-dir results-fastapi/scored/
python publish_leaderboard.py --scoreboard results-fastapi/scored/scoreboard.json
```

**Needs a dedicated BenchModel project** with `tech_stack = "Python / FastAPI"`
and `is_benchmark_project = true`; pass its id as `--project-id`. Without it,
runs inherit whatever project you point at (e.g. the RouteFit "Kotlin / Android"
project) and get mis-tagged on the leaderboard.
