"""AST-based bug injection for the Chaos Audit validation.

Parses a Python file, applies ONE semantic mutation at a time, and unparses. Because
we mutate the syntax tree and regenerate code, every mutant is syntactically valid --
that's what lets this run on code we've never seen (no hand-authored patches like the
curated suites). Each mutation is a known bug with a known change.

Mutations (all classic mutation-testing operators, all likely to change behavior):
  compare_swap   >  <-> >= , <  <-> <= , == <-> != , is <-> is not
  boolop_flip    and <-> or
  drop_not       remove a `not`
  guard_removed  delete an `if <cond>: raise/return` guard clause (the "authz check" case)

To keep each mutant a CLEAN one-change diff, we unparse BOTH the original tree and the
mutated tree and diff those (ast.unparse reformats, so diffing raw-source vs unparsed
would be all noise). The reviewed code is therefore the unparsed form -- valid and
equivalent, but without original comments/formatting. Fine for validation.

Caveat: some mutations are "equivalent" (no behavior change); we target sites likely
to matter but can't prove it without the repo's tests. We at least drop mutants whose
unparsed text is identical to the baseline.
"""
import ast
import difflib

_CMP_SWAP = {
    ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}


def _is_guard(node) -> bool:
    # `if <cond>: raise/return` with no elif/else -> a guard clause.
    return (isinstance(node, ast.If) and not node.orelse
            and len(node.body) == 1 and isinstance(node.body[0], (ast.Raise, ast.Return)))


class _Mut(ast.NodeTransformer):
    """Walks eligible sites in a fixed order; if target == the site's index, mutate
    that one and record it. target=-1 just counts (self.count = total sites)."""

    def __init__(self, target: int):
        self.target = target
        self.count = 0
        self.applied = None

    def _hit(self) -> bool:
        idx = self.count
        self.count += 1
        return idx == self.target

    def visit_Compare(self, node):
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            if type(op) in _CMP_SWAP and self._hit():
                old = type(op).__name__
                node.ops[i] = _CMP_SWAP[type(op)]()
                self.applied = ("compare_swap", f"{old} -> {type(node.ops[i]).__name__}")
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, (ast.And, ast.Or)) and self._hit():
            old = type(node.op).__name__
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            self.applied = ("boolop_flip", f"{old} -> {type(node.op).__name__}")
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit():
            self.applied = ("drop_not", "removed 'not'")
            return node.operand
        return node

    def visit_If(self, node):
        self.generic_visit(node)
        if _is_guard(node) and self._hit():
            self.applied = ("guard_removed", "removed guard clause")
            return None  # delete the guard statement
        return node


def _count_sites(src: str) -> int:
    m = _Mut(target=-1)
    m.visit(ast.parse(src))
    return m.count


def generate_mutations(src: str, filename: str = "<file>") -> list[dict]:
    """One dict per mutation: {file, type, detail, diff}. `diff` is a clean unified
    diff containing only the injected change."""
    baseline = ast.unparse(ast.parse(src))
    base_lines = baseline.splitlines(keepends=True)
    out = []
    for k in range(_count_sites(src)):
        tree = _Mut(target=k)
        new = tree.visit(ast.parse(src))
        if not tree.applied:
            continue
        ast.fix_missing_locations(new)
        try:
            mutated = ast.unparse(new)
        except Exception:
            continue
        if mutated == baseline:
            continue  # no textual change -> skip
        kind, detail = tree.applied
        diff = "".join(difflib.unified_diff(
            base_lines, mutated.splitlines(keepends=True),
            fromfile=f"a/{filename}", tofile=f"b/{filename}", n=3))
        out.append({"file": filename, "type": kind, "detail": detail, "diff": diff})
    return out


if __name__ == "__main__":
    import sys
    src = open(sys.argv[1], encoding="utf-8").read()
    muts = generate_mutations(src, sys.argv[1])
    print(f"{len(muts)} mutation(s):")
    for i, mu in enumerate(muts):
        print(f"\n--- [{i}] {mu['type']}: {mu['detail']} ---")
        print(mu["diff"].rstrip())
