# Benchmark Suites (multi-stack)

This directory is the future home for **per-stack benchmark suites**. It is
**scaffolding only** right now — the live RouteFit benchmark still runs from
`benchmark/bug_index.json` and is untouched. Nothing here is wired into
`apply_bugs.py` / `runner.py` / `scorer.py` yet.

## Why this exists

Today the bug-injection framework is hardcoded to one repo:

- `benchmark/bug_index.json` — a single answer key (RouteFit, Kotlin/Android).
- `apply_bugs.py` — a literal `FILE_LOCATIONS` map of RouteFit's Kotlin paths.

To add the stacks we want (FastAPI, React, Django, Node, Spring, …) each one
needs its own answer key against its own real repo. This folder defines the
layout those suites will live in, so adding a stack becomes "drop in a
`bug_index.json`" instead of editing the core scripts each time.

## Target layout

```
benchmark/
  bug_index.json              <- RouteFit answer key (Track A, legacy single-suite)
  apply_bugs.py  runner.py  scorer.py  publish_leaderboard.py
  results/                    <- RouteFit runs (+ results/scored/), legacy
  results-fastapi/            <- FastAPI runs (+ results-fastapi/scored/), per-suite
  suites/
    README.md                 <- this file
    _template/
      bug_index.template.json <- annotated schema to copy for a new stack
    fastapi-fullstack/
      suite.md                <- target repo, fork/branch plan, status
      bug_index.json          <- (added once the repo is forked + cloned)
```

## Framework support (done)

The pipeline is suite-aware: `apply_bugs.py` reads `file_locations` from whichever
`bug_index.json` it's given (falling back to the built-in RouteFit map only for
the original single-suite index), and `apply_bugs.py` / `runner.py` / `scorer.py`
all accept `--bug-index path/to/suite/bug_index.json`. A suite is fully runnable
from its own `bug_index.json`.

## Adding a new stack (playbook)

1. **Fork** the target repo into an org/account you control (GitHub-side step —
   has to be done by a human; Modela can't fork on your behalf).
2. **Clone** it locally and mount/open the folder so it can be read here.
3. Create two branches: a clean `base` (or use `main`) and a `benchmark/buggy`.
4. **Author the answer key**: copy `_template/bug_index.template.json` to
   `suites/<stack>/bug_index.json` and write real bugs — each `injection` must
   `find`/`replace_with` (or `find_pattern`/`insert_after`) text that exists
   **exactly once** in the real files, same contract `apply_bugs.py` enforces.
5. Commit the buggy branch, capture the `base..benchmark/buggy` diff.
6. Run the pipeline against that diff (see "Per-suite isolation" below):
   `apply_bugs.py` → `runner.py` → `scorer.py` → `publish_leaderboard.py`.

Step 4 is the part Modela can do **for** you, but only after step 2 — bug
injections must match exact file contents, so the repo has to be readable first.

## Per-suite isolation (IMPORTANT — avoids cross-suite zeros)

`scorer.py` grades **every** result file it's given against the **one** answer
key you pass. If suites share a `results/` directory, the other suite's runs get
graded against the wrong `bug_index.json` and score 0/10, polluting the
leaderboard. Two rules keep suites clean:

1. **One results dir per suite.** Pass `--results-dir results-<stack>/` on the
   runner and the matching `--out-dir results-<stack>/scored/` on the scorer.
   Never let two suites share a `results/` folder.
2. **One BenchModel project per stack.** Each run is tagged with the *project's*
   `tech_stack`, not the suite's — so create a project per stack
   (e.g. tech_stack `Python / FastAPI`, `is_benchmark_project = true`) and pass
   its `--project-id`. This also sets `benchmark_eligible`.

Worked example (FastAPI suite, run from `benchmark/`):

```
python apply_bugs.py /path/to/fork --bug-index suites/fastapi-fullstack/bug_index.json
# (commit the buggy branch in the fork)
python runner.py /path/to/fork --bug-index suites/fastapi-fullstack/bug_index.json \
    --results-dir results-fastapi/ --project-id <fastapi-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-fastapi/ --bug-index suites/fastapi-fullstack/bug_index.json \
    --out-dir results-fastapi/scored/
python publish_leaderboard.py --scoreboard results-fastapi/scored/scoreboard.json
```

RouteFit keeps using the legacy `results/` + `bug_index.json` (unchanged).

## Versioning a suite (evolve difficulty, keep history)

A suite can have multiple bug-set versions. Keep the **same `benchmark_name`**,
bump the `version` field, and put each version in its own file:

```
suites/<stack>/bug_index.json      <- v1 (version: 1)
suites/<stack>/bug_index.v2.json   <- v2 (version: 2), harder bug set
```

(RouteFit's legacy v1 lives at `benchmark/bug_index.json`; its v2 at
`benchmark/bug_index.v2.json`.)

Rules:

- **Same `benchmark_name`, different `version`** → v1 and v2 coexist as separate
  leaderboard rows (the 4-column unique key includes `benchmark_version`), and the
  UI groups them with the newest marked **Current** above the older one.
- Give v2 its own **`buggy_branch`** (e.g. `benchmark/buggy-v2`) so it doesn't
  clash with v1's branch in the target repo.
- Run each version end to end against its own checkout + **its own results dir**.
- Requires migration `0006_leaderboard_version.sql` (adds `benchmark_version` +
  the version-aware unique constraint).

Current versions:

| Suite | v1 | v2 |
| ----- | -- | -- |
| RouteFit (Kotlin) | `benchmark/bug_index.json` | `benchmark/bug_index.v2.json` |
| FastAPI (Python) | `suites/fastapi-fullstack/bug_index.json` | `suites/fastapi-fullstack/bug_index.v2.json` |
| React/TS (frontend) | `suites/react-frontend/bug_index.json` | `suites/react-frontend/bug_index.v2.json` |

Running a specific version (FastAPI v2, from `benchmark/`):

```
git -C <fork> checkout master && git -C <fork> checkout -b benchmark/buggy-v2
python apply_bugs.py <fork> --bug-index suites/fastapi-fullstack/bug_index.v2.json
# commit/push benchmark/buggy-v2 in the fork, then:
python runner.py <fork> --bug-index suites/fastapi-fullstack/bug_index.v2.json \
    --results-dir results-fastapi-v2/ --project-id <fastapi-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-fastapi-v2/ --bug-index suites/fastapi-fullstack/bug_index.v2.json \
    --out-dir results-fastapi-v2/scored/
python publish_leaderboard.py --scoreboard results-fastapi-v2/scored/scoreboard.json
```

## Bug authoring guidance (keep it objective)

Good benchmark bugs are unambiguous and have keyword-checkable detection hints:
sign flips, off-by-10x thresholds, unit-conversion errors, null-safety
regressions, resource/memory leaks, wrong-thread dispatch, inverted retention
logic. See `benchmark/bug_index.json` for ten worked RouteFit examples. Avoid
subjective "is this good code" changes — the scorer grades on whether a
finding's text mentions `detection_hints.must_mention_any`, so each bug needs a
small set of words a correct finding would have to use.

## Detection hints: use SYMBOLS, not adjectives (anti-bias rule)

The scorer matches a finding against `detection_hints.must_mention_any`. Whoever
writes those words encodes a *vocabulary* — and that is the single biggest place
reviewer-model bias can sneak into Track A. If the hints are prose adjectives
("ownership check", "stale closure", "race condition"), a model that happens to
describe bugs with the author's phrasing scores higher than one describing the
*same* bug in different words. That measures writing style, not detection.

**Rule: hints must be code symbols and literal tokens from the diff, not
descriptive prose.** A correct finding has to cite these regardless of which
model (or human) wrote it, so they're vocabulary-neutral:

- ✅ good (symbol-anchored): `owner_id`, `invalidateQueries`, `item.id`, `!==`,
  `removeEventListener`, `exp`, `is_superuser`, `limit`, `await`
- ⚠️ acceptable as *secondary* hints: short canonical terms with one obvious
  spelling (`IDOR`, `off-by-one`, `leak`, `expiration`).
- ❌ avoid as the *only* hint: open-ended adjectives a correct finding could
  legitimately omit ("dangerous", "incorrect logic", "bad practice", "subtle").

Each bug should be detectable by at least two symbols an accurate finding is
*forced* to name (the changed identifier + the file/function or the literal
operator). If you can't write symbol-based hints for a bug, the bug is probably
too subjective to grade fairly — redesign it. The React v2 set
(`suites/react-frontend/bug_index.v2.json`) is the reference for this style.

## Self-bias audit (run before trusting a leaderboard)

Provenance bias (a generator model favoring bugs it authored) is **low for the
surgical sign-flip style we use** — a one-token flip in real third-party code
carries no model fingerprint — but it is not zero, and it grows the moment you
let an AI propose whole buggy functions or pick the bug *distribution*. Keep it
honest with these standing checks:

1. **Human owns the answer key.** An AI may *propose* an injection, but a human
   reviews and approves every `find`/`replace_with`, severity, and hint set. The
   benchmark is human-owned regardless of who drafted it.
2. **Symbol-based hints** (section above) — neutralizes the scorer-vocabulary
   vector, which matters more than who typed the injection.
3. **Generator ≠ sole reviewer.** Don't let one model both author a suite and be
   the only model that shines on it. Rotate authors, and/or have a *different*
   model independently re-derive the detection hints **blind** (given only the
   diff, not the original hints) and diff the two keyword sets.
4. **Mix in zero-provenance bugs.** Real reverted regressions / CVEs / historical
   `git revert`s have no model author at all — seed a few per suite as a control.
5. **Measure it, don't assume it.** Track whether the authoring model
   systematically overperforms on its own suites vs. human- or other-model-
   authored ones. So far Claude-authored suites do *not* favor Claude (DeepSeek
   won RouteFit v2, Gemini tied React, GPT bottom) — weak but real evidence the
   bias is small. A bias you quantify is a bias you can discount or correct for.
6. **Realism gate beats provenance.** The bigger threat than "which AI helped" is
   a bug that's unrealistic or quietly tuned to one model's blind spot. The human
   review should ask "would this actually ship?" more than "which model suggested
   it?".

Disclosure: the current Track A suites (RouteFit, FastAPI, React) were drafted
with Claude assistance, and Claude is one of the four reviewers. Per check #5 the
live results do not show Claude dominating, but the clean future state is a
non-Claude (human or other-model) blind pass over each answer key.

## Track B (lifecycle) — planned, not built

Everything above is **Track A** (known-bug detection: can a reviewer find
injected bugs?). The bigger idea — **Track B**, the end-to-end writer→reviewer
lifecycle — is captured here as a pointer, not yet scaffolded in code:

```
Task -> Writer AI -> Commit/PR -> Reviewer AI -> Findings
     -> Writer Response -> Reviewer Recheck -> Human Verdict -> Outcome
```

Track B measures pair performance (which writer+reviewer combo collaborates
best), fix quality, and dispute resolution — not just detection. It maps onto
Modela's existing `reviews`/`findings`/`messages` lifecycle, so it's an
extension of the product, not a separate system.

When Track B is greenlit, the likely first artifacts are a `lifecycle/` suite
type (task spec + acceptance tests as the answer key) and a cross-model matrix
runner. Not started yet by design.
