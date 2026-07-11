# Suite: node-express (RealWorld)

**Status:** `authored, runs pending` — 6 v1 + 6 v2 bugs injected 1:1 against
`gothinkster/node-express-realworld-example-app` (the canonical "RealWorld"
Medium-clone backend). All 12 injections verified to match their target source
exactly once against clean `master` (commit `30b68e1`), each producing a clean,
minimal diff.

## Why this suite

The fifth independent stack and the **first Node.js / Express / TypeScript**
target, added to test whether the cross-stack reviewer signal (GPT-4o weakest,
worst at severity) holds on a server-side JS codebase, and to give the
leaderboard a recognizable Node reference app (the Express analogue to
spring-petclinic). The app is a real REST API: Express routes -> controllers ->
services -> Prisma, with JWT auth (`express-jwt` + `jsonwebtoken`) and bcrypt.
That layering lets the bugs sit in genuinely Node-idiomatic places: the JWT
verification middleware, the token signer, a Prisma `update` data object, a
route handler reading `req.query`.

## Target

- **Repo:** https://github.com/gothinkster/node-express-realworld-example-app
- **Pinned base:** `master` @ `30b68e1` (TypeScript, Express, Prisma, bcryptjs,
  jsonwebtoken, express-jwt). It is **not** one of the existing forks — clone it
  fresh; nothing in it needs modifying except the injected branch.
- **base_branch:** `master`
- **buggy_branch (v1):** `benchmark/node-express`
- **buggy_branch (v2):** `benchmark/node-express-v2`

One vuln per file; the same six files host both versions (different functions),
so v1 and v2 never collide.

## Bug set (v1 — 6 bugs, textbook)

All six high severity. OWASP spread A01/A02/A07/A09. These are meant to be
recognizable — the "can the reviewer find a real, named vuln at all" floor.

| ID | File | Category | OWASP | What's wrong |
| -- | ---- | -------- | ----- | ------------ |
| BUG_001 | auth.ts | broken_authentication | A07 | JWT middleware accepts `algorithms: ['HS256', 'none']` — unsigned token = auth bypass |
| BUG_002 | token.utils.ts | cryptographic_failure | A02 | signing key hardcoded to `'superSecret'`, configured `JWT_SECRET` ignored |
| BUG_003 | auth.service.ts | cryptographic_failure | A02 | `createUser` stores the password in plaintext (bcrypt.hash dropped) |
| BUG_004 | article.service.ts | broken_access_control | A01 | `deleteArticle` ownership 403 check removed — any user deletes any article (IDOR) |
| BUG_005 | auth.controller.ts | logging_failure | A09 | login route `console.log`s email + plaintext password to stdout |
| BUG_006 | profile.service.ts | sensitive_data_exposure | A01 | `getProfile` returns the raw Prisma user (email + password hash) on a public endpoint |

BUG_005 carries a `severity_note`: credential-logging (CWE-532) is keyed **high**
for the same public bias-check as the OWASP suite — models rating it medium/low
diverge from the key.

## Bug set (v2 — 6 bugs, `bug_index.v2.json`, subtle)

Same `benchmark_name`, `version: 2`, branch `benchmark/node-express-v2`. Each
changed line reads as plausible code; the vuln only surfaces under
authorization / data-flow reasoning. 3 high / 3 medium, all hard.

| ID | File | Category | OWASP | What's subtle |
| -- | ---- | -------- | ----- | ------------- |
| BUG_001 | auth.controller.ts | broken_access_control | A01 | `getCurrentUser(Number(req.query.id) || req.auth?.user?.id)` — `/user?id=5` is an IDOR / account takeover |
| BUG_002 | auth.service.ts | mass_assignment | A08 | `updateUser` spreads raw `...userPayload` into Prisma `data` — over-posting any column |
| BUG_003 | article.service.ts | broken_access_control | A01 | `updateArticle` ownership check removed, buried in a long Prisma function |
| BUG_004 | auth.ts | sensitive_data_exposure | A07 | token also read from `?token=` query — JWT leaks to logs / Referer / history |
| BUG_005 | profile.service.ts | sensitive_data_exposure | A01 | `getProfile` spreads `email` into the public profile response (PII leak) |
| BUG_006 | token.utils.ts | broken_authentication | A07 | `expiresIn: '60d'` dropped — tokens never expire, leaked token is permanent |

Both sets verified with `apply_bugs.py` (each find matches exactly once;
mismatch aborts).

## Needs a dedicated project

Runs are tagged with the **project's** `tech_stack`, not this suite's. Create a
BenchModel project with `tech_stack = "Node.js / Express"` and
`is_benchmark_project = true`, and pass its id as `--project-id`. Without it the
runs inherit whatever project you point at and get mis-tagged on the leaderboard
(this is exactly how the "Not specified" tab snuck in earlier). Add
`"Node.js / Express"` to the tech-stack dropdown if it isn't there yet.

## Running this suite (from `benchmark/`)

```
# 0. clone the target once, somewhere local
git clone https://github.com/gothinkster/node-express-realworld-example-app.git <fork>

# 1. fresh buggy branch off clean master, then inject (v1)
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/node-express
python apply_bugs.py <fork> --bug-index suites/node-express/bug_index.json
#    expect 6 "applied BUG_00X" lines

# 2. commit (the runner reads the local diff; push optional)
git -C <fork> add -A && git -C <fork> commit -m "benchmark node-express v1: injected bugs"

# 3. run / score / publish — own results dir
python runner.py <fork> --bug-index suites/node-express/bug_index.json \
    --results-dir results-node-express/ --project-id <node-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-node-express/ \
    --bug-index suites/node-express/bug_index.json \
    --out-dir results-node-express/scored/
python publish_leaderboard.py --scoreboard results-node-express/scored/scoreboard.json
```

For v2, repeat from clean `master` with branch `benchmark/node-express-v2`,
`--bug-index suites/node-express/bug_index.v2.json`, and
`--results-dir results-node-express-v2/`. Always cut v2 from clean `master`, not
from the v1 buggy branch.

Pool to n=3 (run the runner 3x into the same results dir, or 3 separate dirs and
let `publish_leaderboard.py` pool by run_count) before publishing, same as the
other suites.
