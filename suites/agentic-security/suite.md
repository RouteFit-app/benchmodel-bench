# Agentic Security suite (OWASP Top 10 for Agentic Applications)

Review-side benchmark of the threats specific to **autonomous agents and chatbots** —
not generic web bugs. We ship a small, realistic agent framework as the secure baseline
(`backend/app/agent/`), then inject one OWASP-Agentic vulnerability per file and score
who catches them. The hard part for a reviewer is reasoning about the **data-vs-instruction
trust boundary** and autonomous tool execution, not spotting a syntactically bad line.

- **Repo:** benchmodel-fastapi-template (the `backend/app/agent/` package, added on `master`)
- **base_branch:** `master`  •  **buggy_branch:** `benchmark/agentic`
- **tech_stack:** `Agentic Security` (drives the **Agents** page). Comes from the BenchModel
  project, so run under a project tagged `Agentic Security`.

## The five injected weaknesses

| ID | OWASP-Agentic | File · function | Weakness | Sev |
|----|---------------|-----------------|----------|-----|
| BUG_001 | A1 Goal Hijacking / Prompt Injection | `runtime.py · build_messages` | untrusted tool observation appended as a **system** message → injection becomes policy | high |
| BUG_002 | A4 Memory & Context Poisoning | `memory.py · build_memory_context` | trust filter dropped → tool-written (poisoned) memories become instructions | medium |
| BUG_003 | A2 Tool & API Misuse | `tools.py · call_tool` | allowlist gate removed → model can dispatch any registered tool (RCE-by-proxy) | high |
| BUG_004 | A6 Excessive Privilege / Identity Abuse | `permissions.py · authorize` | returns `True` unconditionally → least-privilege collapses | medium |
| BUG_005 | A5 AI Supply-Chain Compromise | `plugins.py · load_plugin` | `pip install`s + imports an arbitrary package name → supply-chain RCE | high |

## Setup (one-time: commit the fixture to master)
The secure agent framework is new code added to the template. Commit it on `master` first,
so the `base..buggy` diff shows only the injected vulnerabilities:
```
cd <fastapi-template repo>
git checkout master
git add backend/app/agent && git commit -m "agent framework fixture (secure baseline)"
```

## Run
```
git checkout -b benchmark/agentic
python <modela>/benchmark/apply_bugs.py . --bug-index <modela>/benchmark/suites/agentic-security/bug_index.json
git add -A && git commit -m "agentic benchmark injections"

cd <modela>/benchmark
python runner.py <fastapi-template repo> --bug-index suites/agentic-security/bug_index.json \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat \
    --results-dir results-agentic --project-id <AGENTIC_PROJECT_ID> --token <BM_TOKEN>
python scorer.py --bug-index suites/agentic-security/bug_index.json --results-dir results-agentic
python publish_leaderboard.py --scoreboard results-agentic/scored/scoreboard.json
```
Run the review+score 3× and pool for the headline.
```
```
