"""Project discovery, configuration, records, and deterministic ID allocation.

All persistent state lives in Markdown/YAML files.  This module only reads and
writes those files; it never performs scientific interpretation.
"""
from __future__ import annotations

import datetime
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import yaml

CONFIG_NAME = ".sci.yaml"
SUPPORTED_SCHEMA_VERSION = 1

# ID allocation is permanent.  Every ID ever handed out by ``sci new`` gets a
# claim file here, so deleting a record (or cloning a project) can never cause
# the same ID to be reused for a different scientific object.
ID_CLAIMS_DIR = ".sci/ids"

KINDS: Tuple[str, ...] = ("question", "exploration", "experiment", "decision")

ID_PREFIX: Dict[str, str] = {
    "question": "Q",
    "exploration": "X",
    "experiment": "EXP",
    "decision": "D",
}

STATUS_VALUES: Dict[str, Tuple[str, ...]] = {
    "question": ("open", "answered", "dropped"),
    "exploration": ("active", "paused", "completed", "dropped"),
    "experiment": ("planned", "running", "completed", "abandoned"),
    "decision": ("active", "superseded", "rejected"),
}

REQUIRED_RECORD_FIELDS: Tuple[str, ...] = ("id", "title", "status", "created")

REQUIRED_PATH_KEYS: Tuple[str, ...] = (
    "charter",
    "state",
    "questions",
    "decisions",
    "explorations",
    "experiments",
)

FILE_PATH_KEYS: Tuple[str, ...] = ("charter", "state")

DIRECTORY_PATH_KEYS: Tuple[str, ...] = (
    "questions",
    "decisions",
    "explorations",
    "experiments",
)

# Reference fields that must point at an existing record, per record kind.
# ``supersedes`` is handled separately because it must also point backwards.
REFERENCE_FIELDS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "exploration": (("question", "question"),),
    "experiment": (("question", "question"), ("exploration", "exploration")),
    "decision": (("question", "question"), ("experiment", "experiment")),
}

# Provenance list fields. ``evidence`` records which scientific observations or
# tests were reviewed for a Decision. ``motivated_by`` records which existing
# Decisions motivated a new Exploration or Experiment. These are the only
# relationships added in this iteration; no new object type is introduced.
EVIDENCE_KINDS: Tuple[str, ...] = ("exploration", "experiment")
MOTIVATED_BY_KINDS: Tuple[str, ...] = ("decision",)


@dataclass(frozen=True)
class Relation:
    """A provenance edge declared in record front matter."""

    name: str
    sources: Tuple[str, ...]
    targets: Tuple[str, ...]
    inverse: str


# The relation registry is the single declaration of the provenance graph.
# ``sci show --related`` uses it for forward links and reverse traversal; new
# relations should be added here rather than hard-coded in each command.
RELATIONS: Tuple[Relation, ...] = (
    Relation(
        name="question",
        sources=("exploration", "experiment", "decision"),
        targets=("question",),
        inverse="questions",
    ),
    Relation(
        name="exploration",
        sources=("experiment",),
        targets=("exploration",),
        inverse="experiments",
    ),
    Relation(
        name="evidence",
        sources=("decision",),
        targets=("exploration", "experiment"),
        inverse="evidenced_by",
    ),
    Relation(
        # Legacy v0.1 Decision field; new decisions record it as evidence.
        name="experiment",
        sources=("decision",),
        targets=("experiment",),
        inverse="evidence_for",
    ),
    Relation(
        name="motivated_by",
        sources=("exploration", "experiment"),
        targets=("decision",),
        inverse="motivated",
    ),
    Relation(
        name="supersedes",
        sources=("decision",),
        targets=("decision",),
        inverse="superseded_by",
    ),
)

# Directories created by ``sci init`` even when the scaffold has no files
# that require them.
REQUIRED_DIRECTORIES: Tuple[str, ...] = (
    "docs",
    "docs/questions",
    "docs/decisions",
    "data",
    "explorations",
    "experiments",
    "outputs",
    "outputs/explorations",
    "outputs/experiments",
    "src",
    "scripts",
    "tests",
    ID_CLAIMS_DIR,
)

# Directories that have no files of their own.  Git does not track empty
# directories, so each one gets a ``.gitkeep``; otherwise a freshly cloned
# project would be missing the directories that ``sci validate`` requires.
TRACKED_EMPTY_DIRECTORIES: Tuple[str, ...] = (
    "docs/questions",
    "docs/decisions",
    "explorations",
    "experiments",
    "src",
    "scripts",
    "tests",
    ID_CLAIMS_DIR,
)

DEFAULT_PATHS: Dict[str, str] = {
    "charter": "docs/CHARTER.md",
    "state": "docs/STATE.md",
    "questions": "docs/questions",
    "decisions": "docs/decisions",
    "explorations": "explorations",
    "experiments": "experiments",
}

_FRONT_MATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)


class ProjectError(Exception):
    """A deterministic, user-facing error in project structure or usage."""


@dataclass
class Record:
    """A scientific record parsed from Markdown/YAML files."""

    kind: str
    id: str
    title: str
    status: str
    created: str
    path: Path
    data: Dict[str, Any]


def find_project_root(start: Path) -> Path:
    """Walk upwards from *start* until a ``.sci.yaml`` is found."""
    candidate = Path(start).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate,) + tuple(candidate.parents):
        if (directory / CONFIG_NAME).is_file():
            return directory
    raise ProjectError(
        "no {} found in {} or any parent directory "
        "(run `sci init` to create a project)".format(CONFIG_NAME, candidate)
    )


def load_config(root: Path) -> Dict[str, Any]:
    """Load and parse ``.sci.yaml``."""
    path = Path(root) / CONFIG_NAME
    if not path.is_file():
        raise ProjectError("missing {} in {}".format(CONFIG_NAME, root))
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProjectError("cannot parse {}: {}".format(CONFIG_NAME, exc)) from exc
    if not isinstance(data, dict):
        raise ProjectError("{} must contain a YAML mapping".format(CONFIG_NAME))
    return data


def resolve_project_path(root: Path, value: Any, label: str = "path") -> Path:
    """Resolve a configured project-relative path without escaping the root.

    Rejects empty values, absolute paths (Unix, Windows drive, UNC), ``~``
    expansion, explicit ``..`` traversal, and symlinks whose resolved target
    leaves the project root.  Returns the resolved path, which is guaranteed
    to be inside the resolved project root.
    """
    root_resolved = Path(root).expanduser().resolve()
    if not isinstance(value, str) or not value.strip():
        raise ProjectError("{} must be a non-empty string".format(label))
    text = value.strip()
    if text.startswith(("~", "/", "\\")):
        raise ProjectError(
            "{} must be project-relative, got {!r}".format(label, value)
        )
    if re.match(r"^[A-Za-z]:[\\/]", text):
        raise ProjectError(
            "{} must be project-relative, got {!r}".format(label, value)
        )
    normalized = text.replace("\\", "/")
    if ".." in PurePosixPath(normalized).parts:
        raise ProjectError(
            "{} must not contain '..' path traversal: {!r}".format(label, value)
        )
    resolved = (root_resolved / normalized).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise ProjectError(
            "{} escapes the project root: {!r}".format(label, value)
        )
    return resolved


def config_path(root: Path, key: str) -> Path:
    """Resolve a configured project path by key (e.g. ``questions``).

    The path is constrained to the project root; unsafe ``.sci.yaml`` values
    raise :class:`ProjectError` instead of escaping the project.
    """
    config = load_config(root)
    paths = config.get("paths")
    if not isinstance(paths, dict) or key not in paths:
        raise ProjectError("paths.{} is missing from {}".format(key, CONFIG_NAME))
    return resolve_project_path(
        root, paths[key], "{}: paths.{}".format(CONFIG_NAME, key)
    )


def relative_path(root: Path, path: Path) -> str:
    """Return *path* relative to *root* using forward slashes when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def slugify(text: str, max_length: int = 60) -> str:
    """Convert a title into a file-name friendly slug.

    Unicode letters are preserved so non-English titles remain readable.  The
    caller (``sci new``) falls back to the record ID when a title contains no
    usable characters.
    """
    slug = re.sub(r"[^\w]+|_+", "-", text.lower(), flags=re.UNICODE).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug


def unique_path(parent: Path, stem: str, suffix: str) -> Path:
    """Return a non-existing path below *parent*, adding ``-2``, ``-3``..."""
    candidate = parent / "{}{}".format(stem, suffix)
    counter = 2
    while candidate.exists():
        candidate = parent / "{}-{}{}".format(stem, counter, suffix)
        counter += 1
    return candidate


def id_number(record_id: str) -> int:
    """Numeric component of an ID such as ``EXP012`` (0 when absent)."""
    match = re.search(r"(\d+)", record_id)
    return int(match.group(1)) if match else 0


def id_matches_kind(record_id: Any, kind: str) -> bool:
    """True when *record_id* has the shape ``ID_PREFIX[kind]<digits>``.

    Structural only: this checks the ID type, not whether a record exists.
    ``EXP###`` is never treated as an exploration ``X###``.
    """
    if not isinstance(record_id, str):
        return False
    prefix = ID_PREFIX[kind]
    text = record_id.strip()
    if text[: len(prefix)].upper() != prefix:
        return False
    return text[len(prefix):].isdigit()


def _filename_id(kind: str, name: str) -> Optional[str]:
    prefix = ID_PREFIX[kind]
    match = re.match(r"^(" + re.escape(prefix) + r"\d+)(?:-|$)", name)
    return match.group(1) if match else None


def iter_record_locations(root: Path, kind: str) -> Iterator[Tuple[str, Path]]:
    """Yield ``(name, record_file)`` for records of *kind*.

    ``name`` is the filename stem for questions/decisions and the directory
    name for explorations/experiments.  Missing directories yield nothing so
    that callers can distinguish "empty" from "malformed".
    """
    if kind not in ID_PREFIX:
        raise ProjectError("unknown record kind: {}".format(kind))
    root = Path(root)
    try:
        config = load_config(root)
    except ProjectError:
        return
    paths = config.get("paths")
    if not isinstance(paths, dict):
        return
    prefix = ID_PREFIX[kind]
    if kind in ("question", "decision"):
        key = "questions" if kind == "question" else "decisions"
        try:
            directory = resolve_project_path(
                root, paths.get(key), "{}: paths.{}".format(CONFIG_NAME, key)
            )
        except ProjectError:
            return
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("{}*.md".format(prefix))):
            if path.is_file():
                yield path.stem, path
    else:
        key = "explorations" if kind == "exploration" else "experiments"
        try:
            directory = resolve_project_path(
                root, paths.get(key), "{}: paths.{}".format(CONFIG_NAME, key)
            )
        except ProjectError:
            return
        if not directory.is_dir():
            return
        record_file = "NOTE.md" if kind == "exploration" else "README.md"
        for entry in sorted(directory.iterdir()):
            if entry.is_dir() and entry.name.startswith(prefix):
                yield entry.name, entry / record_file


def existing_ids(root: Path, kind: str) -> Set[str]:
    """IDs currently present on disk for a record kind."""
    ids: Set[str] = set()
    for name, _path in iter_record_locations(root, kind):
        record_id = _filename_id(kind, name)
        if record_id is not None:
            ids.add(record_id)
    return ids


def _claim_directory(root: Path) -> Path:
    return Path(root) / ID_CLAIMS_DIR


def claimed_ids(root: Path, kind: str) -> Set[str]:
    """IDs permanently claimed for *kind*, whether or not a record exists."""
    if kind not in ID_PREFIX:
        raise ProjectError("unknown record kind: {}".format(kind))
    directory = _claim_directory(root)
    if not directory.is_dir():
        return set()
    prefix = ID_PREFIX[kind]
    pattern = re.compile(r"^(" + re.escape(prefix) + r"\d+)$")
    ids: Set[str] = set()
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        match = pattern.match(entry.name)
        if match:
            ids.add(match.group(1))
    return ids


def next_id(root: Path, kind: str) -> str:
    """Return the next free ID, e.g. ``Q001``, ``EXP012``.

    Both records on disk and permanent claim files count, so an ID whose record
    was deleted is never handed out again.
    """
    prefix = ID_PREFIX[kind]
    highest = 0
    for name, _path in iter_record_locations(root, kind):
        match = re.match(r"^" + re.escape(prefix) + r"(\d+)", name)
        if match:
            highest = max(highest, int(match.group(1)))
    for record_id in claimed_ids(root, kind):
        match = re.match(r"^" + re.escape(prefix) + r"(\d+)$", record_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return "{}{:03d}".format(prefix, highest + 1)


def _write_claim(root: Path, kind: str, record_id: str) -> bool:
    """Create a permanent claim file; return False when already claimed."""
    directory = _claim_directory(root)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(
            "cannot create ID claim directory {}: {}".format(directory, exc)
        ) from exc
    claim = directory / record_id
    try:
        descriptor = os.open(
            str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
        )
    except FileExistsError:
        return False
    except OSError as exc:
        raise ProjectError("cannot claim ID {}: {}".format(record_id, exc)) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                "kind: {}\nclaimed: {}\nclaim_id: {}\n".format(
                    kind,
                    datetime.date.today().isoformat(),
                    uuid.uuid4().hex,
                )
            )
    except OSError as exc:
        raise ProjectError(
            "cannot write ID claim {}: {}".format(claim, exc)
        ) from exc
    return True


def backfill_claims(root: Path, kind: str) -> None:
    """Claim IDs of records created before the claim ledger existed.

    Older projects (or hand-created records) have no claim files.  The first
    new allocation adopts those IDs so they cannot be reused after a deletion.
    """
    for record_id in existing_ids(root, kind):
        _write_claim(root, kind, record_id)


def allocate_id(root: Path, kind: str) -> str:
    """Atomically reserve and return the next ID for *kind*.

    A claim file is created with ``O_CREAT | O_EXCL`` (atomic on POSIX and
    Windows).  Concurrent ``sci new`` processes therefore receive distinct
    IDs, and a claim survives deletion of the record it belongs to.  The random
    ``claim_id`` also makes concurrent branch allocations conflict visibly in
    Git instead of silently producing duplicate IDs.
    """
    if kind not in ID_PREFIX:
        raise ProjectError("unknown record kind: {}".format(kind))
    backfill_claims(root, kind)

    for _attempt in range(10000):
        candidate = next_id(root, kind)
        if not _write_claim(root, kind, candidate):
            # Another process claimed this ID between next_id() and the
            # O_EXCL open.
            continue
        return candidate
    raise ProjectError("could not allocate an ID for {}".format(kind))


def read_front_matter(path: Path) -> Dict[str, Any]:
    """Parse the YAML front matter at the top of a Markdown file."""
    text = Path(path).read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        raise ProjectError("missing YAML front matter")
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ProjectError("invalid YAML front matter: {}".format(exc)) from exc
    if not isinstance(data, dict):
        raise ProjectError("front matter must be a YAML mapping")
    return data


def render_record(front_matter: Dict[str, Any], body: str) -> str:
    """Render a Markdown record with YAML front matter."""
    header = yaml.safe_dump(
        front_matter, sort_keys=False, allow_unicode=True, width=1000
    )
    return "---\n" + header + "---\n\n" + body.strip("\n") + "\n"


def _as_date_text(value: Any) -> Optional[str]:
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_records(root: Path, kind: str) -> Tuple[List[Record], List[str]]:
    """Load records of *kind* and collect structural problems.

    Problems are human-readable strings intended for ``sci validate``.
    Malformed records are still returned with best-effort fields so callers
    such as ``sci status`` stay resilient.
    """
    root = Path(root)
    records: List[Record] = []
    problems: List[str] = []
    seen: Set[str] = set()
    for name, path in iter_record_locations(root, kind):
        rel = relative_path(root, path)
        filename_id = _filename_id(kind, name)
        if filename_id is None:
            problems.append(
                "{}: name does not match {}<digits>-<slug>".format(rel, ID_PREFIX[kind])
            )
        if not path.is_file():
            problems.append("{}: missing record file".format(rel))
            continue
        try:
            data = read_front_matter(path)
        except ProjectError as exc:
            problems.append("{}: {}".format(rel, exc))
            data = {}
        record_id = str(data.get("id") or filename_id or name)
        if filename_id is not None and record_id != filename_id:
            problems.append(
                "{}: front-matter id {!r} does not match name {!r}".format(
                    rel, record_id, name
                )
            )
        if record_id in seen:
            problems.append("{}: duplicate id {!r}".format(rel, record_id))
        seen.add(record_id)
        for field in REQUIRED_RECORD_FIELDS:
            value = data.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                problems.append("{}: missing required field {!r}".format(rel, field))
        created = _as_date_text(data.get("created"))
        if created is None:
            created_text = ""
            if data.get("created") is not None:
                problems.append(
                    "{}: created must be an ISO date (YYYY-MM-DD)".format(rel)
                )
        else:
            created_text = created
            try:
                datetime.date.fromisoformat(created)
            except ValueError:
                problems.append(
                    "{}: created must be an ISO date (YYYY-MM-DD), got {!r}".format(
                        rel, data.get("created")
                    )
                )
        status = data.get("status")
        if isinstance(status, str) and status and status not in STATUS_VALUES[kind]:
            problems.append(
                "{}: status {!r} must be one of: {}".format(
                    rel, status, ", ".join(STATUS_VALUES[kind])
                )
            )
        records.append(
            Record(
                kind=kind,
                id=record_id,
                title=str(data.get("title") or ""),
                status=str(status or ""),
                created=created_text,
                path=path,
                data=data,
            )
        )
    records.sort(key=lambda record: (id_number(record.id), record.id))
    return records, problems
