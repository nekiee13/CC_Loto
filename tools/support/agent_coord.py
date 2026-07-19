"""CC_Loto target-local coordination validator and BOARD renderer.

Run from the repository root as ``python tools/support/agent_coord.py .``.
BOARD.md is generated state, never authority. Before the handoff slice, the
board truthfully reports ``HANDOFF.md missing``. Runtime dependencies are
PyYAML and jsonschema in addition to the standard library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import yaml

from _support_shared import FrontmatterError, load_yaml, scan_sensitive, split_frontmatter

PREFIXES = {"CX": "codex", "CC": "claude-code"}
AGENT_PREFIX = {v: k for k, v in PREFIXES.items()}
DISPOSITIONS = {"resolved", "owner-accepted", "deferred-until"}
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def exit_code(self) -> int:
        return 1 if self.errors else 0


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), TS_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_schema(schemas_dir: Path, filename: str) -> dict:
    path = schemas_dir / filename
    if not path.is_file():
        raise FileNotFoundError(f"missing required schema: coordination/schemas/{filename}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_records(directory: Path, errors: list[str], *, is_yml: bool) -> list[dict]:
    records: list[dict] = []
    if not directory.is_dir():
        return records
    pattern = "*.yml" if is_yml else "*.md"
    for path in sorted(directory.glob(pattern)):
        # Queue README.md files are tracked placeholders, not records.
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        try:
            if is_yml:
                data = load_yaml(text) or {}
                if not isinstance(data, dict):
                    raise FrontmatterError("claim file is not a mapping")
                body = ""
            else:
                data, body = split_frontmatter(text)
        except (FrontmatterError, yaml.YAMLError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        data["_path"] = path
        data["_body"] = body
        records.append(data)
    return records


def _is_manifest(path: Path) -> bool:
    return "manifest" in path.stem.lower()


def _paths_overlap(a: str, b: str) -> bool:
    """True when the claim paths collide by exact match or ancestor/descendant
    scope (T4 claim contract, T6-R4). Separators are normalized so
    ``doc\\x`` and ``doc/x`` compare equal."""
    pa = [p for p in a.replace("\\", "/").strip("/").split("/") if p]
    pb = [p for p in b.replace("\\", "/").strip("/").split("/") if p]
    shorter, longer = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    return longer[:len(shorter)] == shorter


def _public_fields(record: dict) -> dict:
    """Strip internal ``_path``/``_body`` tracking keys before schema validation.

    The schemas use ``additionalProperties: false``; validating the raw
    loader dict (which carries these two loader-only keys) would reject
    every record.
    """
    return {k: v for k, v in record.items() if not k.startswith("_")}


def validate(root: Path) -> ValidationResult:
    result = ValidationResult()
    coord = root / "coordination"
    schemas_dir = coord / "schemas"

    try:
        message_schema = _load_schema(schemas_dir, "message.schema.json")
        claim_schema = _load_schema(schemas_dir, "claim.schema.json")
        manifest_schema = _load_schema(schemas_dir, "resolution-manifest.schema.json")
    except FileNotFoundError as exc:
        result.errors.append(str(exc))
        return result

    active = _load_records(coord / "messages", result.errors, is_yml=False)
    archived = _load_records(coord / "archive", result.errors, is_yml=False)
    all_messages = active + archived

    # --- malformed/duplicate IDs, filenames, timestamps, prefixes, types,
    #     paths (schema-enforced), or unknown fields (schema-enforced) -----
    seen_ids: dict[str, str] = {}
    manifests: dict[str, dict] = {}
    edges: dict[str, str] = {}
    for msg in all_messages:
        path: Path = msg["_path"]
        name = path.name
        if _is_manifest(path):
            try:
                jsonschema.validate(_public_fields(msg), manifest_schema)
            except jsonschema.ValidationError as exc:
                result.errors.append(f"{name}: resolution manifest schema violation: "
                                      f"{exc.message}")
                continue
            manifests[name] = msg
            continue

        try:
            jsonschema.validate(_public_fields(msg), message_schema)
        except jsonschema.ValidationError as exc:
            result.errors.append(f"{name}: message schema violation: {exc.message}")
            continue

        mid = msg["message_id"]
        if mid != path.stem:
            result.errors.append(f"{name}: message_id does not match filename")
        if mid in seen_ids:
            result.errors.append(f"{name}: duplicate message_id (also {seen_ids[mid]})")
        seen_ids[mid] = name
        if _parse_ts(msg.get("created_at_utc")) is None:
            result.errors.append(f"{name}: invalid created_at_utc")
        reply_to = msg.get("reply_to")
        if reply_to:
            edges[mid] = reply_to

    known_ids = set(seen_ids)

    # --- unresolved reply_to, self-reply, or reply cycles ------------------
    for mid, target in edges.items():
        if mid == target:
            result.errors.append(f"{seen_ids[mid]}: self-reply ({mid})")
            continue
        if target not in known_ids:
            result.errors.append(f"{seen_ids[mid]}: reply_to {target!r} not found in "
                                  "messages/ or archive/")
            continue
        seen, cur = {mid}, target
        while cur in edges:
            cur = edges[cur]
            if cur in seen:
                result.errors.append(f"{seen_ids[mid]}: reply_to cycle detected at {cur!r}")
                break
            seen.add(cur)

    # --- unacknowledged active blockers / one-sided synchronization -------
    replied_ids = set(edges.values())
    for msg in active:
        if _is_manifest(msg["_path"]):
            continue
        mid = msg.get("message_id")
        if msg.get("type") == "blocker" and mid not in replied_ids:
            result.errors.append(f"{msg['_path'].name}: unacknowledged active blocker")
        if "both agents synchronized" in msg.get("_body", "").lower() \
                and mid not in replied_ids:
            # T4 contract: one-sided synchronization claims are a validator
            # failure, not advisory (T6-R4).
            result.errors.append(f"{msg['_path'].name}: claims synchronization without "
                                  "a confirming reply from the other agent")

    # --- cross-agent archival / record-prefix ownership violations, and
    #     missing/malformed resolution manifests or manifests referencing
    #     active/missing records --------------------------------------------
    active_ids = {m.get("message_id") for m in active if not _is_manifest(m["_path"])}
    for msg in archived:
        path = msg["_path"]
        if _is_manifest(path):
            continue
        mid = msg.get("message_id", path.stem)
        prefix = path.name[:2]
        covering = [
            name for name, man in manifests.items()
            if name.startswith(prefix)
            and any(entry.get("message_id") == mid
                    for entry in man.get("resolved_messages", []))
        ]
        if not covering:
            result.errors.append(f"archive/{path.name}: no same-prefix resolution manifest "
                                  "references it")
            continue
        for name in covering:
            man = manifests[name]
            if man.get("resolved_by") != PREFIXES.get(prefix):
                result.errors.append(
                    f"archive/{name}: resolved_by {man.get('resolved_by')!r} "
                    f"does not own archive/{path.name}'s prefix {prefix!r} "
                    "(cross-agent archival)")
            entry = next(e for e in man.get("resolved_messages", [])
                         if e.get("message_id") == mid)
            if msg.get("type") == "blocker" and entry.get("disposition") not in DISPOSITIONS:
                result.errors.append(f"archive/{path.name}: archived blocker without an "
                                      "allowed disposition")

    for name, man in manifests.items():
        for entry in man.get("resolved_messages", []):
            eid = entry.get("message_id")
            if eid in active_ids:
                result.errors.append(f"archive/{name}: references active (unarchived) "
                                      f"message {eid!r}")
            elif eid not in known_ids:
                result.errors.append(f"archive/{name}: references unknown message {eid!r}")

    # --- overlapping active claims, invalid renewal/release order, or
    #     inconsistent expiry ----------------------------------------------
    now = datetime.now(timezone.utc)
    claims = _load_records(coord / "claims", result.errors, is_yml=True)
    validated_claims = []
    for claim in claims:
        name = claim["_path"].name
        try:
            jsonschema.validate(_public_fields(claim), claim_schema)
        except jsonschema.ValidationError as exc:
            result.errors.append(f"claims/{name}: claim schema violation: {exc.message}")
            continue
        claimed = _parse_ts(claim.get("claimed_at_utc"))
        renewed = _parse_ts(claim.get("last_renewed_at_utc"))
        expires = _parse_ts(claim.get("expires_at_utc"))
        if claimed and renewed and renewed < claimed:
            result.errors.append(f"claims/{name}: last_renewed_at_utc precedes "
                                  "claimed_at_utc (invalid renewal order)")
        if renewed and expires and expires <= renewed:
            result.errors.append(f"claims/{name}: expires_at_utc does not follow "
                                  "last_renewed_at_utc (inconsistent expiry)")
        if claim.get("status") == "released":
            released = _parse_ts(claim.get("released_at_utc"))
            if claimed and released and released < claimed:
                result.errors.append(f"claims/{name}: released_at_utc precedes "
                                      "claimed_at_utc (invalid release order)")
        validated_claims.append(claim)

    def _is_active(c: dict) -> bool:
        if c.get("status") != "active":
            return False
        expires = _parse_ts(c.get("expires_at_utc"))
        return expires is None or expires > now

    active_claims = [c for c in validated_claims if _is_active(c)]
    for i, a in enumerate(active_claims):
        for b in active_claims[i + 1:]:
            if a.get("agent") == b.get("agent"):
                continue
            if a.get("task") == b.get("task"):
                result.errors.append(f"claims: {a.get('task')} actively claimed by "
                                      "both agents")
            overlap = sorted(
                f"{pa} ~ {pb}"
                for pa in a.get("anticipated_files", [])
                for pb in b.get("anticipated_files", [])
                if _paths_overlap(str(pa), str(pb)))
            if overlap:
                result.errors.append(f"claims: {a.get('task')} and {b.get('task')} "
                                      f"overlap on {overlap}")

    # --- prohibited sensitive content patterns ------------------------------
    for msg in all_messages:
        hits = scan_sensitive(msg.get("_body", ""))
        note = msg.get("note", "")
        if isinstance(note, str):
            hits += scan_sensitive(note)
        if hits:
            result.errors.append(f"{msg['_path'].name}: prohibited content pattern(s): "
                                  f"{', '.join(sorted(set(hits)))}")
    for claim in validated_claims:
        hits = scan_sensitive(str(claim.get("note", "")))
        if hits:
            result.errors.append(f"claims/{claim['_path'].name}: prohibited content "
                                  f"pattern(s): {', '.join(sorted(set(hits)))}")

    # --- stale/generated-board differences ---------------------------------
    board_path = coord / "BOARD.md"
    expected = render_board(root)
    if not board_path.is_file():
        result.errors.append("coordination/BOARD.md missing "
                              "(regenerate with render_board)")
    elif _strip_stamp(board_path.read_text(encoding="utf-8")).rstrip() \
            != _strip_stamp(expected).rstrip():
        result.errors.append("coordination/BOARD.md is stale (regenerate with render_board)")

    return result


def _strip_stamp(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.startswith("Generated: ")]
    return "\n".join(lines)


def render_board(root: Path) -> str:
    """Render the generated board body for ``root``; never hand-edit the output."""
    coord = root / "coordination"
    errors: list[str] = []
    active = [m for m in _load_records(coord / "messages", errors, is_yml=False)
              if not _is_manifest(m["_path"])]
    claims = _load_records(coord / "claims", errors, is_yml=True)
    now = datetime.now(timezone.utc)

    def _is_active(c: dict) -> bool:
        if c.get("status") != "active":
            return False
        expires = _parse_ts(c.get("expires_at_utc"))
        return expires is None or expires > now

    active_claims = sorted((c for c in claims if _is_active(c)),
                            key=lambda c: str(c.get("task", "")))
    released_claims = sorted((c for c in claims if c.get("status") == "released"),
                              key=lambda c: str(c.get("task", "")))
    archived_count = sum(1 for p in (coord / "archive").glob("*.md")
                         if p.name != "README.md") \
        if (coord / "archive").is_dir() else 0

    lines = ["# BOARD (generated)", "",
             "Generated by agent_coord.render_board. Never hand-edit; never "
             "treat as authoritative history.", "", "## Active claims", ""]
    lines += [f"- `{c.get('task', '?')}` — {c.get('agent', '?')}, expires "
              f"{c.get('expires_at_utc', '?')}" for c in active_claims] or ["- none"]
    if released_claims:
        lines += ["", "## Released claims", ""]
        lines += [f"- `{c.get('task', '?')}` — {c.get('agent', '?')}, released "
                  f"{c.get('released_at_utc', '?')}" for c in released_claims]
    lines += ["", "## Active messages", ""]
    lines += [f"- `{m.get('message_id', m['_path'].stem)}` — {m.get('type', '?')}, "
              f"{m.get('from_agent', '?')} -> {m.get('to_agent', '?')}: "
              f"{m.get('task', '')}" for m in active] or ["- none"]
    # T4 board contract: the board also names the current handoff pointer
    # (T6-R5). The board reports, never interprets, the pointer.
    pointer_line = "HANDOFF.md missing"
    handoff_pointer = root / "HANDOFF.md"
    if handoff_pointer.is_file():
        for ln in handoff_pointer.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("- Record:"):
                pointer_line = ln.strip()[2:]
                break
        else:
            pointer_line = "HANDOFF.md present but names no record"
    lines += ["", "## Pointers", "", f"- {pointer_line}",
              f"- Archive: {archived_count} records in `coordination/archive/`", ""]
    return "\n".join(lines)


def write_board(root: Path, *, timestamp: str | None = None) -> Path:
    board_path = root / "coordination" / "BOARD.md"
    stamp = timestamp or datetime.now(timezone.utc).strftime(TS_FMT)
    if _parse_ts(stamp) is None:
        raise ValueError("timestamp must use YYYY-MM-DDTHH:MM:SSZ")
    board_path.write_text(render_board(root) + f"\nGenerated: {stamp}\n", encoding="utf-8", newline="\n")
    return board_path


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="target repository root")
    parser.add_argument("--write-board", action="store_true",
                         help="regenerate coordination/BOARD.md before validating")
    parser.add_argument("--timestamp",
                         help="fixed UTC timestamp for deterministic BOARD generation")
    args = parser.parse_args(argv)

    if args.write_board:
        write_board(args.root, timestamp=args.timestamp)
    result = validate(args.root)
    for w in result.warnings:
        print(f"WARN : {w}")
    for e in result.errors:
        print(f"ERROR: {e}", file=sys.stderr)
    print(f"validate: {len(result.errors)} error(s), {len(result.warnings)} warning(s)")
    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
