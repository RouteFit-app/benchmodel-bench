# Suite: parse-server-realbugs (real regressions)

**Status:** `authored + validated, runs pending` — adds a real-regression suite
to the **Node.js / Express** tab. Reverses the fix for **GHSA-5fw2-8jcv-xh87
(Critical, CVSS 9.8)**, an **account takeover via operator injection** in
**Parse Server** (parse-community, 21k+ stars), a widely deployed Express/Node
backend-as-a-service. No synthetic bugs. The find was verified to match current
`alpha` exactly once and the reversal passes `node --check`.

## The bug (1 real regression)

| ID | File · func | Reverses | Sev | The regression |
| -- | ----------- | -------- | --- | -------------- |
| BUG_001 | `src/Auth.js` · `findUsersWithAuthData` | GHSA-5fw2-8jcv-xh87 (commit 0d0a5543, PR #10185) | high | removes the 4-line guard requiring `providerAuthData.id` to be a string, so an object (a query operator) can be injected into the auth-data lookup → account takeover |

## The attack the guard stops

`findUsersWithAuthData` resolves a third-party login by building a query from the
provider's auth id:

```js
return { [`authData.${provider}.id`]: providerAuthData.id };
```

The fix added:

```js
if (typeof providerAuthData.id !== 'string') {
  throw new Parse.Error(Parse.Error.INVALID_VALUE, `Invalid authData id for provider '${provider}'.`);
}
```

Without it, a client can send an **object** as the id — e.g. `{"$ne": null}`,
`{"$regex": "^"}`, `{"$gt": ""}` — which Parse/Mongo interprets as a query
**operator** instead of a literal id. The operator matches a victim's auth
record, and the attacker is logged in as that user: an unauthenticated **account
takeover**.

## Why it's a fair-but-hard target

The removed line is a *type check*, not an obvious "security guard" comment. The
reviewer has to connect three things: (1) `providerAuthData.id` is
attacker-supplied, (2) it flows directly into a database query key/value, and
(3) allowing a non-string lets the client smuggle a query operator (NoSQL
operator injection) that bypasses authentication. A shallow read sees "an id is
used to look up a user" and moves on. Naming a generic "missing validation" is
partial; the catch names operator/NoSQL injection or account-takeover via a
non-string id reaching the query.

## Running (from `benchmark/`)

```
# 0. clone parse-server (blobless keeps it light). NOTE: default branch is `alpha`.
git clone --filter=blob:none https://github.com/parse-community/parse-server.git parse-server-repo

# 1. fresh buggy branch off the default (alpha), then inject (expect 1 applied block)
git -C parse-server-repo checkout -b benchmark/real-regression
python apply_bugs.py parse-server-repo --bug-index suites/parse-server-realbugs/bug_index.json
git -C parse-server-repo add -A && git -C parse-server-repo commit -m "benchmark parse-server real regression: reintroduced"

# 2. run n=3 / score / publish (project tech_stack = Node.js / Express)
python runner.py parse-server-repo --bug-index suites/parse-server-realbugs/bug_index.json \
    --results-dir results-parse-server/ --project-id <node-express-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-parse-server/ \
    --bug-index suites/parse-server-realbugs/bug_index.json --out-dir results-parse-server/scored/
python publish_leaderboard.py --scoreboard results-parse-server/scored/scoreboard.json
```

If `apply_bugs` reports a count mismatch, `alpha` drifted on this block; re-anchor
before running.
