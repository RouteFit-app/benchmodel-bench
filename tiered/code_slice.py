"""code_slice -- pull grounded source out of a repo checkout for an LLM stage.

The verifier and adversarial stages must reason about the ACTUAL code, not a
finding's prose, or they hallucinate. This reads the real file from the repo
(checked out at the buggy branch) and returns either a hunk plus surrounding
context, or the whole file. Flagged lines get a "->" marker so the model knows
which lines the scout pointed at.
"""
import re
import subprocess
from pathlib import Path

MAX_WHOLE_FILE_LINES = 1200  # cap so a giant file can't blow up token cost


def _clean_rel(file_path: str) -> str:
    # Scout reads the diff, so a path may arrive as "a/app/x.py" or "b/app/x.py".
    fp = (file_path or "").strip().strip('"').strip("'").replace("\\", "/")
    if fp.startswith(("a/", "b/")):
        fp = fp[2:]
    return fp


def _read_file(repo_path, rel: str, ref):
    """File contents at a git ref (the buggy branch) if given, else the working
    tree. Reading at `ref` is what matters: the diff is computed between branches
    without checking one out, so the working tree is usually the CLEAN base and
    would hand the verifier fixed code."""
    if ref:
        r = subprocess.run(
            ["git", "-C", str(repo_path), "show", f"{ref}:{rel}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            return None
        return r.stdout
    full = Path(repo_path) / rel
    if not full.exists():
        return None
    try:
        return full.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def code_slice(repo_path, file_path, line_range=None, context: int = 25, whole_file: bool = False, ref=None) -> str:
    rel = _clean_rel(file_path)
    if not rel:
        return "[code_slice: no file path given]"
    text = _read_file(repo_path, rel, ref)
    if text is None:
        return f"[code_slice: {rel} not found{f' at {ref}' if ref else ''}]"
    lines = text.splitlines(keepends=True)

    if whole_file:
        body = "".join(lines[:MAX_WHOLE_FILE_LINES])
        if len(lines) > MAX_WHOLE_FILE_LINES:
            body += f"\n... [truncated at {MAX_WHOLE_FILE_LINES} lines]\n"
        return body

    nums = [int(n) for n in re.findall(r"\d+", str(line_range or ""))]
    if not nums:
        return f"[code_slice: bad line_range {line_range!r}]"
    start, end = min(nums), max(nums)
    lo = max(0, start - 1 - context)
    hi = min(len(lines), end + context)
    out = []
    for i in range(lo, hi):
        ln = i + 1
        marker = " -> " if start <= ln <= end else "    "
        out.append(f"{ln}:{marker}{lines[i]}")
    return "".join(out)
