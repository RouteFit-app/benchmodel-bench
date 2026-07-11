# Chaos Audit validation

Cheap experiment to decide whether "Chaos Audit" (inject known bugs into a customer's
OWN code, measure which model catches them) is worth building. Same clinical approach
as the tiered-review experiment: prove it discriminates on real code before writing a
line of product or website copy.

- `mutate.py` -- AST bug injector (comparison swaps, boolean flips, dropped `not`,
  guard-clause removal). Every mutant is syntactically valid; each is a clean
  one-change diff.
- `run_chaos.py` -- injects N bugs into a target repo, has each model review each diff
  blind, and reports the per-model catch rate and the **spread**.

## Run it on your own code

```bash
# from benchmark/chaos/
python run_chaos.py --target ../../backend --max-mutations 15
```

Keys (BYOK): `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` (or
`GOOGLE_API_KEY`) / `DEEPSEEK_API_KEY`, in env or `backend/.env`. Cost is ~$0.30-0.50
for 15 bugs x 3 models (tiny diffs).

## The kill criterion

The whole value of a per-codebase audit is that it **separates** models. Watch the
spread:

- **Spread < 15 points** (or the cheap model catches everything): the audit tells a
  customer nothing they couldn't guess. Dead, same "no discrimination" failure the
  curated suites showed. Stop.
- **Real spread**: the audit produces a per-codebase signal a customer would pay for
  ("on your code, Opus catches 12/15, GPT-4o 8/15"). Worth pursuing.

## Honest limits

- Grading is "did the model return a real finding on a one-change diff" -- clean, but
  it counts *noticing* the change, not perfectly diagnosing it.
- Some mutations may be equivalent (no behavior change); we target likely-meaningful
  sites but don't run your tests to confirm.
- Python-only for now (uses the `ast` module). Other languages would need their own
  parser (babel/acorn for JS, etc.) before this becomes a product.
