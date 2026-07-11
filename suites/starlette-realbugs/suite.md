# Suite: starlette-realbugs (real regressions)

**Status:** `authored, runs pending` — the first **AI-framework-CVE** real-regression
suite. Starlette is the ASGI foundation under FastAPI, so these are real
vulnerabilities in the framework people build AI services on. Every bug is the
exact reverse of a merged Starlette security fix. **BUG_001 reverses
CVE-2026-48710 (BadHost, May 2026); BUG_002 reverses CVE-2023-29159.** No
synthetic bugs. Each find verified to match current `main` exactly once, and the
full reversal set was applied to a clean checkout to confirm it reproduces the
buggy state.

## Why this suite

The audience is people building with AI, and the most relevant security question
for them is whether a reviewer catches bugs in the *frameworks they ship on*. This
suite tests exactly that, on real, recent, assigned CVEs in Starlette/FastAPI, the
neutral provenance pitch (we rank the models, on bugs maintainers caught and
fixed) applied to the AI-framework supply chain. Groups under a `Python / Starlette`
tab, distinct from the FastAPI-app injected suites.

## Method: regression reintroduction

Took three merged Starlette security-fix commits and reversed them so the buggy
branch reintroduces the original defect. The reviewer (diff only) must flag
exactly what Starlette's maintainers later fixed, including two assigned CVEs.

## Target

- **Repo:** https://github.com/Kludex/starlette
- **base_branch:** `main`  ·  **buggy_branch:** `benchmark/real-regression`
- Two files (`datastructures.py`, `staticfiles.py`).

## Bug set (3 real regressions)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | datastructures.py · URL.__init__ | `764dab0` (#3279, **CVE-2026-48710** BadHost) | high | drops `_HOST_RE.fullmatch`, raw Host header builds request.url, path poisoning / auth bypass |
| BUG_002 | staticfiles.py · lookup_path | `1797de4` (**CVE-2023-29159**) | medium | `commonpath`→`commonprefix`, character-prefix check, sibling-dir path traversal |
| BUG_003 | staticfiles.py · lookup_path | `fd53168` (#3287) | medium | removes the absolute-path guard, `os.path.join` discards the static root, arbitrary file read |

Each `fixed_by` in `bug_index.json` links the upstream fix commit (and CVE) for
per-case verification.

## Severity note

BUG_001 (BadHost) is rated HIGH per the public advisory. BUG_002/BUG_003 are
weighted medium pending a CVSS check, consistent with the board's calibrate-to-the-
published-rating discipline; do not headline a higher severity without verifying NVD.

## Compile note

All three reversals are valid Python: BUG_001 leaves `_HOST_RE`/`import re`
defined-but-unused (legal at module scope), and BUG_002/003 each leave their code
runnable. The buggy branch imports and runs, the defects are runtime/security.

## Needs a dedicated project

Create a BenchModel project with `tech_stack = "Python / Starlette"` and
`is_benchmark_project = true`, pass its id as `--project-id`. Groups under a new
`Python / Starlette` tab.

## Running (from `benchmark/`)

```
# 0. clone starlette once (blobless keeps it light)
git clone --filter=blob:none https://github.com/Kludex/starlette.git <fork>

# 1. fresh buggy branch off clean main, then inject (expect 3 applied lines)
git -C <fork> checkout main && git -C <fork> checkout -b benchmark/real-regression
python apply_bugs.py <fork> --bug-index suites/starlette-realbugs/bug_index.json
git -C <fork> add -A && git -C <fork> commit -m "benchmark starlette real regressions: reintroduced"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py <fork> --bug-index suites/starlette-realbugs/bug_index.json \
    --results-dir results-starlette/ --project-id <starlette-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-starlette/ \
    --bug-index suites/starlette-realbugs/bug_index.json --out-dir results-starlette/scored/
python publish_leaderboard.py --scoreboard results-starlette/scored/scoreboard.json
```

Pinned to `main` as of the clone (`de970d7`). If `apply_bugs` reports a count
mismatch, `main` drifted on one of these lines, ping me and I'll re-anchor.
