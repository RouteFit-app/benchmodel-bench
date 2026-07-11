# Spring PetClinic Regressions (real-world bugs)

Unlike the other suites, **no bug here was authored for the benchmark.** Each one is a
real fix from spring-petclinic's git history, **reverted** so the original regression is
reintroduced. This is the Defects4J pattern and it neutralizes the "synthetic injection
inflates scores" critique — the reviewer is auditing bugs that genuinely shipped.

- **Repo:** spring-petclinic (mounted) · **base:** `main` · **buggy:** `benchmark/real-regressions`
- **Bugs (each = a reverted maintainer fix):**
  1. `BUG_001` — `PetController` compares Integer ids with `!=` instead of `Objects.equals` (reference vs value). Reverted from **fdc40a7**.
  2. `BUG_002` — editing a pet calls `owner.addPet(pet)` instead of updating it, creating a duplicate. Reverted from **2aa53f9** (Fixes #1752).
  3. `BUG_003` — removes the guard rejecting an owner-id/URL mismatch on update. Reverted from **14af47d**.

Each bug records its `provenance` (commit, date, message) in bug_index.json.

## Run
```
# 1) buggy branch = main with the 3 fixes reverted in
cd <spring-petclinic>; git checkout main && git checkout -b benchmark/real-regressions
cd <modela>/benchmark
python apply_bugs.py <spring-petclinic> --bug-index suites/spring-realbugs/bug_index.json
cd <spring-petclinic>; git add -A && git commit -m "Real regressions" && git checkout main
# 2) run -> score -> publish
cd <modela>/benchmark
python runner.py <spring-petclinic> --bug-index suites/spring-realbugs/bug_index.json \
  --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat \
  --results-dir results-spring-realbugs --project-id <SPRING_PROJECT_ID> --token <TOKEN>
python scorer.py            --bug-index suites/spring-realbugs/bug_index.json --results-dir results-spring-realbugs
python publish_leaderboard.py --scoreboard results-spring-realbugs/scored/scoreboard.json
```
