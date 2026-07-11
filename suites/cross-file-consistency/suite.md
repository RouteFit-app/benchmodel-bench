# Cross-File Consistency suite

Reviewer-track suite that tests whether a model catches **cross-file inconsistencies** —
a change in one file that leaves a dependent file stale or out of sync. This is the
real "API changed, the other layer didn't" failure mode that single-file bug suites
(and writer tasks) miss.

- **Repo:** benchmodel-fastapi-template (mounted)
- **base_branch:** `master`  •  **buggy_branch:** `benchmark/crossfile`
- **Bugs (all anchored in `models.py`, each only wrong relative to another file):**
  1. `UserPublic` exposes `phone` that nothing populates (response ↔ data layer).
  2. `UserCreate` requires `referral_code` that crud's `model_validate` silently drops (schema ↔ crud ↔ table).
  3. `UserUpdate` renames `password`→`new_password`; `crud.update_user` still keys on `"password"` (models ↔ crud).
  4. `User` gains a `last_login` column with no Alembic migration (model ↔ migrations).

## Run
```
python apply_bugs.py <fastapi-template repo> --bug-index suites/cross-file-consistency/bug_index.json
python runner.py     <fastapi-template repo> --bug-index suites/cross-file-consistency/bug_index.json \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat --results-dir results-crossfile
python scorer.py            --bug-index suites/cross-file-consistency/bug_index.json --results-dir results-crossfile
python publish_leaderboard.py --scoreboard results-crossfile/scored/scoreboard.json
```
