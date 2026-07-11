"""scrub.py -- strip memorization "tells" out of a diff before it reaches the reviewer.

Why this exists
---------------
A benchmark built on real CVEs has one honest weakness: a model can "catch" a
known bug because it read the public write-up during training, not because it
reasoned about the code in front of it. That's recall, not review, and it
inflates scores in a way that doesn't survive contact with a novel bug.

The single easiest way a diff leaks the answer is by *naming it*: a `CVE-2023-...`
in a comment, a link to an NVD/GHSA advisory, a commit-message-style
"SECURITY FIX: patch XSS in ..." line that got committed onto the buggy branch.
`scrub_diff` removes those tells so the model has to look at the code, not the
label. It does NOT touch actual source logic -- it only redacts identifiers,
advisory URLs, and comment lines that announce a security fix.

This is deliberately conservative. It would rather leave a borderline comment in
than risk deleting a line of real code and changing what the diff means. It is
importable so the main runner can apply it (runner.py --scrub) and so the
negative-control runner can apply it to every case.

    from anti_cheat.scrub import scrub_diff
    clean, removed = scrub_diff(diff_text)
"""
import re

# Vulnerability identifiers that hand the model the answer key.
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{1,7}\b", re.IGNORECASE)
GHSA_RE = re.compile(r"\bGHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}\b", re.IGNORECASE)
CWE_RE = re.compile(r"\bCWE-\d{1,4}\b", re.IGNORECASE)

# Advisory / write-up URLs. If any of these hosts appear in a token, redact the
# whole URL token -- the path itself often spells out the vulnerability.
ADVISORY_HOSTS = (
    "nvd.nist.gov",
    "cve.mitre.org",
    "cve.org",
    "github.com/advisories",
    "github.com/.*?/security/advisories",
    "githubusercontent.com/.*?advisor",
    "snyk.io",
    "security.snyk.io",
    "huntr.dev",
    "huntr.com",
    "osv.dev",
    "exploit-db.com",
    "packetstormsecurity",
)
ADVISORY_URL_RE = re.compile(
    r"https?://\S*(?:" + "|".join(ADVISORY_HOSTS) + r")\S*", re.IGNORECASE
)

# A comment LINE (not code) that announces a security fix/vuln. We only strip a
# line when it is a comment AND it reads like an advisory note, so we never drop
# executable code. Comment leaders across the languages the suites use.
_COMMENT_LEADERS = (r"#", r"//", r"/\*", r"\*", r"<!--", r"--")
_COMMENT_LEAD_RE = re.compile(r"^\s*(?:" + "|".join(_COMMENT_LEADERS) + r")")

# Phrases that mark a comment as "this line is telling the reviewer the answer".
_ANNOUNCE_RE = re.compile(
    r"\b(?:security[ -]?fix|vuln(?:erability)?|exploit|advisory|"
    r"remote code execution|\brce\b|arbitrary code|"
    r"sql[ -]?injection|xss|cross[ -]site|ssrf|xxe|"
    r"path traversal|directory traversal|deserial|"
    r"patch(?:ed|es)?\s+(?:for\s+)?(?:the\s+)?(?:cve|vuln|security)|"
    r"fixes?\s+(?:cve|ghsa|vuln|security))\b",
    re.IGNORECASE,
)

REDACTION = "[redacted]"


def _is_diff_meta(line: str) -> bool:
    """diff/patch metadata lines we must never delete (they define structure)."""
    return (
        line.startswith("diff ")
        or line.startswith("index ")
        or line.startswith("@@")
        or line.startswith("--- ")
        or line.startswith("+++ ")
        or line.startswith("rename ")
        or line.startswith("similarity ")
        or line.startswith("new file")
        or line.startswith("deleted file")
    )


def _strip_diff_prefix(line: str):
    """Return (prefix, body) so we can inspect a diff line's payload without the
    leading +/-/space. Non-diff text returns ('', line)."""
    if line[:1] in ("+", "-", " ") and not line.startswith(("+++", "---")):
        return line[0], line[1:]
    return "", line


def scrub_diff(text: str):
    """Redact CVE/GHSA/CWE identifiers and advisory URLs inline, and drop
    comment lines that announce a security fix.

    Returns (cleaned_text, removed) where `removed` is a list of short strings
    describing what was taken out, so a run can log exactly what was scrubbed
    (transparency: a reviewer of the *benchmark* can audit that only tells, not
    logic, were removed).
    """
    if not text:
        return text, []

    removed = []
    out_lines = []

    for line in text.splitlines():
        if _is_diff_meta(line):
            out_lines.append(line)
            continue

        prefix, body = _strip_diff_prefix(line)

        # 1) Drop an added/context comment line that literally announces a fix.
        #    Only for '+' (introduced) or ' ' (context) lines, and only if it is
        #    a comment -- never a removed '-' line (that changes the diff's
        #    meaning) and never real code.
        if prefix in ("+", " ") and _COMMENT_LEAD_RE.match(body) and _ANNOUNCE_RE.search(body):
            removed.append(f"comment: {body.strip()[:80]}")
            # Keep the line slot as an empty comment so line offsets don't shift
            # in a way that confuses a reviewer counting lines; use the body's
            # own comment leader.
            lead = _COMMENT_LEAD_RE.match(body).group(0)
            out_lines.append(f"{prefix}{lead} {REDACTION}")
            continue

        # 2) Inline-redact identifiers and advisory URLs anywhere on the line.
        new_body = body
        for rx, label in ((CVE_RE, "CVE id"), (GHSA_RE, "GHSA id"),
                          (CWE_RE, "CWE id"), (ADVISORY_URL_RE, "advisory URL")):
            def _repl(m):
                removed.append(f"{label}: {m.group(0)[:80]}")
                return REDACTION
            new_body = rx.sub(_repl, new_body)

        out_lines.append(f"{prefix}{new_body}")

    cleaned = "\n".join(out_lines)
    # Preserve a trailing newline if the input had one.
    if text.endswith("\n"):
        cleaned += "\n"
    return cleaned, removed


if __name__ == "__main__":
    import sys
    src = sys.stdin.read() if not sys.argv[1:] else open(sys.argv[1], encoding="utf-8").read()
    clean, removed = scrub_diff(src)
    sys.stderr.write(f"# scrubbed {len(removed)} tell(s):\n")
    for r in removed:
        sys.stderr.write(f"#   - {r}\n")
    sys.stdout.write(clean)
