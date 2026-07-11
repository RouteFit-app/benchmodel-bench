# Suite: gin-realbugs (real regressions)

**Status:** `authored, runs pending` — the third provenance-proof suite, and the
first **Go** target. Every bug is the exact reverse of a real, merged Gin
bug-fix, the regression that actually shipped before maintainers patched it.
**BUG_001 reverses the fix for an assigned CVE (CVE-2023-29401).** No synthetic
bugs. Each find verified to match current `master` exactly once, and the full
reversal set was applied to a clean checkout to confirm it produces the buggy
state cleanly.

## Why this suite

Extends the real-regression story to a third language (after Java/Keycloak and
Python/Django) in one of the most-deployed Go web frameworks. Same neutrality
pitch: we rank the **models**, on **real historical regressions** maintainers
caught and fixed, with a `fixed_by` link (commit + PR, plus a CVE) per bug. Also
directly answers the Greptile/CodeRabbit "vendor benchmark" critique, these bugs
were written by Gin contributors and caught by Gin maintainers, not designed by
us to favor any model. Groups under a `Go` tab.

## Method: regression reintroduction

Took four merged Gin bug-fix commits and reversed them so the buggy branch
reintroduces the original defect. The reviewer (diff only) must flag exactly
what Gin's maintainers later fixed, including a real CVE.

## Target

- **Repo:** https://github.com/gin-gonic/gin
- **base_branch:** `master`  ·  **buggy_branch:** `benchmark/real-regression`
- Two files (`context.go`, `gin.go`); three bugs in context.go (distinct
  functions) + one in gin.go.

## Bug set (4 real regressions)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | context.go · FileAttachment | `2d4bbec` (#3556, **CVE-2023-29401**, CVSS 4.3) | medium | drops `escapeQuotes(filename)`, raw filename interpolated into `Content-Disposition`, response-header injection |
| BUG_002 | context.go · initQueryCache | `e0d46de` (#3969) | medium | drops `&& c.Request.URL != nil`, nil-pointer panic when `Request.URL` is nil |
| BUG_003 | context.go · NegotiateFormat | `7cb151b` (#3397) | medium | drops `&& i < len(offer)`, index-out-of-range panic via a short `Accept` offer (DoS) |
| BUG_004 | gin.go · RunFd | `c3d5a28` (#4422) | medium | drops `defer f.Close()`, file-descriptor leak on every `RunFd` |

Each `fixed_by` in `bug_index.json` links the upstream fix commit + PR (and the
CVE for BUG_001) for per-case verification.

## Compile note

All four reversals are compile-safe Go: BUG_001 leaves `escapeQuotes`/`quoteEscaper`
defined-but-unused (legal at package scope), and BUG_002–004 each leave their
variables still used. So the buggy branch builds, the defects are runtime/security
bugs, exactly what a reviewer should catch from the diff.

## Needs a dedicated project

Create a BenchModel project with `tech_stack = "Go"` and
`is_benchmark_project = true`, pass its id as `--project-id`. Groups under a new
`Go` tab.

## Running (from `benchmark/`)

```
# 0. clone gin once (blobless keeps it light)
git clone --filter=blob:none https://github.com/gin-gonic/gin.git <fork>

# 1. fresh buggy branch off clean master, then inject (expect 4 applied lines)
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/real-regression
python apply_bugs.py <fork> --bug-index suites/gin-realbugs/bug_index.json
git -C <fork> add -A && git -C <fork> commit -m "benchmark gin real regressions: reintroduced"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py <fork> --bug-index suites/gin-realbugs/bug_index.json \
    --results-dir results-gin/ --project-id <go-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-gin/ \
    --bug-index suites/gin-realbugs/bug_index.json --out-dir results-gin/scored/
python publish_leaderboard.py --scoreboard results-gin/scored/scoreboard.json
```

Pinned to `master` as of the clone (`03f3e42`). If `apply_bugs` reports a count
mismatch, `master` drifted on one of these lines, ping me and I'll re-anchor.
