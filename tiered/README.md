# Tiered review pipeline (experiment)

A DoorDash-style staged reviewer, run against your existing bug suites so you can
measure **cost per caught bug** instead of claiming it. See `../../TIERED_REVIEW_SPEC.md`
for the full design.

    Scout (cheap, whole diff) -> Verify (strong, per flag) -> Adversary (diff arch, per confirmed)

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
- Their cost comes from `../estimate_cost.py` (same char-based estimate this uses).

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
