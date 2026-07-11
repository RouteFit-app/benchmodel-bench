# Anti-Cheat: measuring reasoning vs. memorized recall

A benchmark built on real CVEs has one honest weakness. A model can "catch" a
known bug because it read the public write-up during training, not because it
reasoned about the code in front of it. That is **recall, not review**, and it
inflates a model's score in a way that does not survive contact with a bug it
has never seen.

This module measures that gap. It does not try to stop a model from having read
CVEs (impossible). It measures **how much a model leans on that memory instead
of reasoning**, and it strips the easiest way a diff leaks the answer.

Two independent tools:

## 1. Negative controls (`controls.json` + `run_controls.py` + `score_controls.py`)

Every control is **safe code that looks like a famous vulnerability**. For
example: a diff that switches a loader to `yaml.safe_load` (looks like the
`yaml.load` deserialization RCE, but isn't), or one that swaps a token compare to
`hmac.compare_digest` (looks like a timing-attack site, but is the fix).

We hand each control to a model with a neutral "review this diff" prompt that
gives **no hint the code is clean**, then watch what it does:

- A model that **reasons** about the actual code says "looks fine."
- A model running on **memorized patterns** raises the vulnerability anyway.
  That's a **false alarm**, and it's the signal we count.

```
false-alarm rate = (# controls where the model raised the phantom vuln)
                   / (# controls the model reviewed)
```

Lower is better: less recall, more reasoning.

The scorer reuses the main benchmark's polarity guard (`scorer._endorses_change`),
so a model that correctly notes "this now uses `safe_load`, good" is **not**
penalized. Only a model that raises the vuln as a live, open problem is.

### The current control set

| id | resembles | why it's actually safe |
|----|-----------|------------------------|
| `yaml_safe_load` | YAML deserialization RCE | `safe_load` can't build arbitrary objects |
| `literal_eval` | `eval()` code injection | `literal_eval` only parses literals |
| `compare_digest` | timing-attack token compare | `compare_digest` **is** the constant-time fix |
| `parameterized_sql` | SQL injection | value is a bound parameter, not concatenated |
| `md5_cache_key` | broken-crypto / weak hash | MD5 is a cache key, `usedforsecurity=False` |
| `subprocess_list_args` | OS command injection | list args, `shell=False`, no shell to inject into |
| `escape_html` | reflected XSS | input is `escape()`d before output |
| `safe_path_join` | path traversal | `basename` + containment check |

Add a case: drop a `<id>.diff` in `controls/`, add an entry to `controls.json`
with its `trap_keywords` (the vuln-class terms a false alarm would use), done.

### Run it

```bash
# from benchmark/anti_cheat/
python run_controls.py                          # 5 models, 1 run each, diffs scrubbed
python run_controls.py --runs 3                 # repeat 3x per model (recall is consistent; flaky flags show up)
python run_controls.py --no-scrub               # A/B: submit raw diffs to see the scrubber's effect
python score_controls.py                        # false-alarm scoreboard + per-control matrix
```

Keys are read the same way as the lifecycle / correctness / red-team runners:
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) /
`DEEPSEEK_API_KEY`, from the environment or `backend/.env`.

## 2. Tell-scrubbing (`scrub.py`)

`scrub_diff(text)` redacts the labels that hand a model the answer: `CVE-…`,
`GHSA-…`, `CWE-…` identifiers, advisory URLs (NVD, GHSA, Snyk, OSV, …), and
comment lines that literally announce a security fix. It **never edits real
source logic** — only identifiers, links, and announcing comments — and it
returns the list of what it removed so a run can be audited.

Wire it into a real-CVE suite run:

```bash
python runner.py /path/to/repo --reviewer-ai claude-opus-4-8 --scrub
```

This is the cheap, honest defense: it forces the model to earn the catch from the
code, not from a `# fixes CVE-2023-1234` a patch left behind.

## Where this fits

The strongest defense against memorized recall is already in the suites: the
**hand-injected bugs**, which don't exist in any training data. Treat those as
the trusted signal and the reintroduced real CVEs as the softer one. These two
tools add to that: the negative controls put a *number* on each model's recall
tendency, and the scrubber removes the most obvious leak. Together they let the
leaderboard say something most benchmarks can't: *we measured how much each model
is reasoning versus remembering, and here's the score.*
