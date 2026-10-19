"""Scaffold metadata, doctor checks, and non-destructive upgrades.

``sci init`` records a hash baseline in ``.sci/scaffold.json``.  ``sci doctor``
uses that baseline to distinguish user modifications from files that merely
lag behind the installed package.  ``sci upgrade`` updates only files whose
current hash still matches the baseline; user-modified files are preserved and
receive a ``.new`` sidecar unless ``--force`` is given.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import __version__
from .output import Diagnostic
from .project import (
    KINDS,
    ProjectError,
    backfill_claims,
    claimed_ids,
    existing_ids,
    load_config,
)

PROJECT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "project"
SKILLS_SOURCE_DIR = Path(__file__).resolve().parent / "resources" / "skills"

SCAFFOLD_FILE = ".sci/scaffold.json"
SCAFFOLD_SCHEMA_VERSION = 1
SCAFFOLD_VERSION = 1

PLACEHOLDER_NAME = "{{PROJECT_NAME}}"
PLACEHOLDER_DATE = "{{PROJECT_DATE}}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def managed_files() -> Dict[str, Path]:
    """Return ``relative project path -> packaged source file``."""
    files: Dict[str, Path] = {}
    for source in sorted(PROJECT_TEMPLATE_DIR.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts:
            files[source.relative_to(PROJECT_TEMPLATE_DIR).as_posix()] = source
    for source in sorted(SKILLS_SOURCE_DIR.rglob("*")):
        if source.is_file():
            relative = (
                Path(".agents") / "skills" / source.relative_to(SKILLS_SOURCE_DIR)
            ).as_posix()
            files[relative] = source
    return files


def _project_values(config: Dict[str, Any]) -> Dict[str, str]:
    project = config.get("project")
    if not isinstance(project, dict):
        return {PLACEHOLDER_NAME: "", PLACEHOLDER_DATE: ""}
    name = project.get("name")
    created = project.get("created")
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    return {
        PLACEHOLDER_NAME: str(name) if name is not None else "",
        PLACEHOLDER_DATE: str(created) if created is not None else "",
    }


def render_managed_bytes(source: Path, config: Dict[str, Any]) -> bytes:
    """Render a packaged scaffold file with the project's name/date."""
    try:
        text = Path(source).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return Path(source).read_bytes()
    for placeholder, value in _project_values(config).items():
        text = text.replace(placeholder, value)
    return text.encode("utf-8")


def scaffold_path(root: Path) -> Path:
    return Path(root) / SCAFFOLD_FILE


def write_scaffold_manifest(
    root: Path, pending: Optional[List[str]] = None
) -> Path:
    """Hash the managed files currently present in *root* and record a baseline.

    *pending* marks files whose current content already differs from the
    packaged scaffold.  Adopting an old project records them as pending so a
    later ``sci upgrade`` writes sidecars instead of overwriting local edits.
    """
    root = Path(root)
    files: Dict[str, str] = {}
    for relative, _source in managed_files().items():
        destination = root / relative
        if destination.is_file():
            files[relative] = sha256_file(destination)
    data: Dict[str, Any] = {
        "schema_version": SCAFFOLD_SCHEMA_VERSION,
        "sciharness_version": __version__,
        "scaffold_version": SCAFFOLD_VERSION,
        "files": files,
    }
    if pending:
        data["pending"] = sorted(set(pending))
    path = scaffold_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise ProjectError(
            "cannot write scaffold manifest {}: {}".format(path, exc)
        ) from exc
    return path


def load_scaffold_manifest(root: Path) -> Optional[Dict[str, Any]]:
    path = scaffold_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(
            "cannot parse scaffold manifest {}: {}".format(path, exc)
        ) from exc
    if not isinstance(data, dict):
        raise ProjectError("scaffold manifest must contain a JSON object")
    if data.get("schema_version") != SCAFFOLD_SCHEMA_VERSION:
        raise ProjectError(
            "scaffold manifest schema_version must be {}".format(
                SCAFFOLD_SCHEMA_VERSION
            )
        )
    if not isinstance(data.get("files"), dict):
        raise ProjectError("scaffold manifest files must be a mapping")
    for key, value in data["files"].items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ProjectError(
                "scaffold manifest files must map relative paths to hashes"
            )
    if "pending" in data and not isinstance(data["pending"], list):
        raise ProjectError("scaffold manifest pending must be a list")
    return data


def _severity_order(diagnostic: Diagnostic) -> int:
    return {"error": 0, "warning": 1, "info": 2}.get(diagnostic.severity, 3)


def doctor(root: Path, fix: bool = False) -> List[Diagnostic]:
    """Return diagnostics about project structure, scaffold drift, and ID claims."""
    root = Path(root)
    from .commands.validate import validate_project

    diagnostics: List[Diagnostic] = []
    try:
        config = load_config(root)
    except ProjectError as exc:
        return [
            Diagnostic(
                code="CONFIG_ERROR",
                severity="error",
                message=str(exc),
                path=".sci.yaml",
            )
        ]

    diagnostics.extend(
        Diagnostic.from_problem(problem)
        for problem in validate_project(root)
    )

    try:
        manifest = load_scaffold_manifest(root)
    except ProjectError as exc:
        diagnostics.append(
            Diagnostic(
                code="SCAFFOLD_INVALID",
                severity="error",
                message=str(exc),
                path=SCAFFOLD_FILE,
            )
        )
        manifest = None

    if manifest is None:
        if not fix:
            diagnostics.append(
                Diagnostic(
                    code="SCAFFOLD_MISSING",
                    severity="warning",
                    message=(
                        "no scaffold baseline; cannot distinguish user edits "
                        "from updates to packaged files"
                    ),
                    path=SCAFFOLD_FILE,
                    hint="run `sci doctor --fix` to adopt the current files",
                )
            )
        if fix:
            try:
                pending = []
                for relative, source in managed_files().items():
                    destination = root / relative
                    if not destination.is_file():
                        continue
                    if sha256_file(destination) != sha256_bytes(
                        render_managed_bytes(source, config)
                    ):
                        pending.append(relative)
                write_scaffold_manifest(root, pending=pending)
                diagnostics.append(
                    Diagnostic(
                        code="SCAFFOLD_ADOPTED",
                        severity="info",
                        message=(
                            "recorded current files as the scaffold baseline; "
                            "{} file(s) marked for sidecar review".format(
                                len(pending)
                            )
                        ),
                        path=SCAFFOLD_FILE,
                    )
                )
            except ProjectError as exc:
                diagnostics.append(
                    Diagnostic(
                        code="SCAFFOLD_WRITE_FAILED",
                        severity="error",
                        message=str(exc),
                        path=SCAFFOLD_FILE,
                    )
                )
    else:
        manifest_version = manifest.get("sciharness_version")
        if manifest_version != __version__:
            diagnostics.append(
                Diagnostic(
                    code="SCAFFOLD_VERSION",
                    severity="warning",
                    message=(
                        "project scaffold was recorded by sciharness {}, "
                        "installed version is {}".format(
                            manifest_version, __version__
                        )
                    ),
                    path=SCAFFOLD_FILE,
                    hint="run `sci upgrade --dry-run`",
                )
            )
        recorded = manifest.get("files") or {}
        for relative, source in sorted(managed_files().items()):
            destination = root / relative
            baseline = recorded.get(relative)
            if not destination.is_file():
                diagnostics.append(
                    Diagnostic(
                        code="MANAGED_FILE_MISSING",
                        severity="warning",
                        message="managed scaffold file is missing",
                        path=relative,
                        hint="run `sci upgrade` to restore it",
                    )
                )
                continue
            current = sha256_file(destination)
            packaged = sha256_bytes(render_managed_bytes(source, config))
            if baseline is None:
                diagnostics.append(
                    Diagnostic(
                        code="MANAGED_FILE_UNTRACKED",
                        severity="warning",
                        message="managed scaffold file has no baseline hash",
                        path=relative,
                        hint="run `sci upgrade --dry-run`",
                    )
                )
            elif current != baseline:
                diagnostics.append(
                    Diagnostic(
                        code="MANAGED_FILE_MODIFIED",
                        severity="info",
                        message="managed scaffold file was modified locally",
                        path=relative,
                    )
                )
            elif current != packaged:
                diagnostics.append(
                    Diagnostic(
                        code="MANAGED_FILE_STALE",
                        severity="warning",
                        message="managed scaffold file is older than the installed package",
                        path=relative,
                        hint="run `sci upgrade`",
                    )
                )
        for relative in sorted(set(recorded) - set(managed_files())):
            diagnostics.append(
                Diagnostic(
                    code="MANAGED_FILE_OBSOLETE",
                    severity="info",
                    message="baseline references a file no longer in the packaged scaffold",
                    path=relative,
                    hint="run `sci upgrade` to drop the stale baseline entry",
                )
            )
        pending = manifest.get("pending") or []
        if pending:
            diagnostics.append(
                Diagnostic(
                    code="UPGRADE_PENDING",
                    severity="warning",
                    message="upgrade sidecars still need review: {}".format(
                        ", ".join(str(item) for item in pending)
                    ),
                    path=SCAFFOLD_FILE,
                )
            )

    for kind in KINDS:
        missing = sorted(existing_ids(root, kind) - claimed_ids(root, kind))
        if not missing:
            continue
        if fix:
            backfill_claims(root, kind)
            diagnostics.append(
                Diagnostic(
                    code="ID_CLAIMS_BACKFILLED",
                    severity="info",
                    message="backfilled permanent claims for {}".format(
                        ", ".join(missing)
                    ),
                    path=".sci/ids",
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    code="ID_UNCLAIMED",
                    severity="warning",
                    message="records without permanent ID claims: {}".format(
                        ", ".join(missing)
                    ),
                    path=".sci/ids",
                    hint="run `sci doctor --fix`",
                )
            )

    diagnostics.sort(key=lambda item: (_severity_order(item), item.code, item.path or ""))
    return diagnostics


@dataclass
class UpgradeAction:
    path: str
    action: str
    detail: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "path": self.path,
            "action": self.action,
            "detail": self.detail,
        }


def upgrade(
    root: Path, dry_run: bool = False, force: bool = False
) -> Tuple[List[UpgradeAction], List[str]]:
    """Update unmodified scaffold files and report conflicts.

    Returns ``(actions, pending)`` where *pending* lists files that still have
    a ``.new`` sidecar to review.
    """
    root = Path(root)
    manifest = load_scaffold_manifest(root)
    if manifest is None:
        raise ProjectError(
            "no scaffold baseline; run `sci doctor --fix` to adopt the current "
            "files before upgrading"
        )
    config = load_config(root)
    recorded = dict(manifest.get("files") or {})
    pending: Set[str] = set(str(item) for item in (manifest.get("pending") or []))
    actions: List[UpgradeAction] = []
    new_files: Dict[str, str] = dict(recorded)
    managed = managed_files()

    for relative, source in sorted(managed.items()):
        destination = root / relative
        packaged = render_managed_bytes(source, config)
        packaged_hash = sha256_bytes(packaged)
        current = sha256_file(destination) if destination.is_file() else None
        baseline = recorded.get(relative)

        if current is None:
            actions.append(UpgradeAction(relative, "create"))
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(packaged)
            new_files[relative] = packaged_hash
            pending.discard(relative)
        elif current == packaged_hash:
            actions.append(UpgradeAction(relative, "current"))
            new_files[relative] = packaged_hash
            pending.discard(relative)
        elif relative in pending and not force:
            actions.append(
                UpgradeAction(
                    relative, "sidecar", "adopted baseline still needs review"
                )
            )
            if not dry_run:
                _write_sidecar(destination, packaged)
        elif baseline is None:
            actions.append(
                UpgradeAction(relative, "sidecar", "untracked managed file")
            )
            if not dry_run:
                _write_sidecar(destination, packaged)
            pending.add(relative)
        elif current == baseline:
            actions.append(UpgradeAction(relative, "update"))
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(packaged)
            new_files[relative] = packaged_hash
            pending.discard(relative)
        elif force:
            actions.append(
                UpgradeAction(relative, "overwrite", "local changes discarded")
            )
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(packaged)
            new_files[relative] = packaged_hash
            pending.discard(relative)
        else:
            actions.append(
                UpgradeAction(relative, "sidecar", "local changes preserved")
            )
            if not dry_run:
                _write_sidecar(destination, packaged)
            pending.add(relative)

    for relative in sorted(set(recorded) - set(managed)):
        actions.append(UpgradeAction(relative, "obsolete"))
        new_files.pop(relative, None)
        pending.discard(relative)

    if not dry_run:
        version = (
            __version__
            if not pending
            else (manifest.get("sciharness_version") or __version__)
        )
        data: Dict[str, Any] = {
            "schema_version": SCAFFOLD_SCHEMA_VERSION,
            "sciharness_version": version,
            "scaffold_version": SCAFFOLD_VERSION,
            "files": {key: new_files[key] for key in sorted(new_files)},
        }
        if pending:
            data["pending"] = sorted(pending)
        path = scaffold_path(root)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise ProjectError(
                "cannot write scaffold manifest {}: {}".format(path, exc)
            ) from exc

    return actions, sorted(pending)


def _write_sidecar(destination: Path, packaged: bytes) -> None:
    sidecar = destination.with_name(destination.name + ".new")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_bytes(packaged)
