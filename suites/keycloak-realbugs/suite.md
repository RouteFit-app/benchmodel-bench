# Suite: keycloak-realbugs (real regressions)

**Status:** `authored, runs pending` — the first **provenance-proof** suite: every
bug is the exact reverse of a real, merged Keycloak bug-fix, i.e. the original
regression that actually shipped before maintainers patched it. No synthetic
bugs. Verified each find matches current `main` exactly once.

## Why this suite (the Greptile answer)

Greptile's and CodeRabbit's benchmarks are vendor benchmarks (they rank their own
tool). The credibility gap we close is twofold: we rank the **models** (neutral),
and now we test on **real historical regressions**, not injected edits. A skeptic
can't say "you designed the bug to favor a model", these bugs were written by
Keycloak contributors and caught by Keycloak maintainers. Each carries
`provenance: "real-regression"` and a `fixed_by` link to the upstream fix commit.

This is also the first **Java (non-Spring)** target, so it groups under a `Java`
tab, distinct from the Spring suites.

## Method: regression reintroduction

For each bug we took a merged bug-fix commit and **reversed it** so the buggy
branch reintroduces the original defect. The reviewer (seeing only the diff)
must flag exactly what Keycloak's maintainers later fixed.

## Target

- **Repo:** https://github.com/keycloak/keycloak
- **base_branch:** `main`
- **buggy_branch:** `benchmark/real-regression`
- Plain Java (Quarkus/JBoss, not Spring). One bug per file across 4 files.

## Bug set (4 real regressions)

| ID | File | Reverses | Sev | The regression |
| -- | ---- | -------- | --- | -------------- |
| BUG_001 | IdpCreateUserIfUniqueAuthenticator.java | `b6027fe65d` | medium | drops `\|\| username.trim().isEmpty()`, brokered login can create a blank-username account (key recalibrated high->medium after run 1, both reviewers rated it below high) |
| BUG_002 | ImmutableAttributeValidator.java | `5d37617911` | medium | stops lower-casing EMAIL before comparison, uppercase LDAP email fails immutable-attribute validation |
| BUG_003 | DefaultKeycloakSession.java | `4d5f69098b` | medium | `Optional.ofNullable(realm.getId())` evaluates `realm.getId()` first, NPE on null realm (Optional guards the wrong thing) |
| BUG_004 | InfinispanOrganizationProvider.java | `e0dfe8d5b1` | medium | removes null guard + `.toLowerCase()` on the org domain cache key, mixed-case cache miss + null-domain NPE |

Each `fixed_by` in `bug_index.json` links the upstream fix commit for per-case
verification.

## Needs a dedicated project

Create a BenchModel project with `tech_stack = "Java"` and
`is_benchmark_project = true`, pass its id as `--project-id`. Groups under a new
`Java` tab.

## Running (from `benchmark/`)

```
# 0. clone keycloak once (it's large; a blobless clone is lighter and works fine)
git clone --filter=blob:none https://github.com/keycloak/keycloak.git <fork>

# 1. fresh buggy branch off clean main, then inject (expect 4 applied lines)
git -C <fork> checkout main && git -C <fork> checkout -b benchmark/real-regression
python apply_bugs.py <fork> --bug-index suites/keycloak-realbugs/bug_index.json
git -C <fork> add -A && git -C <fork> commit -m "benchmark keycloak real regressions: reintroduced"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py <fork> --bug-index suites/keycloak-realbugs/bug_index.json \
    --results-dir results-keycloak/ --project-id <java-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-keycloak/ \
    --bug-index suites/keycloak-realbugs/bug_index.json --out-dir results-keycloak/scored/
python publish_leaderboard.py --scoreboard results-keycloak/scored/scoreboard.json
```

Pinned to `main` as of commit `e73344070e`. If `apply_bugs` ever reports a count
mismatch, `main` drifted on one of these lines, ping me and I'll re-anchor.
