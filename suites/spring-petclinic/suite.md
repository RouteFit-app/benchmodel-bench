# Suite: spring-petclinic  (Java / Spring Boot)

**Status:** `live` — 7 bugs authored 1:1 against the canonical Spring Boot sample
app, verified to match clean `main` exactly once each.

## Target

- **Repo:** https://github.com/RouteFit-app/spring-petclinic (fork of
  `spring-projects/spring-petclinic`, Apache-2.0)
- **Code under test:** the `owner` domain — Spring MVC controllers, a programmatic
  `Validator`, Spring Data JPA repositories, JPA entities.
- **base_branch:** `main` · **buggy_branch:** `benchmark/buggy`

## Why this suite

Statically-typed enterprise JVM — the most different stack from Kotlin/Android,
a Python API, and a React frontend. Tests whether the cross-stack reviewer
ranking holds on idiomatic, widely-recognized Java. The bugs lean on Spring
specifics a generic reviewer can miss: `@InitBinder` mass-assignment, a
programmatic `Validator`, 0-based `PageRequest`, and a cross-file entity-identity
bug.

## Bugs (v1 — 7, all exact-match, symbol-anchored hints)

2 high / 4 medium / 1 low; 5 hard / 2 medium.

| ID | File | Category | Sev | Diff | What's wrong |
| -- | ---- | -------- | --- | ---- | ------------ |
| BUG_001 | OwnerController | broken_access_control | high | hard | `setDisallowedFields("id","*.id")` → `setDisallowedFields()` — entity `id` becomes bindable (mass assignment / IDOR) |
| BUG_002 | PetValidator | validation_gap | medium | hard | the only "name required" check removed — blank pet names persist |
| BUG_003 | PetController | inverted_logic | medium | hard | duplicate-name check inverted (`!Objects.equals` → `Objects.equals`) |
| BUG_004 | VisitController | temporal_validation | medium | medium | visit-date guard inverted — past dates accepted, future rejected |
| BUG_005 | OwnerController | off_by_one | low | medium | `PageRequest.of(page - 1,…)` → `of(page,…)` — first page unreachable |
| BUG_006 | Owner | entity_identity | high | hard | `getPet(id)` `!pet.isNew()` → `pet.isNew()` — never finds saved pet; edits duplicate (spans Owner + PetController) |
| BUG_007 | Owner | validation_gap | medium | hard | `@NotBlank` removed from `city` |

One is security-relevant (BUG_001). BUG_006 is the cross-file "leader separator":
its effect only shows when you trace `Owner.getPet` into `PetController.updatePetDetails`.

## Bugs (v2 — 7, framework-semantic & cross-file, `bug_index.v2.json`)

v1 saturated detection (all four 7/7). v2 (`version: 2`, branch
`benchmark/buggy-v2`) targets the detection ceiling: each bug needs Spring/JPA
semantics or cross-file tracing, not a one-line read. 2 high / 5 medium; 6 hard.

| ID | File | Category | Sev | Why it's hard |
| -- | ---- | -------- | --- | ------------- |
| BUG_001 | model/BaseEntity | framework_semantics | high | `isNew()` inverted (`id == null` → `!= null`) — app-wide persist/merge blast radius from one line |
| BUG_002 | owner/Owner | jpa_cascade | high | pets cascade `ALL` → `PERSIST` — edits silently not saved; pure JPA semantics |
| BUG_003 | vet/Vets | null_safety | medium | lazy-init guard removed → NPE only visible via `VetController` caller |
| BUG_004 | model/Person | constraint_mismatch | medium | `@Size(max=30)` dropped but `@Column(length=30)` stays — passes validation, fails at DB |
| BUG_005 | owner/Visit | temporal_default | medium | constructor default `plusDays(1)` → `minusDays(1)` |
| BUG_006 | owner/Owner | boolean_logic | medium | `getPet` guard `\|\|` → `&&` — duplicate names slip through on create (shared method) |
| BUG_007 | model/NamedEntity | validation_gap | medium | `@NotBlank` removed from `name` — drops the rule across Pet/PetType/Specialty/Vet at once |

Verified 7/7 against clean `main`. Run on its own branch + `results-spring-v2/`;
coexists with v1 as a separate version on the leaderboard. The open question: do
the JPA-semantic bugs (BUG_001/002) finally break the 7/7 detection ceiling, and
does the cross-file NPE (BUG_003) separate the leaders?

## Needs a dedicated project

Create a BenchModel project with `tech_stack = "Java / Spring Boot"` and
`is_benchmark_project = true` **before** the first run, so it lands in its own tab
(no retag). Pass its id (or set `$env:BENCHMODEL_PROJECT_ID`).

## Running (from `benchmark/`)

```
git -C <fork> checkout main && git -C <fork> checkout -b benchmark/buggy
python apply_bugs.py <fork> --bug-index suites/spring-petclinic/bug_index.json   # expect 7 applied
git -C <fork> add -A && git -C <fork> commit -m "benchmark spring v1: injected bugs"
$env:BENCHMODEL_PROJECT_ID="<spring-project-id>"
python runner.py <fork> --bug-index suites/spring-petclinic/bug_index.json \
    --results-dir results-spring/ --reviewer-ai gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
python scorer.py --results-dir results-spring/ --bug-index suites/spring-petclinic/bug_index.json \
    --out-dir results-spring/scored/
python publish_leaderboard.py --scoreboard results-spring/scored/scoreboard.json
# evidence:
python publish_artifacts.py <fork> --bug-index suites/spring-petclinic/bug_index.json \
    --results-dir results-spring/ --out <benchmodel-results> --slug spring/v1
```

`<fork>` = `C:\Users\sahlu\AndroidStudioProjects\spring-petclinic`.
