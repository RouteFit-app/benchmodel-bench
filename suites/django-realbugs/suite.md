# Suite: django-realbugs (real regressions)

**Status:** `authored, runs pending` — the second provenance-proof suite (Python).
Every bug is the exact reverse of a real, merged Django fix, the regression that
actually shipped before maintainers patched it. **BUG_001 reverses a fix for an
assigned CVE (CVE-2026-25674).** No synthetic bugs. Each find verified to match
current `main` exactly once.

## Why this suite

Pairs with the Keycloak real-regression suite to make the provenance story
cross-language: real, historical regressions in two of the most-deployed
open-source codebases (Java + Python), ranking the models, not our own tool, with
a `fixed_by` link per bug for verification. First `Python` (generic, non-FastAPI)
target, so it groups under a `Python` tab.

## Method: regression reintroduction

Took four merged Django bug-fix commits and reversed them. The reviewer (diff
only) must flag exactly what Django's maintainers later fixed, including a real
CVE.

## Target

- **Repo:** https://github.com/django/django
- **base_branch:** `main`  ·  **buggy_branch:** `benchmark/real-regression`
- One bug per file across 4 files.

## Bug set (4 real regressions)

| ID | File | Reverses | Sev | The regression |
| -- | ---- | -------- | --- | -------------- |
| BUG_001 | core/cache/backends/filebased.py | `019e44f67a` (CVE-2026-25674, NVD: low) | low | back to process-global `os.umask` around `makedirs`, incorrect/too-permissive permissions, thread-unsafe |
| BUG_002 | db/models/lookups.py | `5776a1660e` (#31667) | medium | drops `rhs.discard(None)`, None leaks into `__in` IN-clauses (NULL never matches) |
| BUG_003 | forms/fields.py | `f5ea9aa2f3` (#32807) | medium | removes None guard in `JSONField.bound_data`, `json.loads(None)` raises TypeError, form redisplay crashes |
| BUG_004 | contrib/staticfiles/storage.py | `67b334fbaf` (#31517) | medium | only guards `is not None`, a None hash interpolates the literal 'None' into the static filename |

Each `fixed_by` in `bug_index.json` links the upstream fix commit (and CVE) for
per-case verification.

## Needs a dedicated project

Create a BenchModel project with `tech_stack = "Python"` and
`is_benchmark_project = true`, pass its id as `--project-id`. Groups under a
`Python` tab (distinct from the `Python / FastAPI` injected suites).

## Running (from `benchmark/`)

```
# 0. clone django once (blobless keeps it light)
git clone --filter=blob:none https://github.com/django/django.git <fork>

# 1. fresh buggy branch off clean main, then inject (expect 4 applied lines)
git -C <fork> checkout main && git -C <fork> checkout -b benchmark/real-regression
python apply_bugs.py <fork> --bug-index suites/django-realbugs/bug_index.json
git -C <fork> add -A && git -C <fork> commit -m "benchmark django real regressions: reintroduced"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py <fork> --bug-index suites/django-realbugs/bug_index.json \
    --results-dir results-django/ --project-id <python-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-django/ \
    --bug-index suites/django-realbugs/bug_index.json --out-dir results-django/scored/
python publish_leaderboard.py --scoreboard results-django/scored/scoreboard.json
```

Pinned to `main` as of the clone. If `apply_bugs` reports a count mismatch, `main`
drifted on one of these lines, ping me and I'll re-anchor.
