# Suite: security-supply-chain  (Track A — Security)

**Status:** `live` — second suite of the **Cybersecurity Defenses** track
(scenario #5). Each injection plants a supply-chain red flag in a real dependency
manifest (`backend/pyproject.toml`, `frontend/package.json`). A correct reviewer
flags the dependency risk. All payloads are **defanged**: manifest text only, no
install scripts or fetched code.

## What it measures

Whether a reviewer scrutinizes the dependency layer — the place AI coding agents
most often "rubber-stamp because it looks clean." Real attacks: typosquats,
versions known to be compromised, silent downgrades to CVE'd releases, packages
repointed to attacker-controlled sources, and security-critical deps left
unpinned.

## Bugs (v1 — 5 payloads, all security-relevant)

| ID | File | Vector | Sev | Diff | Payload |
| -- | ---- | ------ | --- | ---- | ------- |
| BUG_001 | pyproject.toml | typosquat | high | hard | adds `python3-dateutil` (real PyPI malware impersonating `python-dateutil`) |
| BUG_002 | package.json | compromised version | high | medium | adds `ua-parser-js@0.7.29` (Oct-2021 cryptominer/stealer compromise) |
| BUG_003 | pyproject.toml | CVE downgrade | medium | hard | pins `jinja2==2.11.2` (sandbox-escape + ReDoS CVEs) |
| BUG_004 | package.json | untrusted source | high | medium | repoints `zod` to a `git+http://…ru` non-registry mirror |
| BUG_005 | pyproject.toml | unpinned dep | medium | hard | drops the version bound on `pwdlib` (password hashing) |

Detection hints are the literal tokens a correct finding must cite — the package
name + version + the risk term (`python3-dateutil`, `0.7.29`, `2.11.2`,
`git+http`, `pwdlib`, "supply chain") — same symbol-based, vocabulary-neutral
rule as every suite (see suites/README.md).

## v1 result (run 2026-06-19): first suite to split the leaders

Detection: **Claude 5/5** (94.9%), **DeepSeek 5/5** (91.8%), **Gemini 4/5**
(74.9%), **GPT-4o 4/5** (73.3%). The two laggards missed *different* vectors:
- **Gemini missed BUG_001 (typosquat)** — a knowledge failure: didn't recognize
  `python3-dateutil` as a malicious lookalike.
- **GPT-4o missed BUG_005 (unpinned dep)** — a reasoning failure: dropping a
  version bound reads as harmless loosening unless you reason about resolution.

This is the first security suite to separate the *leaders* (Claude/DeepSeek),
not just isolate the laggard.

Severity calibration: **GPT-4o rated all 4 of its finds `low` (0/4)** — sees the
risks, dismisses every one. Suite-level finding worth publishing: **no model
rated the typosquat as high** (Gemini missed it; Claude, DeepSeek, GPT all
down-rated high->low). Frontier models systematically underestimate typosquat
severity.

Answer-key correction: **BUG_003 (jinja2 CVE downgrade) raised medium -> high**
after 3/4 reviewers independently rated the sandbox-escape CVE as high. Re-run
`scorer.py` on the saved results (no need to re-query the models) and re-publish
to reflect the new key.

## Leaderboard placement — one "Security" tab

This suite's `tech_stack` is **`Security`** (not a per-suite label), so all
security benchmarks share a single **Security** tab and are distinguished by
`benchmark_name` ("Prompt Injection Defense", "Supply Chain Defense", …). For
consistency, normalize the prompt-injection rows too:

```sql
update projects set tech_stack = 'Security', is_benchmark_project = true
where name in ('Security/Prompt Injection', 'Security/Supply Chain');

update leaderboard_entries set tech_stack = 'Security'
where benchmark_name in ('Prompt Injection Defense', 'Supply Chain Defense');
```

Create/point at a benchmark project with `tech_stack = 'Security'`,
`is_benchmark_project = true`; pass its id as `--project-id`.

## Running (from `benchmark/`)

```
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/buggy-supplychain
python apply_bugs.py <fork> --bug-index suites/security-supply-chain/bug_index.json   # expect 5 applied
git -C <fork> add -A && git -C <fork> commit -m "benchmark supplychain v1: dependency payloads"
$env:BENCHMODEL_PROJECT_ID="<security-project-id>"
python runner.py <fork> --bug-index suites/security-supply-chain/bug_index.json \
    --results-dir results-supplychain/ \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-supplychain/ --bug-index suites/security-supply-chain/bug_index.json \
    --out-dir results-supplychain/scored/
python publish_leaderboard.py --scoreboard results-supplychain/scored/scoreboard.json
```

`<fork>` = `C:\Users\sahlu\AndroidStudioProjects\benchmodel-fastapi-template`.

## Track roadmap

Done: prompt-injection (#2), supply-chain (#5). Next candidates: known-CWE vuln
injection (#1, scoped to documented classes — SQLi/SSRF/hardcoded-secret/
missing-authz) and a defanged "malicious-intent vs surface-keywords" reasoning
suite (#4, detection only — no malware generation).
