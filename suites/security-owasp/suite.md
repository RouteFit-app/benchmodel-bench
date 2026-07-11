# OWASP Top 10 suite (Security Review track)

Reviewer-track security suite. We inject six **real, named OWASP vulnerabilities** into a
production-shaped FastAPI app (the full-stack template) as small, surgical diffs, then
measure who catches them, who mis-rates severity, and who invents false positives.

This is the "Security Review" track from the red-team plan: we are **not** asking models to
attack anything — we hand them a PR diff and score how well they spot the weakness. Each
bug lives in a **different file** so the scorer's file-aware matching keeps findings clean,
and each carries an `owasp` label so results roll up into a vulnerability × model matrix
(the Security Blind Spots view).

- **Repo:** benchmodel-fastapi-template
- **base_branch:** `master`  •  **buggy_branch:** `benchmark/owasp`
- **tech_stack:** comes from the **BenchModel project**, not this file. Run under the same
  project you tagged `Security` (the one supply-chain / prompt-injection use) so it lands on
  the Security page. The `tech_stack` key in `bug_index.json` is informational only.

## The six injected weaknesses

| ID | OWASP | File · function | Weakness | Sev |
|----|-------|-----------------|----------|-----|
| BUG_001 | A01 Broken Access Control | `items.py · delete_item` | Ownership check removed → IDOR, any user deletes any item | high |
| BUG_002 | A01 Broken Access Control | `users.py · read_users` | `superuser` dependency dropped → unauthenticated user enumeration | high |
| BUG_003 | A07 AuthN Failures | `deps.py · get_current_user` | `jwt.decode(..., verify_signature=False)` → token forgery / full bypass | high |
| BUG_004 | A02 Cryptographic Failures | `config.py · Settings` | `SECRET_KEY` hardcoded to a literal → anyone can sign valid JWTs | high |
| BUG_005 | A03 Injection | `crud.py · get_user_by_email` | f-string `text(...)` raw SQL → SQL injection from login/recovery | high |
| BUG_006 | A09 Logging Failures | `login.py · login_access_token` | `print(... password=...)` → plaintext credentials in logs | medium |

Severity is mostly `high` (these are genuine criticals); BUG_006 is `medium` and acts as a
calibration point for the severity-accuracy column.

## v2 — the subtle set (`bug_index.v2.json`, branch `benchmark/owasp-v2`)

Where v1 saturates on detection, v2's six bugs need data-flow / boolean tracing:

| ID | OWASP | File · function | Weakness | Sev |
|----|-------|-----------------|----------|-----|
| BUG_001 | A04 Insecure Design | `utils.py · generate_password_reset_token` | reset JWT silently drops its `exp` claim → token never expires | high |
| BUG_002 | A01 Broken Access Control | `items.py · update_item` | ownership operator flipped `!=`→`==` → edit others' items, not your own | high |
| BUG_003 | A02 Cryptographic Failures | `deps.py · get_current_user` | `"none"` added to JWT algorithm allowlist → unsigned-token forgery | high |
| BUG_004 | A07 AuthN Failures | `crud.py · authenticate` | constant-time `DUMMY_HASH` defense removed → user-enumeration timing oracle | medium |
| BUG_005 | A07 AuthN Failures | `login.py · recover_password` | recovery now 404s on unknown email → account enumeration | medium |
| BUG_006 | A03 Injection | `users.py · read_users` | `sort` param interpolated into `order_by(text(...))` → ORDER BY injection | high |

Run identically to v1 but with `--bug-index suites/security-owasp/bug_index.v2.json`,
branch `benchmark/owasp-v2`, and `--results-dir results-owasp-v2`.

## Methodology notes
- Every `find` matches its target file **exactly once** and every injected file still
  compiles (validated in CI before publishing).
- Reviewers see only the `base..buggy` diff — never this file.
- Detection is scored on symbols/keywords (`detection_hints.must_mention_any`), not phrasing,
  so wording style is neutral across models.

## Run
First create the buggy branch from a clean `master` checkout, then run under the **Security**
project so `tech_stack` is set correctly:
```
# 1. make the buggy branch
cd <fastapi-template repo>
git checkout master && git checkout -b benchmark/owasp
python <modela>/benchmark/apply_bugs.py . --bug-index <modela>/benchmark/suites/security-owasp/bug_index.json
git add -A && git commit -m "owasp benchmark injections"

# 2. review + score + publish (use the Security project's id/token)
cd <modela>/benchmark
python runner.py <fastapi-template repo> --bug-index suites/security-owasp/bug_index.json \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat \
    --results-dir results-owasp --project-id <SECURITY_PROJECT_ID> --token <BM_TOKEN>
python scorer.py --bug-index suites/security-owasp/bug_index.json --results-dir results-owasp
python publish_leaderboard.py --scoreboard results-owasp/scored/scoreboard.json
```
Run the review+score 3× into the same results dir and pool for the headline — the Security
Blind Spots matrix (vuln × model) is the stable signal, not any single run's ranking.
