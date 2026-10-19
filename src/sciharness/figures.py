"""Manuscript figure scaffolding and structural validation.

SciHarness structures figure production and validates declared provenance and
release artifacts.  It never renders plots, exports source data, or infers
scientific approval.  Project-specific scripts remain responsible for the
finalized panel data, the final visual, and the paired source CSV.

Path conventions inside ``manifest.yaml``:

- ``generator.file`` and ``style_file`` are relative to the project root;
- panel ``outputs.*`` and ``source_data.files`` are relative to the figure
  directory (for example ``release/main/with_legend/Fig3a.pdf``).

Project-relative artifact paths that start with ``manuscript/`` are also
accepted.  Declared paths are always relative and must not escape the project
root.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .datasets import dataset_ids
from .project import ProjectError, existing_ids, relative_path

MANUSCRIPT_DIR = "manuscript"
FIGURES_DIR = "manuscript/figures"

FIGURE_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "figure"

FIGURE_SCHEMA_VERSION = 1

FIGURE_STATUSES: Tuple[str, ...] = ("working", "validated", "released")
PANEL_ROLES: Tuple[str, ...] = ("main", "supplementary")

FIGURE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

WORKING_SUBDIRECTORIES: Tuple[str, ...] = (
    "working/exploratory",
    "working/validation",
    "working/cache",
    "working/legacy",
)

PREVIEW_SUBDIRECTORIES: Tuple[str, ...] = ("previews",)

# Release layout is declared by manifest paths, not imposed by the scaffold.
# Init only creates ``release/`` (with a ``.gitkeep`` so Git keeps it); project
# scripts create the concrete ``release/...`` directories they declare.
RELEASE_LEAF_DIRECTORIES: Tuple[str, ...] = ("release",)

GITKEEP = ".gitkeep"

APPROVAL_FILENAME = "APPROVAL.yaml"
APPROVAL_SCHEMA_VERSION = 1

# Path segments that may never host a publication artifact.
_FORBIDDEN_RELEASE_SEGMENTS = ("working", "previews")


@dataclass
class FigureInspection:
    """Parsed figure state plus declared release artifacts."""

    target: Path
    figure_md: Path
    manifest_path: Path
    rel_manifest: str
    data: Dict[str, Any]
    problems: List[str]
    outputs: List[Tuple[str, str, Path]]
    source_files: List[Tuple[str, str, Path]]
    required_without_files: List[str]


def validate_figure_id(figure_id: Any) -> str:
    """Reject unsafe figure identifiers, including path traversal."""
    if not isinstance(figure_id, str) or not FIGURE_ID_RE.match(figure_id):
        raise ProjectError(
            "invalid figure id {!r}: use letters, digits, '-' or '_' "
            "(for example 'figure3')".format(figure_id)
        )
    return figure_id


def figure_directory(root: Path, figure_id: str) -> Path:
    """Return ``<root>/manuscript/figures/<figure_id>``."""
    return Path(root) / MANUSCRIPT_DIR / "figures" / figure_id


def _write_from_template(source: Path, destination: Path, figure_id: str) -> None:
    text = Path(source).read_text(encoding="utf-8")
    destination.write_text(text.replace("{{FIGURE_ID}}", figure_id), encoding="utf-8")


def init_figure(root: Path, figure_id: str) -> Path:
    """Create a figure workspace lazily; fail safely if it already exists."""
    root = Path(root)
    validate_figure_id(figure_id)
    target = figure_directory(root, figure_id)
    if target.exists():
        raise ProjectError(
            "figure {!r} already exists: {}".format(
                figure_id, relative_path(root, target)
            )
        )

    for relative in (
        WORKING_SUBDIRECTORIES + PREVIEW_SUBDIRECTORIES + RELEASE_LEAF_DIRECTORIES
    ):
        (target / relative).mkdir(parents=True, exist_ok=True)
    for relative in RELEASE_LEAF_DIRECTORIES:
        keep = target / relative / GITKEEP
        if not keep.exists():
            keep.write_text("", encoding="utf-8")

    _write_from_template(
        FIGURE_TEMPLATE_DIR / "FIGURE.md", target / "FIGURE.md", figure_id
    )
    _write_from_template(
        FIGURE_TEMPLATE_DIR / "manifest.yaml", target / "manifest.yaml", figure_id
    )
    return target


def list_figures(root: Path) -> List[Tuple[str, str, bool]]:
    """Return ``(figure_id, status, approved)`` for figures on disk.

    Malformed manifests are reported with empty status so callers such as
    ``sci status`` stay resilient.
    """
    root = Path(root)
    directory = root / FIGURES_DIR
    figures: List[Tuple[str, str, bool]] = []
    if not directory.is_dir():
        return figures
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        status = ""
        approved = False
        manifest = entry / "manifest.yaml"
        if manifest.is_file():
            try:
                data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                data = None
            if isinstance(data, dict):
                status = str(data.get("status") or "")
                release = data.get("release")
                if isinstance(release, dict):
                    approved = release.get("approved") is True
        figures.append((entry.name, status, approved))
    return figures


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------


def _looks_absolute(value: str) -> bool:
    if value.startswith(("/", "\\", "~")):
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", value))


def _normalized(value: str) -> PurePosixPath:
    """Normalize separators without touching ``..``."""
    return PurePosixPath(value.replace("\\", "/"))


def _within(path: Path, directory: Path) -> bool:
    """True when *path* is inside *directory* (both already resolved)."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _check_declared_path(
    root: Path,
    base: Path,
    value: Any,
    rel_manifest: str,
    label: str,
    problems: List[str],
    *,
    forbid_release_segments: bool = False,
    must_be_within: Optional[Path] = None,
    within_label: str = "",
) -> Optional[Path]:
    if not isinstance(value, str) or not value.strip():
        problems.append(
            "{}: {} must be a non-empty string path".format(rel_manifest, label)
        )
        return None
    if _looks_absolute(value):
        problems.append(
            "{}: {} must be project-relative, got absolute path {!r}".format(
                rel_manifest, label, value
            )
        )
        return None
    normalized = _normalized(value)
    if ".." in normalized.parts:
        problems.append(
            "{}: {} must not contain '..' path traversal: {!r}".format(
                rel_manifest, label, value
            )
        )
        return None
    candidate = (base / value).resolve()
    root_resolved = Path(root).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        problems.append(
            "{}: {} escapes the project root: {!r}".format(rel_manifest, label, value)
        )
        return None
    if forbid_release_segments and any(
        part in _FORBIDDEN_RELEASE_SEGMENTS for part in normalized.parts
    ):
        problems.append(
            "{}: {} must not point into working/ or previews/: {!r}".format(
                rel_manifest, label, value
            )
        )
        return None
    if must_be_within is not None and not _within(candidate, must_be_within):
        problems.append(
            "{}: {} must resolve inside {}: {!r}".format(
                rel_manifest, label, within_label, value
            )
        )
        return None
    return candidate


def _artifact_base(root: Path, target: Path, value: str) -> Path:
    """Choose the base for a figure artifact path.

    Figure-relative paths (``release/...``) resolve against the figure
    directory.  Paths explicitly rooted at ``manuscript/`` resolve against the
    project root so both conventions are usable.
    """
    first = _normalized(value).parts[0] if _normalized(value).parts else ""
    return Path(root) if first == MANUSCRIPT_DIR else target


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> Any:
    """Normalize YAML values so JSON serialization is order- and type-safe."""
    if isinstance(value, dict):
        return {str(key): _canonical_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _reviewed_manifest_hash(data: Dict[str, Any]) -> str:
    """Hash the reviewable manifest content, excluding status/approval state.

    The figure goes from ``validated`` to ``released`` after approval, which
    changes ``status`` and ``release`` in the manifest.  Those fields are
    intentionally excluded so that the legitimate transition does not
    invalidate the approval.  Panels, paths, style, and figure id are included.
    """
    payload = {
        key: value
        for key, value in data.items()
        if key not in ("status", "release")
    }
    canonical = json.dumps(
        _canonical_json(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git_head(root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _git_user(root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _default_approver(root: Path) -> str:
    return (
        _git_user(root)
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or "unknown"
    )


def _inspect_figure(root: Path, figure_id: str) -> FigureInspection:
    target = figure_directory(root, figure_id)
    figure_md = target / "FIGURE.md"
    manifest_path = target / "manifest.yaml"
    rel_manifest = relative_path(root, manifest_path)
    empty = FigureInspection(
        target=target,
        figure_md=figure_md,
        manifest_path=manifest_path,
        rel_manifest=rel_manifest,
        data={},
        problems=[],
        outputs=[],
        source_files=[],
        required_without_files=[],
    )
    if not target.is_dir():
        empty.problems.append(
            "{}: figure directory does not exist".format(relative_path(root, target))
        )
        return empty

    problems: List[str] = []
    if not figure_md.is_file():
        problems.append("{}: missing FIGURE.md".format(relative_path(root, figure_md)))
    if not manifest_path.is_file():
        problems.append("{}: missing manifest.yaml".format(rel_manifest))
        empty.problems = problems
        return empty
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        problems.append("{}: invalid YAML: {}".format(rel_manifest, exc))
        empty.problems = problems
        return empty
    if not isinstance(data, dict):
        problems.append("{}: must contain a YAML mapping".format(rel_manifest))
        empty.problems = problems
        return empty

    manifest_problems, outputs, source_files, required_without = _validate_manifest(
        root, figure_id, target, rel_manifest, data
    )
    problems.extend(manifest_problems)
    return FigureInspection(
        target=target,
        figure_md=figure_md,
        manifest_path=manifest_path,
        rel_manifest=rel_manifest,
        data=data,
        problems=problems,
        outputs=outputs,
        source_files=source_files,
        required_without_files=required_without,
    )


def validate_figure(root: Path, figure_id: str, release: bool = False) -> List[str]:
    """Return a list of structural problems for a manuscript figure.

    With ``release=True`` additionally require explicit approval, a
    ``validated`` or ``released`` status, an intact approval record, and the
    presence and hashes of all declared release artifacts and paired source
    data.  Validation never mutates status or approval.
    """
    root = Path(root)
    try:
        validate_figure_id(figure_id)
    except ProjectError as exc:
        return [str(exc)]

    inspection = _inspect_figure(root, figure_id)
    problems = list(inspection.problems)
    if release and inspection.data:
        problems.extend(_validate_release(root, inspection))
    return problems


def _validate_manifest(
    root: Path,
    figure_id: str,
    target: Path,
    rel_manifest: str,
    data: Dict[str, Any],
) -> Tuple[
    List[str],
    List[Tuple[str, str, Path]],
    List[Tuple[str, str, Path]],
    List[str],
]:
    problems: List[str] = []

    if data.get("schema_version") != FIGURE_SCHEMA_VERSION:
        problems.append(
            "{}: schema_version must be {}".format(
                rel_manifest, FIGURE_SCHEMA_VERSION
            )
        )

    if data.get("figure_id") != figure_id:
        problems.append(
            "{}: figure_id {!r} does not match directory name {!r}".format(
                rel_manifest, data.get("figure_id"), figure_id
            )
        )

    status = data.get("status")
    if status not in FIGURE_STATUSES:
        problems.append(
            "{}: status {!r} must be one of: {}".format(
                rel_manifest, status, ", ".join(FIGURE_STATUSES)
            )
        )

    problems.extend(_validate_style_file(root, rel_manifest, data.get("style_file")))

    panels = data.get("panels")
    if panels is None:
        panels = {}
    if not isinstance(panels, dict):
        problems.append("{}: panels must be a mapping".format(rel_manifest))
        return problems, [], [], []

    experiment_ids = existing_ids(root, "experiment")
    exploration_ids = existing_ids(root, "exploration")
    known_datasets = dataset_ids(root)
    seen_outputs: Dict[str, str] = {}
    declared_outputs: List[Tuple[str, str, Path]] = []
    required_source_files: List[Tuple[str, str, Path]] = []
    required_without_files: List[str] = []

    for panel_id in sorted(panels, key=str):
        raw_panel = panels[panel_id]
        label = "panels.{}".format(panel_id)
        if not isinstance(raw_panel, dict):
            problems.append("{}: {} must be a mapping".format(rel_manifest, label))
            continue

        role = raw_panel.get("role")
        if role not in PANEL_ROLES:
            problems.append(
                "{}: {}.role {!r} must be one of: {}".format(
                    rel_manifest, label, role, ", ".join(PANEL_ROLES)
                )
            )

        problems.extend(
            _validate_evidence(
                rel_manifest,
                label,
                raw_panel.get("evidence"),
                experiment_ids,
                exploration_ids,
                known_datasets,
            )
        )
        problems.extend(
            _validate_generator(
                root, rel_manifest, label, raw_panel.get("generator")
            )
        )
        problems.extend(
            _validate_panel_outputs(
                root,
                target,
                rel_manifest,
                label,
                raw_panel.get("outputs"),
                seen_outputs,
                declared_outputs,
            )
        )
        problems.extend(
            _validate_source_data(
                root,
                target,
                rel_manifest,
                label,
                raw_panel.get("source_data"),
                required_source_files,
                required_without_files,
            )
        )

    return (
        problems,
        declared_outputs,
        required_source_files,
        required_without_files,
    )


def _validate_style_file(root: Path, rel_manifest: str, value: Any) -> List[str]:
    if value is None:
        return []
    problems: List[str] = []
    resolved = _check_declared_path(
        root, root, value, rel_manifest, "style_file", problems
    )
    if resolved is not None and not resolved.is_file():
        problems.append(
            "{}: style_file does not exist: {!r}".format(rel_manifest, value)
        )
    return problems


def _validate_evidence(
    rel_manifest: str,
    label: str,
    evidence: Any,
    experiment_ids: Any,
    exploration_ids: Any,
    dataset_ids: Any,
) -> List[str]:
    if evidence is None:
        return []
    if not isinstance(evidence, dict):
        return ["{}: {}.evidence must be a mapping".format(rel_manifest, label)]

    problems: List[str] = []
    prefix = "{}.evidence".format(label)

    def check_one(field: str, allowed: Any, expected: str) -> None:
        value = evidence.get(field)
        if value is None:
            return
        if not isinstance(value, str) or not value.strip():
            problems.append(
                "{}: {}.{} must be a string ID".format(
                    rel_manifest, prefix, field
                )
            )
            return
        if value.strip() not in allowed:
            problems.append(
                "{}: {}.{} {!r} does not exist".format(
                    rel_manifest, prefix, field, value.strip()
                )
            )

    def check_many(field: str, allowed: Any, expected: str) -> None:
        value = evidence.get(field)
        if value is None:
            return
        if not isinstance(value, list):
            problems.append(
                "{}: {}.{} must be a list of {} IDs".format(
                    rel_manifest, prefix, field, expected
                )
            )
            return
        seen = set()
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                problems.append(
                    "{}: {}.{}[{}] must be a non-empty string ID".format(
                        rel_manifest, prefix, field, index
                    )
                )
                continue
            item = item.strip()
            if item in seen:
                problems.append(
                    "{}: {}.{} contains duplicate ID {!r}".format(
                        rel_manifest, prefix, field, item
                    )
                )
                continue
            seen.add(item)
            if item not in allowed:
                problems.append(
                    "{}: {}.{} {!r} does not exist".format(
                        rel_manifest, prefix, field, item
                    )
                )

    check_one("experiment", experiment_ids, "experiment")
    check_many("experiments", experiment_ids, "experiment")
    check_many("explorations", exploration_ids, "exploration")
    check_many("datasets", dataset_ids, "dataset")
    return problems


def _validate_generator(
    root: Path, rel_manifest: str, label: str, generator: Any
) -> List[str]:
    if generator is None:
        return []
    if not isinstance(generator, dict):
        return ["{}: {}.generator must be a mapping".format(rel_manifest, label)]
    file_value = generator.get("file")
    if file_value is None:
        return []
    problems: List[str] = []
    resolved = _check_declared_path(
        root,
        root,
        file_value,
        rel_manifest,
        "{}.generator.file".format(label),
        problems,
    )
    if resolved is not None and not resolved.is_file():
        problems.append(
            "{}: {}.generator.file does not exist: {!r}".format(
                rel_manifest, label, file_value
            )
        )
    return problems


def _validate_panel_outputs(
    root: Path,
    target: Path,
    rel_manifest: str,
    label: str,
    outputs: Any,
    seen: Dict[str, str],
    declared: List[Tuple[str, str, Path]],
) -> List[str]:
    if outputs is None:
        return []
    if not isinstance(outputs, dict):
        return ["{}: {}.outputs must be a mapping".format(rel_manifest, label)]
    problems: List[str] = []
    release_root = (Path(target) / "release").resolve()
    within_label = "{}/release".format(relative_path(root, target))
    for key in sorted(outputs, key=str):
        value = outputs[key]
        path_label = "{}.outputs.{}".format(label, key)
        base = _artifact_base(root, target, str(value)) if isinstance(value, str) else target
        resolved = _check_declared_path(
            root, base, value, rel_manifest, path_label, problems,
            forbid_release_segments=True,
            must_be_within=release_root,
            within_label=within_label,
        )
        if resolved is None:
            continue
        canonical = str(resolved)
        if canonical in seen:
            problems.append(
                "{}: {} duplicates release output path {!r} already declared by {}".format(
                    rel_manifest, path_label, value, seen[canonical]
                )
            )
            continue
        seen[canonical] = path_label
        declared.append((path_label, str(value), resolved))
    return problems


def _validate_source_data(
    root: Path,
    target: Path,
    rel_manifest: str,
    label: str,
    source_data: Any,
    required_files: List[Tuple[str, str, Path]],
    required_without_files: List[str],
) -> List[str]:
    if source_data is None:
        return []
    if not isinstance(source_data, dict):
        return ["{}: {}.source_data must be a mapping".format(rel_manifest, label)]
    problems: List[str] = []
    source_root = (Path(target) / "release" / "source_data").resolve()
    within_label = "{}/release/source_data".format(relative_path(root, target))
    required = source_data.get("required", False)
    if not isinstance(required, bool):
        problems.append(
            "{}: {}.source_data.required must be a boolean".format(rel_manifest, label)
        )
        required = False
    files = source_data.get("files", [])
    if files is None:
        files = []
    if not isinstance(files, list):
        problems.append(
            "{}: {}.source_data.files must be a list".format(rel_manifest, label)
        )
        return problems
    if required and not files:
        required_without_files.append("{}.source_data".format(label))
    for index, value in enumerate(files):
        path_label = "{}.source_data.files[{}]".format(label, index)
        base = _artifact_base(root, target, str(value)) if isinstance(value, str) else target
        resolved = _check_declared_path(
            root, base, value, rel_manifest, path_label, problems,
            forbid_release_segments=True,
            must_be_within=source_root,
            within_label=within_label,
        )
        if resolved is None or not required:
            continue
        required_files.append((path_label, str(value), resolved))
    return problems


def _validate_release(root: Path, inspection: FigureInspection) -> List[str]:
    data = inspection.data
    rel_manifest = inspection.rel_manifest
    problems: List[str] = []

    status = data.get("status")
    if status not in ("validated", "released"):
        problems.append(
            "{}: release validation requires status 'validated' or 'released', "
            "got {!r}".format(rel_manifest, status)
        )
    release = data.get("release")
    if not isinstance(release, dict) or release.get("approved") is not True:
        problems.append(
            "{}: release.approved must be true for a release-ready figure".format(
                rel_manifest
            )
        )

    if not inspection.outputs:
        problems.append(
            "{}: release requires at least one declared panel output".format(
                rel_manifest
            )
        )
    for _path_label, value, resolved in inspection.outputs:
        if not resolved.is_file():
            problems.append(
                "{}: declared release output does not exist: {!r}".format(
                    rel_manifest, value
                )
            )
    for _path_label, value, resolved in inspection.source_files:
        if not resolved.is_file():
            problems.append(
                "{}: required source data does not exist: {!r}".format(
                    rel_manifest, value
                )
            )
    for label in inspection.required_without_files:
        problems.append(
            "{}: {} is required but declares no source-data files".format(
                rel_manifest, label
            )
        )

    approval_path = inspection.target / "release" / APPROVAL_FILENAME
    if not approval_path.is_file():
        problems.append(
            "{}: missing release approval record {} (run `sci figure approve {}`)"
            .format(
                rel_manifest,
                relative_path(root, approval_path),
                data.get("figure_id"),
            )
        )
        return problems
    try:
        approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        problems.append(
            "{}: invalid approval record {}: {}".format(
                rel_manifest, relative_path(root, approval_path), exc
            )
        )
        return problems
    if not isinstance(approval, dict):
        problems.append(
            "{}: approval record must contain a YAML mapping".format(rel_manifest)
        )
        return problems
    if approval.get("schema_version") != APPROVAL_SCHEMA_VERSION:
        problems.append(
            "{}: approval record schema_version must be {}".format(
                rel_manifest, APPROVAL_SCHEMA_VERSION
            )
        )
    if approval.get("figure_id") != data.get("figure_id"):
        problems.append(
            "{}: approval record figure_id does not match manifest".format(
                rel_manifest
            )
        )
    approved_by = approval.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip():
        problems.append(
            "{}: approval record must name who approved the figure".format(
                rel_manifest
            )
        )
    if isinstance(release, dict) and (
        release.get("approved_by") != approved_by
        or release.get("approved_at") != approval.get("approved_at")
    ):
        problems.append(
            "{}: manifest approval metadata does not match approval record".format(
                rel_manifest
            )
        )
    approved_at = approval.get("approved_at")
    if not isinstance(approved_at, str) or not approved_at.strip():
        problems.append(
            "{}: approval record must record when the figure was approved".format(
                rel_manifest
            )
        )
    else:
        try:
            datetime.datetime.fromisoformat(approved_at.strip())
        except ValueError:
            problems.append(
                "{}: approval record approved_at must be an ISO timestamp".format(
                    rel_manifest
                )
            )
    if approval.get("manifest_sha256") != _reviewed_manifest_hash(data):
        problems.append(
            "{}: manifest changed since approval (re-run `sci figure approve {}`)"
            .format(rel_manifest, data.get("figure_id"))
        )
    if inspection.figure_md.is_file():
        if approval.get("figure_md_sha256") != _sha256(inspection.figure_md):
            problems.append(
                "{}: FIGURE.md changed since approval (re-run `sci figure approve {}`)"
                .format(rel_manifest, data.get("figure_id"))
            )

    artifacts = approval.get("artifacts")
    if not isinstance(artifacts, dict):
        problems.append(
            "{}: approval record must contain artifact hashes".format(rel_manifest)
        )
        return problems
    for _path_label, value, resolved in (
        inspection.outputs + inspection.source_files
    ):
        if not resolved.is_file():
            continue
        expected = artifacts.get(value)
        if not isinstance(expected, str) or not expected:
            problems.append(
                "{}: approval record has no hash for {!r}".format(
                    rel_manifest, value
                )
            )
        elif _sha256(resolved) != expected:
            problems.append(
                "{}: artifact changed since approval: {!r}".format(
                    rel_manifest, value
                )
            )
    return problems


def approve_figure(
    root: Path, figure_id: str, approved_by: Optional[str] = None
) -> Path:
    """Record explicit approval of a validated figure and its artifacts.

    This does not render, export, or judge the figure.  It captures the current
    manifest, FIGURE.md, and artifact hashes so a later ``--release`` check can
    prove that what was reviewed is still what is on disk.
    """
    root = Path(root)
    validate_figure_id(figure_id)
    inspection = _inspect_figure(root, figure_id)
    if inspection.problems:
        raise ProjectError(
            "cannot approve figure {!r}:\n  - {}".format(
                figure_id, "\n  - ".join(inspection.problems)
            )
        )
    data = inspection.data
    status = data.get("status")
    if status != "validated":
        raise ProjectError(
            "figure status must be 'validated' before approval, got {!r}".format(
                status
            )
        )
    if not inspection.outputs:
        raise ProjectError(
            "cannot approve figure {!r}: no release outputs are declared".format(
                figure_id
            )
        )
    if inspection.required_without_files:
        raise ProjectError(
            "cannot approve figure {!r}: {} is required but declares no "
            "source-data files".format(
                figure_id, ", ".join(inspection.required_without_files)
            )
        )

    artifacts: Dict[str, str] = {}
    for _path_label, value, resolved in (
        inspection.outputs + inspection.source_files
    ):
        if not resolved.is_file():
            raise ProjectError(
                "cannot approve figure {!r}: declared artifact does not exist: "
                "{!r}".format(figure_id, value)
            )
        artifacts[value] = _sha256(resolved)

    by = (approved_by or "").strip() or _default_approver(root)
    approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    release = data.get("release")
    if not isinstance(release, dict):
        release = {}
    release.update(
        {"approved": True, "approved_by": by, "approved_at": approved_at}
    )
    data["release"] = release
    inspection.manifest_path.write_text(
        yaml.safe_dump(
            data, sort_keys=False, allow_unicode=True, width=1000
        ),
        encoding="utf-8",
    )

    approval = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "figure_id": figure_id,
        "approved_by": by,
        "approved_at": approved_at,
        "reviewed_commit": _git_head(root),
        "manifest_sha256": _reviewed_manifest_hash(data),
        "figure_md_sha256": (
            _sha256(inspection.figure_md)
            if inspection.figure_md.is_file()
            else None
        ),
        "artifacts": artifacts,
    }
    approval_path = inspection.target / "release" / APPROVAL_FILENAME
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(
        yaml.safe_dump(approval, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8",
    )
    return approval_path
