"""Project discovery, configuration, records, and deterministic ID allocation.

All persistent state lives in Markdown/YAML files.  This module only reads and
writes those files; it never performs scientific interpretation.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import yaml

CONFIG_NAME = ".sci.yaml"
SUPPORTED_SCHEMA_VERSION = 1

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


def config_path(root: Path, key: str) -> Path:
    """Resolve a configured project path by key (e.g. ``questions``)."""
    config = load_config(root)
    paths = config.get("paths")
    if not isinstance(paths, dict) or key not in paths:
        raise ProjectError("paths.{} is missing from {}".format(key, CONFIG_NAME))
    return Path(root) / str(paths[key])


def relative_path(root: Path, path: Path) -> str:
    """Return *path* relative to *root* using forward slashes when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def slugify(text: str, max_length: int = 60) -> str:
    """Convert a title into a file-name friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug or "untitled"


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
        directory = root / str(paths.get(key, ""))
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("{}*.md".format(prefix))):
            if path.is_file():
                yield path.stem, path
    else:
        key = "explorations" if kind == "exploration" else "experiments"
        directory = root / str(paths.get(key, ""))
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


def next_id(root: Path, kind: str) -> str:
    """Allocate the next deterministic ID, e.g. ``Q001``, ``EXP012``."""
    prefix = ID_PREFIX[kind]
    highest = 0
    for name, _path in iter_record_locations(root, kind):
        match = re.match(r"^" + re.escape(prefix) + r"(\d+)", name)
        if match:
            highest = max(highest, int(match.group(1)))
    return "{}{:03d}".format(prefix, highest + 1)


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
