# BenchModel benchmark harness

The open, re-runnable core of [BenchModel](https://benchmodel.io): the bug suites,
the grader, and three self-contained experiments for measuring how well LLMs catch
real software bugs. Bring your own provider keys; nothing here calls a hosted
service.

This is the research harness, not the product. It's shared in the spirit of
"receipts, not claims" — clone it, run it with your own keys, and check the numbers.

## What's here

- `suites/` — the injected-bug suites. Each `bug_index(.vN).json` is an answer key:
  the bugs, their files, severities, and detection hints, plus the repo + base/buggy
  branches the diff is computed from. `suite.md` documents each one.
- `scorer.py` — grades a set of findings against a suite's answer key (detection,
  false positives, severity, a polarity guard so "this is now fixed" doesn't count
  as a catch).
- `model_pricing.json` — per-model $/Mtoken, for the char-based cost estimates.
- `lifecycle/lifecycle_runner.py` — the shared provider-call helpers (`load_env`,
  `key_for`, `call`) used by the experiments below.

### Experiments (each has its own README)

- `anti_cheat/` — **memorization controls.** Safe code that *looks* like a famous
  vulnerability (yaml.safe_load, hmac.compare_digest, parameterized SQL, ...). A
  model that reasons says "fine"; a model running on memorized CVE patterns raises
  the phantom vuln. Measures recall-over-reasoning. Fully self-contained (inline
  diffs, no external repo needed) — the best place to start.
- `tiered/` — the **tiered-review experiment.** A cheap-scout / strong-verifier /
  adversarial-judge pipeline, run against the suites and a large real diff. Result:
  on normal repos it cost more and caught fewer bugs than a single strong-model call.
  Includes the write-up.
- `chaos/` — an **AST bug injector** (mutation testing operators) plus a runner that
  measures whether models actually *separate* on injected bugs.

## Run it

Keys (BYOK), in the environment or a local `.env`:
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) /
`DEEPSEEK_API_KEY`.

```bash
# memorization controls (self-contained, ~$0.30)
cd anti_cheat && python run_controls.py && python score_controls.py

# tiered experiment against a suite (needs that suite's repo checked out locally)
cd tiered && python run_tiered.py --bug-index ../suites/security-owasp/bug_index.json --repo /path/to/repo --out results/owasp.json

# chaos injector on any Python code
cd chaos && python run_chaos.py --target /path/to/code --max-mutations 15
```

The main suites diff a real repo between two branches, so you clone the target repo
yourself (URL + branches are in each `bug_index.json`); no repos are vendored here.

## Known limitations (the honest part)

This harness is a work in progress and has the construct-validity issues you'd
expect, stated plainly:

- **Injected bugs can be too easy.** The current mechanical injections (operator
  swaps, guard removal) are caught by nearly every model, so on those suites the
  metric barely discriminates. Fixing this (harder, multi-dimensional bug classes;
  bugs mined from recent post-cutoff fixes so they can't be memorized) is active work.
- **Reintroduced-CVE suites may lean on recall** rather than reasoning; the
  `anti_cheat` controls exist precisely to measure that failure mode.
- Grading counts a model *noticing* a problem, not perfectly diagnosing it.

Issues and PRs welcome. If you find where a metric measures something other than
what it claims, that's the most useful thing you can send.
