"""Shared target-local helpers for portable CC_Loto support tools.

Slice 2 installs ``agent_coord.py`` under the existing ``tools/support``
convention; the handoff slice adds its second consumer there.
"""

from __future__ import annotations

import re

import yaml

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


class _StringTimestampLoader(yaml.SafeLoader):
    """SafeLoader that leaves ISO-timestamp-shaped scalars as plain strings.

    PyYAML's default resolvers implicitly tag bare ``2026-07-17T02:00:00Z``
    scalars as ``tag:yaml.org,2002:timestamp`` and hand back a ``datetime``.
    Every record schema in this contract declares those fields as JSON
    strings; silently accepting a datetime would either crash formatting or
    (worse) let a non-string slip past schema validation. Removing the
    timestamp resolver keeps every scalar a string unless explicitly tagged.
    """


_StringTimestampLoader.yaml_implicit_resolvers = {
    key: [r for r in resolvers if r[0] != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(text: str) -> object:
    return yaml.load(text, Loader=_StringTimestampLoader)

# Each pattern is deliberately narrow: the goal is to catch credential-shaped
# and private-path-shaped content per the T5 sensitive-data boundary, not to
# be a general-purpose secret scanner.
SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key pattern"),
    (re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
     "private key block"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*"
                r"['\"]?[A-Za-z0-9_\-/+=]{6,}"),
     "credential-shaped key=value"),
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+"), "private absolute user path"),
    (re.compile(r"/home/[^/\s]+/"), "private absolute user path"),
]


class FrontmatterError(ValueError):
    """Raised when a record's frontmatter block is missing or malformed."""


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return ``(frontmatter_mapping, body)``; raise FrontmatterError on defect."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise FrontmatterError("missing frontmatter block")
    try:
        data = load_yaml(m.group(1))
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"malformed frontmatter YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter is not a mapping")
    return data, text[m.end():]


def scan_sensitive(text: str) -> list[str]:
    """Return the distinct labels of every prohibited pattern found in text."""
    return [label for pattern, label in SENSITIVE_PATTERNS if pattern.search(text)]
