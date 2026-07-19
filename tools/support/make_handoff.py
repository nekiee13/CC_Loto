"""CC_Loto target-local deterministic handoff publisher.

Publishes an immutable validated record before atomically replacing HANDOFF.md,
then appends a canonical event to support/log.md. Install and import this module
from tools/support; all paths resolve beneath the explicit target root. Runtime
dependencies are PyYAML and jsonschema in the support-operator environment.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from _support_shared import scan_sensitive, split_frontmatter

RECORD_ID_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z-[a-f0-9]{7,40}$")
# SHA-1 (40 hex) or SHA-256 (64 hex): the T4/T5 review's non-blocking
# observation about a SHA-1-only pattern is addressed by this target-local
# implementation; SHA-1 and SHA-256 repository formats are both accepted.
HEAD_RE = re.compile(r"^[a-f0-9]{40}$|^[a-f0-9]{64}$")
CHECK_STATES = {"passed", "failed", "skipped", "not-run", "unknown",
                 "not-configured", "unavailable"}
GIT_STATES = {"current", "stale", "absent", "unknown"}
INDEX_STATES = {"current", "stale", "absent", "unknown", "not-configured"}
STATUSES = {"complete", "partial", "blocked"}
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
REQUIRED_HEADINGS = [
    "Objective and scope", "Work completed", "Remaining work", "Decisions",
    "Validation checks", "Git and index state", "Blockers and interrupted risk",
    "Artifacts", "Exact next action", "Follow-up queue",
]
_PATH_UNSAFE_RE = re.compile(r"^[A-Za-z]:|^[\\/]|(^|[\\/])\.\.($|[\\/])")


class PublishError(Exception):
    """Raised when validation fails or publication cannot proceed safely."""


class FaultInjected(Exception):
    """Raised by ``publish`` at a caller-selected checkpoint for fault tests."""


@dataclass
class Check:
    name: str
    state: str
    command: str | None = None
    exit_code: int | None = None
    evidence: str = ""


@dataclass
class GitState:
    state: str
    root: str | None = None
    branch: str | None = None
    head: str | None = None
    upstream_relation: str = ""
    worktree: str = ""


@dataclass
class NextAction:
    owner: str
    action: str
    stop_condition: str
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class HandoffRecord:
    record_id: str
    created_at_utc: str
    source_agent: str
    status: str
    objective: str
    checks: list[Check]
    git_state: GitState
    next_action: NextAction
    index_state: str = "not-configured"
    work_completed: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    follow_up_queue: list[str] = field(default_factory=list)


@dataclass
class PublishResult:
    record_id: str
    record_path: Path
    pointer_path: Path
    log_path: Path
    adopted_existing: bool
    exit_code: int


# --------------------------------------------------------------- Git state

def collect_git_state(root: Path) -> GitState:
    """Collect the actual current Git state of exactly ``root`` without mutating it.

    Contract (T6-R1): the reported state describes the supplied target root
    itself. If ``root`` is not itself a repository root — including when it
    merely sits *inside* some enclosing repository's worktree — the state is
    ``absent``; this function never walks upward and adopts a parent
    repository's identity.
    """
    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                  text=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    top = run("rev-parse", "--show-toplevel")
    if top is None:
        return GitState(state="absent", root=None, branch=None, head=None)
    try:
        if Path(top).resolve() != Path(root).resolve():
            return GitState(state="absent", root=None, branch=None, head=None)
    except OSError:
        return GitState(state="unknown", root=top, branch=None, head=None)
    head = run("rev-parse", "HEAD")
    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    if head is None:
        return GitState(state="unknown", root=top, branch=branch, head=None)
    porcelain = run("status", "--porcelain")
    worktree = "clean" if porcelain == "" else "dirty" if porcelain is not None else "unknown"
    upstream = run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ahead_behind = run("rev-list", "--left-right", "--count", "HEAD...@{u}") if upstream else None
    if upstream is None:
        relation = "no-upstream"
    elif ahead_behind in (None, "0\t0"):
        relation = "synchronized" if ahead_behind == "0\t0" else "unknown"
    else:
        relation = f"ahead-behind:{ahead_behind}"
    return GitState(state="current", root=top, branch=branch, head=head,
                     upstream_relation=relation, worktree=worktree)


def compare_staleness(recorded: GitState, current: GitState) -> list[str]:
    """Field-by-field divergence; never silently normalized.

    Covers every recorded Git fact the T5 contract names: root, branch,
    HEAD, upstream relation, and worktree observation (T6-R3).
    """
    diffs = []
    for name in ("state", "root", "branch", "head", "upstream_relation", "worktree"):
        rv, cv = getattr(recorded, name), getattr(current, name)
        if rv != cv:
            diffs.append(f"{name}: recorded {rv!r} != current {cv!r}")
    return diffs


# --------------------------------------------------------------- validation

def _check_errors(check: Check) -> list[str]:
    errs = []
    if check.state not in CHECK_STATES:
        errs.append(f"check {check.name!r}: invalid state {check.state!r}")
        return errs
    if not check.evidence:
        errs.append(f"check {check.name!r}: evidence is required for every state")
    if check.state == "passed":
        if not check.command:
            errs.append(f"check {check.name!r}: passed requires a non-empty command")
        if check.exit_code != 0:
            errs.append(f"check {check.name!r}: passed requires exit_code 0, "
                        f"got {check.exit_code!r}")
    elif check.state == "failed":
        if not check.command:
            errs.append(f"check {check.name!r}: failed requires a non-empty command")
        if not isinstance(check.exit_code, int) or check.exit_code == 0:
            errs.append(f"check {check.name!r}: failed requires a non-zero integer "
                        f"exit_code, got {check.exit_code!r}")
    else:
        if check.exit_code is not None:
            errs.append(f"check {check.name!r}: {check.state} requires a null exit_code, "
                        f"got {check.exit_code!r}")
    return errs


def _git_state_errors(gs: GitState) -> list[str]:
    errs = []
    if gs.state not in GIT_STATES:
        return [f"git_state: invalid state {gs.state!r}"]
    if gs.state == "absent" and not (gs.root is None and gs.branch is None and gs.head is None):
        errs.append("git_state absent requires null root, branch, and head "
                     "(no fabricated Git identity)")
    if gs.state == "unknown" and gs.head is not None:
        errs.append("git_state unknown requires a null head (no fabricated HEAD)")
    if gs.state in ("current", "stale"):
        if not gs.root:
            errs.append("git_state current/stale requires a non-empty root")
        if not gs.branch:
            errs.append("git_state current/stale requires a non-empty branch")
        if not gs.head or not HEAD_RE.match(gs.head):
            errs.append(f"git_state current/stale requires a full 40- or 64-hex HEAD, "
                        f"got {gs.head!r}")
    return errs


def _path_errors(label: str, paths: list[str]) -> list[str]:
    return [f"{label}: unsafe path {p!r} (absolute or path-traversal)"
            for p in paths if not p or _PATH_UNSAFE_RE.match(p)]


def validate_record(record: HandoffRecord) -> list[str]:
    errs: list[str] = []
    if not RECORD_ID_RE.match(record.record_id):
        errs.append(f"record_id {record.record_id!r} does not match the required pattern")
    if record.source_agent not in {"codex", "claude-code"}:
        errs.append(f"source_agent {record.source_agent!r} is not codex or claude-code")
    if record.status not in STATUSES:
        errs.append(f"status {record.status!r} is not complete, partial, or blocked")
    try:
        datetime.strptime(record.created_at_utc, TS_FMT)
    except (ValueError, TypeError):
        errs.append(f"created_at_utc {record.created_at_utc!r} is not a valid UTC timestamp")
    if not record.objective.strip():
        errs.append("objective must not be empty")
    if record.index_state not in INDEX_STATES:
        errs.append(f"index_state {record.index_state!r} is invalid")
    errs += _git_state_errors(record.git_state)
    for check in record.checks:
        errs += _check_errors(check)
    if record.status == "complete" and any(c.state == "failed" for c in record.checks):
        errs.append("status cannot be complete while a check state is failed "
                    "(never complete with an implied pass)")
    if record.status == "complete" and record.git_state.state in ("absent", "unknown"):
        errs.append("status cannot be complete with git_state absent/unknown; "
                    "use partial or blocked as appropriate")
    na = record.next_action
    if not na.owner.strip():
        errs.append("next_action.owner must not be empty")
    if not na.action.strip():
        errs.append("next_action.action must not be empty")
    if not na.stop_condition.strip():
        errs.append("next_action.stop_condition must not be empty")
    errs += _path_errors("artifacts", record.artifacts)

    rendered = render_record(record)
    hits = scan_sensitive(rendered)
    if hits:
        errs.append(f"sensitive content pattern(s) detected: {', '.join(sorted(set(hits)))}")
    return errs


def normalize_record(record: HandoffRecord) -> dict:
    """The fully normalized object the shipped JSON Schema validates."""
    data = dict(vars(record))
    data["checks"] = [vars(c) for c in record.checks]
    data["git_state"] = vars(record.git_state)
    data["next_action"] = vars(record.next_action)
    return data


def schema_errors(record: HandoffRecord, schema: dict) -> list[str]:
    """Validate the normalized record against the target-local shipped schema."""
    validator = jsonschema.Draft202012Validator(schema)
    return [f"schema: {err.json_path}: {err.message}"
            for err in validator.iter_errors(normalize_record(record))]


def _load_handoff_schema(root: Path) -> dict:
    """Load the target-local ``support/schemas/handoff.schema.json``.

    The schema is a mandatory part of the clone-complete target contract
    (T6-R2b): publication without it is refused rather than degraded to the
    handwritten checks alone. There is deliberately no override parameter
    (T6-R2c) — an external schema path could bypass a stricter installed
    schema, so the installed one is the only authority.
    """
    path = root / "support" / "schemas" / "handoff.schema.json"
    if not path.is_file():
        raise PublishError(f"missing target-local handoff schema: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"unreadable handoff schema {path}: {exc}") from exc


# --------------------------------------------------------------- rendering

def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "(none)"


def render_record(record: HandoffRecord) -> str:
    checks_json = json.dumps([vars(c) for c in record.checks], indent=2)
    git_json = json.dumps({"git_state": vars(record.git_state),
                           "index_state": record.index_state}, indent=2)
    next_action_json = json.dumps(vars(record.next_action), indent=2)
    return (
        "---\n"
        f"record_id: {record.record_id}\n"
        f"created_at_utc: {record.created_at_utc}\n"
        f"source_agent: {record.source_agent}\n"
        f"status: {record.status}\n"
        "---\n\n"
        "# Session handoff\n\n"
        "## Objective and scope\n\n"
        f"{record.objective}\n\n"
        "## Work completed\n\n"
        f"{_bullets(record.work_completed)}\n\n"
        "## Remaining work\n\n"
        f"{_bullets(record.remaining_work)}\n\n"
        "## Decisions\n\n"
        f"{_bullets(record.decisions)}\n\n"
        "## Validation checks\n\n"
        f"```json\n{checks_json}\n```\n\n"
        "## Git and index state\n\n"
        f"```json\n{git_json}\n```\n\n"
        "## Blockers and interrupted risk\n\n"
        f"{_bullets(record.blockers)}\n\n"
        "## Artifacts\n\n"
        f"{_bullets(record.artifacts)}\n\n"
        "## Exact next action\n\n"
        f"```json\n{next_action_json}\n```\n\n"
        "## Follow-up queue\n\n"
        f"{_bullets(record.follow_up_queue)}\n"
    )


def _split_headings(body: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    # parts[0] is preamble ("# Session handoff\n\n"); then alternating heading/content
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        sections[parts[i].strip()] = parts[i + 1].strip()
    return sections


def _parse_bullets(text: str) -> list[str]:
    if text.strip() == "(none)":
        return []
    return [ln[2:].strip() for ln in text.splitlines() if ln.startswith("- ")]


def _parse_json_block(text: str) -> object:
    m = re.search(r"```json\r?\n(.*?)\r?\n```", text, re.DOTALL)
    if not m:
        raise PublishError("missing required ```json block")
    return json.loads(m.group(1))


def parse_record(text: str) -> HandoffRecord:
    """Parse frontmatter and required headings back into a HandoffRecord."""
    try:
        fm, body = split_frontmatter(text)
    except ValueError as exc:
        raise PublishError(f"malformed record: {exc}") from exc

    sections = _split_headings(body)
    missing = [h for h in REQUIRED_HEADINGS if h not in sections]
    if missing:
        raise PublishError(f"missing required heading(s): {', '.join(missing)}")

    try:
        checks_raw = _parse_json_block(sections["Validation checks"])
        checks = [Check(**c) for c in checks_raw]
        git_raw = _parse_json_block(sections["Git and index state"])
        git_state = GitState(**git_raw["git_state"])
        next_action_raw = _parse_json_block(sections["Exact next action"])
        next_action = NextAction(**next_action_raw)
    except (KeyError, TypeError, json.JSONDecodeError, PublishError) as exc:
        raise PublishError(f"malformed structured section: {exc}") from exc

    return HandoffRecord(
        record_id=fm.get("record_id", ""),
        created_at_utc=fm.get("created_at_utc", ""),
        source_agent=fm.get("source_agent", ""),
        status=fm.get("status", ""),
        objective=sections["Objective and scope"],
        checks=checks,
        git_state=git_state,
        index_state=git_raw.get("index_state", "not-configured"),
        next_action=next_action,
        work_completed=_parse_bullets(sections["Work completed"]),
        remaining_work=_parse_bullets(sections["Remaining work"]),
        decisions=_parse_bullets(sections["Decisions"]),
        blockers=_parse_bullets(sections["Blockers and interrupted risk"]),
        artifacts=_parse_bullets(sections["Artifacts"]),
        follow_up_queue=_parse_bullets(sections["Follow-up queue"]),
    )


def render_pointer(record: HandoffRecord, record_relpath: str) -> str:
    return (
        "# Current handoff\n\n"
        f"- Record: [`{record.record_id}`]({record_relpath})\n"
        f"- Published at UTC: `{record.created_at_utc}`\n"
        f"- Source agent: `{record.source_agent}`\n"
        f"- Status: `{record.status}`\n"
        f"- Recorded HEAD: `{record.git_state.head}`\n\n"
        "Validate the immutable record and compare staleness before continuing. This "
        "pointer is replaceable; the referenced record is immutable.\n"
    )


# --------------------------------------------------------------- publication

def _atomic_write(path: Path, text: str, *, no_clobber: bool = False) -> None:
    """Write ``text`` durably, then atomically finalize at ``path``.

    ``no_clobber=True`` (immutable records, T6-R7) finalizes with
    ``os.link``, which fails with FileExistsError if the ID appeared between
    the caller's existence check and this write — an ``os.replace`` there
    would silently overwrite a concurrently published record. The
    replaceable pointer keeps ``os.replace`` semantics.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    if no_clobber:
        try:
            os.link(tmp, path)
        finally:
            os.unlink(tmp)
    else:
        os.replace(tmp, path)


def publish(root: Path, record: HandoffRecord, *, fault_at: str | None = None) -> PublishResult:
    """Run the T5 deterministic publication protocol against ``root``.

    Publication requires BOTH the handwritten semantic checks and the
    target-local shipped ``support/schemas/handoff.schema.json`` to accept
    the fully normalized record; either verdict alone cannot publish
    (T6-R2b). The installed schema cannot be overridden from outside the
    target (T6-R2c).

    ``fault_at`` simulates an interruption at a named checkpoint for tests:
    ``"before-record-write"``, ``"after-record-before-pointer"``, or
    ``"after-pointer-before-log"``. A prior call that faulted after the record
    was written may be retried; an identical record is adopted, not rewritten.
    """
    errors = validate_record(record)
    if errors:
        raise PublishError("validation failed:\n" + "\n".join(errors))
    schema = _load_handoff_schema(root)
    errors = schema_errors(record, schema)
    if errors:
        raise PublishError("schema validation failed:\n" + "\n".join(errors))

    handoffs_dir = root / "support" / "handoffs"
    record_path = handoffs_dir / f"{record.record_id}.md"
    pointer_path = root / "HANDOFF.md"
    log_path = root / "support" / "log.md"
    rendered = render_record(record)

    adopted = False
    if record_path.is_file():
        if record_path.read_text(encoding="utf-8") == rendered:
            adopted = True
        else:
            raise PublishError(f"record id {record.record_id!r} already exists with "
                               "different content; immutable records are never overwritten")

    if fault_at == "before-record-write":
        raise FaultInjected("interrupted before record publish")

    if not adopted:
        try:
            _atomic_write(record_path, rendered, no_clobber=True)
        except FileExistsError:
            # A same-ID record landed between the existence check above and
            # finalization. Adopt it only if byte-identical; never overwrite.
            if record_path.read_text(encoding="utf-8") == rendered:
                adopted = True
            else:
                raise PublishError(
                    f"record id {record.record_id!r} was published concurrently with "
                    "different content; immutable records are never overwritten") from None

    if fault_at == "after-record-before-pointer":
        raise FaultInjected("interrupted between record and pointer")

    record_relpath = str(Path("support") / "handoffs" / f"{record.record_id}.md")
    pointer_text = render_pointer(record, record_relpath.replace("\\", "/"))
    _atomic_write(pointer_path, pointer_text)

    if fault_at == "after-pointer-before-log":
        raise FaultInjected("interrupted after pointer, before log")

    stamp = datetime.now(timezone.utc).strftime(TS_FMT)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(
            f"handoff-published | {stamp} | {record.record_id} | "
            f"Immutable handoff published; status {record.status}; "
            f"HANDOFF.md updated | {record.source_agent}\n"
        )

    # Re-open and validate record/pointer identity (step 9).
    reread = parse_record(record_path.read_text(encoding="utf-8"))
    if reread.record_id != record.record_id or reread.status != record.status:
        raise PublishError("post-publication identity check failed")
    if record.record_id not in pointer_path.read_text(encoding="utf-8"):
        raise PublishError("pointer does not reference the published record id")

    return PublishResult(record_id=record.record_id, record_path=record_path,
                         pointer_path=pointer_path, log_path=log_path,
                         adopted_existing=adopted, exit_code=0)
