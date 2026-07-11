# Suite: spring-hardmode (Hard Mode flagship)

**Status:** `authored, runs pending` — 6 deliberately hard, blended
security + correctness + framework-semantics bugs injected 1:1 into
`spring-projects/spring-petclinic` (the user's local checkout). All 6 verified to
match their target source exactly once against clean `main`, each a clean,
one-line, tab-correct diff.

## Why this suite (the missing tier)

Every v1/v2 suite on the board saturates detection for the top three models, the
only spread is severity, so they rank the laggard (GPT) but not the leaders. The
reason: single-file injected vulns with a recognizable signature are within every
frontier model's competence. Hard Mode is the experiment to **separate the
leaders**, by using bugs where detection itself should fail for some strong
models:

- **Framework-semantics bugs** that require real JPA / Spring knowledge, not
  pattern matching (cascade-on-merge, cascade-from-@ManyToOne to shared lookup
  data, data-binding disallowed-field scopes).
- **Validation/boundary bugs** disguised as plausible, consistent-looking code
  (a guard that mirrors the style of the line above it; an `isAfter` vs `isBefore`
  that differ only at the equality boundary).
- A blend of **security** (mass assignment) and **correctness** (silent data
  loss, integrity), so it scores across metrics, not just "find the vuln."

If this set still ties the top three, that's itself a finding (petclinic is only
~single-module deep); if it cracks them apart, it becomes the template for hard
modes on the other stacks.

## Target

- **Repo:** https://github.com/spring-projects/spring-petclinic (the same local
  checkout the other Spring suites use)
- **base_branch:** `main`
- **buggy_branch:** `benchmark/hardmode` (its own branch; never collides with
  `benchmark/buggy` or `benchmark/real-regressions`)
- Java, tab-indented, one bug per file across 6 files in the `owner` package.

## Bug set (6 bugs)

2 high / 4 medium, all `hard`. 2 security, 4 correctness/framework.

| ID | File | Category | Sev | What's hard about it |
| -- | ---- | -------- | --- | -------------------- |
| BUG_001 | PetController.java | mass_assignment | high | binder drops nested `"*.id"` (keeps `"id"`), nested-id binding / tampering; needs to know `"id"` != `"*.id"` scope |
| BUG_002 | OwnerController.java | mass_assignment | high | binder drops top-level `"id"`, owner-id bindable -> record overwrite on the guard-less create path |
| BUG_003 | Owner.java | data_loss | high | pets cascade `ALL` -> `PERSIST`, merge no longer cascades, pet edits silently not saved (JPA merge semantics) |
| BUG_004 | Pet.java | data_integrity | medium | `cascade = ALL` added to `@ManyToOne type`, ops on a Pet cascade to the shared PetType lookup row |
| BUG_005 | PetValidator.java | validation_gap | medium | birthDate-required gated behind `pet.isNew()`, edits can null out birthDate; mimics the type-check style above it |
| BUG_006 | VisitController.java | boundary_condition | medium | `!isAfter(now)` -> `isBefore(now)`, accepts a visit dated today despite future-only contract (boundary off-by-one) |

Verified with `apply_bugs.py` (each find matches exactly once; mismatch aborts).
No v2, Hard Mode IS the hard set; if it ranks the leaders it gets replicated to
the other stacks rather than deepened in place.

## Needs a dedicated project

Reuse the existing `tech_stack = "Java / Spring Boot"` benchmark project (the one
the other Spring suites publish under). It must have `is_benchmark_project = true`
in Supabase, and be passed as `--project-id`. Groups as a new benchmark family
under the existing Java / Spring Boot tab (different `benchmark_name`), no new tab.

## Running this suite (from `benchmark/`)

```
# 1. fresh buggy branch off clean main, then inject (expect 6 applied lines)
git -C <petclinic> checkout main && git -C <petclinic> checkout -b benchmark/hardmode
python apply_bugs.py <petclinic> --bug-index suites/spring-hardmode/bug_index.json
git -C <petclinic> add -A && git -C <petclinic> commit -m "benchmark spring hardmode: injected bugs"

# 2. run 3x into one dir (pool n=3) / score / publish
python runner.py <petclinic> --bug-index suites/spring-hardmode/bug_index.json \
    --results-dir results-spring-hard/ --project-id <spring-project-id> \
    --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-spring-hard/ \
    --bug-index suites/spring-hardmode/bug_index.json --out-dir results-spring-hard/scored/
python publish_leaderboard.py --scoreboard results-spring-hard/scored/scoreboard.json
```

`<petclinic>` = the local spring-petclinic checkout
(`C:\Users\sahlu\AndroidStudioProjects\spring-petclinic`).
