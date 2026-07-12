# Tiered review pipeline (experiment)

A DoorDash-style staged reviewer, run against your existing bug suites so you can
measure **cost per caught bug** instead of claiming it.

    Scout (cheap, whole diff) -> Verify (strong, per flag) -> Adversary (diff arch, per confirmed)

## Result (receipts, not a claim)

We ran this and it lost. On the injected-bug suites the cheap scout already caught
everything, so the extra stages were pure overhead (~100x the cost for the same
result); on a large real diff (99k chars of merged Django) the tiered pipeline
found **zero** issues while a single strong-model call found **four**, at half the
cost. The raw run files are in `receipts/`:

- `receipts/owasp.json` — OWASP suite, tiered caught 6/6 but cost $0.124 vs the
  scout alone at $0.0009.
- `receipts/react.json` — React suite, tiered 8/8 at $0.139.
- `receipts/django-big.json` — django `main~20..main`, **tiered 0 findings at
  $0.27 vs a single opus baseline's 4 findings at ~$0.14** (baseline block is in
  the same file).

Each file carries per-stage call counts, char counts, and estimated cost under
`run_meta`, so the numbers above are recomputable from the file. The write-up of
what this means is the `/findings` post on the site.

Keys (BYOK): `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` (or
`GOOGLE_API_KEY`) / `DEEPSEEK_API_KEY`, in the environment or `backend/.env`.

## Prerequisite

The Security (OWASP) suite diffs the `benchmodel-fastapi-template` repo, branch
`benchmark/owasp` off `master`. Point `--repo` at your local checkout of it (the same
one your existing runner uses). If the diff comes back empty, that branch isn't
checked out.

## Run the Security suite

```bash
# from benchmark/tiered/
python run_tiered.py \
  --bug-index ../suites/security-owasp/bug_index.json \
  --repo /path/to/benchmodel-fastapi-template \
  --out results/owasp.json

python score_tiered.py --result results/owasp.json --bug-index ../suites/security-owasp/bug_index.json
```

`run_tiered.py` prints per-stage cost as it goes; `score_tiered.py` prints catch
rate, false positives, and the headline **cost per caught bug**.

## The comparison that sells it

The tiered number only means something next to single-model baselines on the SAME
suite:

- **Cheap model alone** and **strong model alone** catch rates are already on your
  leaderboard for this suite (deepseek-chat, claude-opus-4-8 on OWASP).
- Their cost comes from the same char-based estimate this uses (`chars / 4 +
  scaffold`, priced from `../model_pricing.json`), computed inline in
  `run_tiered.py` — see the `run_meta` cost fields in any `receipts/*.json`.

You're looking for the tiered row to land near the strong model's catch rate at a
fraction of its cost, with fewer false positives. If it does, that's the chart for
the landing page, measured on your own bugs, reproducible.

## Config

Models per stage default to `deepseek-chat` (scout), `claude-opus-4-8` (verify),
`gpt-4o` (adversarial). Override with `--models SCOUT VERIFY ADV`. The right picks
come from your leaderboard: best recall-per-dollar scout, most precise verifier, best
independent-family skeptic.

## Notes / honesty

- Cost is **estimated from characters** (chars / 4 + scaffold, from
  `model_pricing.json`), because the provider calls don't return token counts. It's an
  estimate, good for relative comparison; confirm against real BYOK billing before
  publishing absolute numbers.
- Calls run at **temperature 0** for determinism.
- This is an experiment harness. Only lift it into `backend/services/` as a product
  review mode after the numbers hold up.
