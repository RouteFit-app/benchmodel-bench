# Suite: node-boilerplate (Security Config)

**Status:** `authored, runs pending` — 6 v1 + 6 v2 bugs injected 1:1 against
`hagopj13/node-express-boilerplate` (a production Express + Mongoose + Passport
REST API boilerplate). All 12 injections verified to match their target source
exactly once against clean `master` (commit `179ae84`), each a clean, minimal
diff.

## Why this suite

A second Node target that deliberately attacks a **different bug class** than the
RealWorld suite. RealWorld is a domain app with no security middleware, so its
bugs are handler-level (ownership, crypto in services). This boilerplate ships
the whole infra/config/auth layer, helmet, express-mongo-sanitize, xss-clean,
express-rate-limit, a role/permission map, joi-validated env config, passport-jwt,
which lets the bugs live in places a domain app can't host:

- **NoSQL injection** (Mongoose, not SQL/Prisma) — a class not covered anywhere
  else on the board.
- **Security misconfiguration / A05** (helmet, CORS reflect-with-credentials).
- **Broken RBAC** via the role-rights map and the auth middleware.
- **Brute-force / A07** via the rate limiter.
- **Weak config** via the joi env schema.

Same `tech_stack` as the RealWorld suite (`Node.js / Express`), so it groups as a
**second benchmark family under the existing Node tab**, no new tab. Different
`benchmark_name` keeps the two leaderboard groups separate.

## Target

- **Repo:** https://github.com/hagopj13/node-express-boilerplate
- **Pinned base:** `master` @ `179ae84` (Express, Mongoose, Passport-JWT, helmet,
  express-mongo-sanitize, xss-clean, express-rate-limit, joi). Plain JS (no TS).
- **base_branch:** `master`
- **buggy_branch (v1):** `benchmark/node-sec`
- **buggy_branch (v2):** `benchmark/node-sec-v2`

## Bug set (v1 — 6 bugs, textbook)

5 high / 1 medium. One vuln per file; clearly recognizable removed/weakened
controls.

| ID | File | Category | OWASP | What's wrong |
| -- | ---- | -------- | ----- | ------------ |
| BUG_001 | src/app.js | injection | A03 | `app.use(mongoSanitize())` removed -> NoSQL operator injection on login |
| BUG_002 | src/config/config.js | cryptographic_failure | A02 | `JWT_SECRET` `required()` -> `default('secret')`, boots with a known key |
| BUG_003 | src/config/roles.js | broken_access_control | A01 | `user` role granted `['getUsers','manageUsers']` -> every user is admin |
| BUG_004 | src/middlewares/rateLimiter.js | security_misconfiguration | A07 | auth limiter `max` 20 -> 100000, brute-force throttle effectively off |
| BUG_005 | src/models/user.model.js | sensitive_data_exposure | A02 | `private: true` dropped from password -> bcrypt hash serialized in responses |
| BUG_006 | src/config/passport.js | broken_authentication | A07 | token-type guard removed -> refresh/reset tokens accepted as access tokens |

## Bug set (v2 — 6 bugs, `bug_index.v2.json`, subtle)

2 high / 4 medium, all hard. Each reads as plausible (often "correct-looking")
code; the vuln only surfaces under auth / data-flow reasoning.

| ID | File | Category | OWASP | What's subtle |
| -- | ---- | -------- | ----- | ------------- |
| BUG_001 | src/middlewares/auth.js | broken_access_control | A01 | ownership check `!==` -> `===`, rights-less user can act on OTHER users (IDOR) |
| BUG_002 | src/services/token.service.js | broken_authentication | A02 | `jwt.verify` -> `jwt.decode`, signature no longer checked |
| BUG_003 | src/config/config.js | broken_authentication | A07 | access-token expiry `30` -> `43200` min (30 days), non-revocable bearer |
| BUG_004 | src/models/user.model.js | cryptographic_failure | A02 | pre-save hash trigger `isModified('password')` -> `('name')`, plaintext on reset |
| BUG_005 | src/services/auth.service.js | broken_authentication | A07 | login split into 404-vs-401, account enumeration |
| BUG_006 | src/app.js | security_misconfiguration | A05 | `cors()` -> `cors({ origin: true, credentials: true })`, reflect-any-origin + creds |

Both sets verified with `apply_bugs.py` (each find matches exactly once; mismatch
aborts).

## Needs a dedicated project

Runs are tagged with the **project's** `tech_stack`, not this suite's. Reuse the
same `tech_stack = "Node.js / Express"` benchmark project you made for the
RealWorld suite (or make a second one). It must have `is_benchmark_project = true`
in Supabase, otherwise the runner's submission is treated as a gated user review
and rejected with 422, and it must be passed as `--project-id`.

## Running this suite (from `benchmark/`)

```
# 0. clone the target once
git clone https://github.com/hagopj13/node-express-boilerplate.git <fork>

# 1. v1: fresh buggy branch off clean master, then inject (expect 6 applied lines)
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/node-sec
python apply_bugs.py <fork> --bug-index suites/node-boilerplate/bug_index.json
git -C <fork> add -A && git -C <fork> commit -m "benchmark node-sec v1: injected bugs"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py <fork> --bug-index suites/node-boilerplate/bug_index.json \
    --results-dir results-node-sec/ --project-id <node-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-node-sec/ \
    --bug-index suites/node-boilerplate/bug_index.json --out-dir results-node-sec/scored/
python publish_leaderboard.py --scoreboard results-node-sec/scored/scoreboard.json
```

For v2, repeat from clean `master` with branch `benchmark/node-sec-v2`,
`--bug-index suites/node-boilerplate/bug_index.v2.json`, and
`--results-dir results-node-sec-v2/`. Always cut v2 from clean `master`.
