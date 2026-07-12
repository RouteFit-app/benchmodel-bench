#!/usr/bin/env python3
"""pin_commits.py -- freeze a suite's answer key to exact commit SHAs.

June Kim's audit (Issue #1, finding 3) noted that 0 of the answer keys pinned a
commit: they referenced BRANCHES (base_branch / buggy_branch), and branches move,
so a published leaderboard row wasn't reproducible against a frozen point.

This resolves a suite's base_branch and buggy_branch to their current SHAs in a
checked-out clone and writes `base_commit` / `buggy_commit` back into the
bug_index.json, in place, preserving field order. Run it once per suite whenever
you (re)cut the buggy branch.

    python pin_commits.py --bug-index suites/security-owasp/bug_index.json \
                          --repo /path/to/benchmodel-fastapi-template

    # check without writing
    python pin_commits.py --bug-index suites/security-owasp/bug_index.json \
                          --repo /path/to/repo --dry-run

The repo is whatever the suite's "repo" URL points at, cloned locally with both
branches present. Nothing here calls the network; it only shells out to `git`
in the clone you already have.
"""
import argparse
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path


def rev_parse(repo: Path, ref: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(
            f"git rev-parse failed for ref '{ref}' in {repo}:\n{out.stderr.strip()}\n"
            f"Make sure the clone has that branch (git fetch --all)."
        )
    return out.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bug-index", type=Path, required=True, help="Path to a suite's bug_index.json")
    ap.add_argument("--repo", type=Path, required=True, help="Path to a local clone of the suite's repo")
    ap.add_argument("--dry-run", action="store_true", help="Print the resolved SHAs without writing")
    args = ap.parse_args()

    if not args.bug_index.is_file():
        sys.exit(f"No bug_index at {args.bug_index}")
    if not (args.repo / ".git").exists():
        sys.exit(f"{args.repo} is not a git checkout")

    data = json.loads(args.bug_index.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    base_branch = data.get("base_branch")
    buggy_branch = data.get("buggy_branch")
    if not base_branch or not buggy_branch:
        sys.exit("bug_index.json must have base_branch and buggy_branch to pin.")

    base_sha = rev_parse(args.repo, base_branch)
    buggy_sha = rev_parse(args.repo, buggy_branch)
    print(f"base_branch  {base_branch:24} -> {base_sha}")
    print(f"buggy_branch {buggy_branch:24} -> {buggy_sha}")

    if args.dry_run:
        print("(dry run -- not written)")
        return

    # Insert base_commit/buggy_commit right after buggy_branch, preserving order.
    out = OrderedDict()
    for k, v in data.items():
        if k.startswith("_commit_note"):
            continue  # drop the template note if present
        out[k] = v
        if k == "buggy_branch":
            out["base_commit"] = base_sha
            out["buggy_commit"] = buggy_sha
    # If buggy_branch wasn't found as a key for some reason, still set them.
    out.setdefault("base_commit", base_sha)
    out.setdefault("buggy_commit", buggy_sha)

    args.bug_index.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Pinned -> {args.bug_index}")


if __name__ == "__main__":
    main()
