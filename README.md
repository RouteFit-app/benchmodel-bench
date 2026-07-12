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

## What's not shipped here (and why)

Some suite docs (`suite.md`) show a full run as `apply_bugs.py -> runner.py ->
scorer.py`. Only `scorer.py` (and the `lifecycle/` provider helpers) live in this
public research core. The others are part of BenchModel's private harness and are
intentionally not published:

- `apply_bugs.py` — applies a suite's `injection` find/replace blocks to a checked-out
  repo to produce the buggy branch. The injections themselves are public (they're in
  each `bug_index.json`), so you can apply them by hand or with a three-line script.
- `runner.py` — drives the reviewer model over a diff and writes the finding JSON that
  `scorer.py` grades. It carries the product's review prompt, so it stays private; build
  your own thin runner on the shipped `lifecycle/` helpers, or grade findings you already
  have. `scorer.py`'s input format is documented at the top of that file.
- `estimate_cost.py` / `publish_leaderboard.py` — the cost estimate is char-based
  (`chars / 4 + scaffold`, priced from `model_pricing.json`) and is reproduced inline in
  the tiered experiment; publishing is BenchModel-specific.

If a `suite.md` references one of these, treat it as "this is how the full harness runs
it," not a file you'll find in this repo. Everything you need to independently check a
score — the answer keys and `scorer.py` — is here.

## Known limitations (the honest part)

This harness is a work in progress and has the construct-validity issues you'd
expect, stated plainly:

- **The oracle used to over-credit vocabulary.** An external audit (June Kim,
  Issue #1) showed the scorer counted a bug as detected on a single keyword
  substring, so 20 lines of generic boilerplate scored ~64% across the answer keys
  at zero model cost. `scorer.py` now gates detection on a file match OR 2+ distinct
  hints (`min_hints_without_file`, default 2). `probe_boilerplate.py` reruns that
  attack: the boilerplate score drops sharply. Residual leakage comes from
  over-generic hint words and substring (not word-boundary) matching; pruning hints
  to symbols per the template's own rule is in progress.
- **Injected bugs can be too easy.** The current mechanical injections (operator
  swaps, guard removal) are caught by nearly every model, so on those suites the
  metric barely discriminates. Fixing this (harder, multi-dimensional bug classes;
  bugs mined from recent post-cutoff fixes so they can't be memorized) is active work.
- **Reintroduced-CVE suites may lean on recall** rather than reasoning; the
  `anti_cheat` controls exist precisely to measure that failure mode.
- **Answer keys reference branches, not pinned commits.** Branches move. `pin_commits.py`
  resolves a suite's `base_branch`/`buggy_branch` to SHAs and writes `base_commit`/
  `buggy_commit` back into the key; run it per suite to freeze the target.
- Grading counts a model *noticing* a problem, not perfectly diagnosing it.

Issues and PRs welcome. If you find where a metric measures something other than
what it claims, that's the most useful thing you can send. This harness is better for
one such report already (see Issue #1).
