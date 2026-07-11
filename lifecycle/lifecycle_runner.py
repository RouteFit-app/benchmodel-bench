#!/usr/bin/env python3
"""lifecycle_runner.py -- round-robin writer->reviewer (Track B).

Phase 1 (write):  each model writes the task.
Phase 2 (review): the OTHER models each review every writer's code.

Keys (BYOK): ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY (or GOOGLE_API_KEY)
/ DEEPSEEK_API_KEY -- in the environment or backend/.env.

Usage (from benchmark/lifecycle/):
  python lifecycle_runner.py --task login/task.json \
      --models gpt-4o gemini-2.5-pro claude-sonnet-4-6 deepseek-chat
"""
import argparse, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
WRITER_SYSTEM = ("You are a senior software engineer writing production code. Write secure, "
                 "correct code and follow best practices. Return ONLY the requested code -- no "
                 "markdown fences, no explanation.")
REVIEW_SYSTEM = ("You are a senior security reviewer. Identify security and correctness problems "
                 "in the code you are shown. Be specific and concise; list each issue clearly.")

def load_env():
    for envp in [HERE.parents[1] / "backend" / ".env", HERE / ".env"]:
        if not envp.exists(): continue
        try:
            from dotenv import load_dotenv; load_dotenv(envp)
        except ImportError:
            for line in envp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("="); os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def key_for(m):
    m = m.lower()
    if "claude" in m: return os.environ.get("ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY"
    if any(x in m for x in ("gpt", "o1", "o3", "o4")): return os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY"
    if "gemini" in m: return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"), "GEMINI_API_KEY"
    if "deepseek" in m: return os.environ.get("DEEPSEEK_API_KEY"), "DEEPSEEK_API_KEY"
    return None, "UNKNOWN"

def _call_impl(model, key, system, user):
    m = model.lower()
    if "claude" in m:
        import anthropic
        c = anthropic.Anthropic(api_key=key, timeout=120.0)
        r = c.messages.create(model=model, max_tokens=2000, system=system, messages=[{"role": "user", "content": user}])
        return r.content[0].text
    if "gemini" in m:
        from google import genai; from google.genai import types
        c = genai.Client(api_key=key)
        r = c.models.generate_content(model=model, contents=user, config=types.GenerateContentConfig(system_instruction=system))
        return r.text
    from openai import OpenAI
    c = OpenAI(api_key=key, base_url=("https://api.deepseek.com" if "deepseek" in m else None), timeout=120.0)
    r = c.chat.completions.create(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content

import concurrent.futures as _cf
_EXEC = _cf.ThreadPoolExecutor(max_workers=8)

def call(model, key, system, user, attempts=2, hard_timeout=150):
    """Hard wall-clock timeout + one retry so a single stalled API call (e.g. a hung
    Gemini request) can't freeze the whole run. On final failure the caller logs the
    error and moves on, leaving that one slot empty rather than blocking."""
    last = None
    for _ in range(attempts):
        try:
            return _EXEC.submit(_call_impl, model, key, system, user).result(timeout=hard_timeout)
        except Exception as e:
            last = e
    raise last

def safe(s): return "".join(ch if (ch.isalnum() or ch in "-_.") else "-" for ch in s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", type=Path, required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    load_env()
    spec = json.loads(a.task.read_text(encoding="utf-8"))
    ctx = ""
    for rel in spec.get("context_files", []):
        ctx += f"\n\n--- {rel} ---\n{(a.task.parent / rel).read_text(encoding='utf-8')}"
    writer_user = spec["writer_prompt"] + "\n\n## Existing project files:" + ctx
    out = a.out or (a.task.parent / "results")
    keys = {m: key_for(m) for m in a.models}
    usable = [m for m in a.models if keys[m][0]]
    for m in a.models:
        if not keys[m][0]: print(f"  SKIP {m}: set {keys[m][1]}")

    print("== Phase 1: WRITE ==")
    code = {}
    for m in usable:
        try:
            c = call(m, keys[m][0], WRITER_SYSTEM, writer_user)
        except Exception as e:
            print(f"  ERROR write {m}: {e}"); continue
        (out / safe(m)).mkdir(parents=True, exist_ok=True)
        (out / safe(m) / "code.txt").write_text(c, encoding="utf-8")
        code[m] = c
        print(f"  {m} wrote {len(c)} chars")

    print("== Phase 2: REVIEW (each writer reviewed by the others) ==")
    for w in code:
        rdir = out / safe(w) / "reviews"; rdir.mkdir(parents=True, exist_ok=True)
        for r in usable:
            if r == w: continue
            review_user = spec["review_prompt"] + "\n\n```\n" + code[w] + "\n```"
            try:
                rv = call(r, keys[r][0], REVIEW_SYSTEM, review_user)
            except Exception as e:
                print(f"  ERROR {r} reviewing {w}: {e}"); continue
            (rdir / f"{safe(r)}.txt").write_text(rv, encoding="utf-8")
            print(f"  {r} reviewed {w}")
    print(f"\nDone -> {out}\nNow: python lifecycle_scorer.py --results-dir {out}")

if __name__ == "__main__":
    main()
