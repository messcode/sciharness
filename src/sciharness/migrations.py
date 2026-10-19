"""Project configuration schema migrations.

Records and figure manifests carry their own version fields; this module
migrates ``.sci.yaml``.  Migrations are sequential, explicit, and never run
implicitly: ``sci migrate`` is the only entry point.
"""
from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from .project import (
    CONFIG_NAME,
    DEFAULT_PATHS,
    SUPPORTED_SCHEMA_VERSION,
    ProjectError,
    load_config,
)


@dataclass
class MigrationAction:
    from_version: int
    to_version: int
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "description": self.description,
        }


@dataclass
class MigrationResult:
    before: int
    after: int
    actions: List[MigrationAction]

    @property
    def changed(self) -> bool:
        return bool(self.actions)


def current_version(config: Dict[str, Any]) -> int:
    value = config.get("schema_version")
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectError("schema_version must be an integer")
    return value


def _migrate_0_to_1(
    config: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    """Add schema_version and fill the minimal project/paths defaults."""
    migrated = copy.deepcopy(config)
    migrated["schema_version"] = 1

    project = migrated.get("project")
    if not isinstance(project, dict):
        project = {}
        migrated["project"] = project
    if not isinstance(project.get("name"), str) or not project["name"].strip():
        project["name"] = "Untitled project"
    if not project.get("created"):
        project["created"] = datetime.date.today().isoformat()

    paths = migrated.get("paths")
    if not isinstance(paths, dict):
        paths = {}
        migrated["paths"] = paths
    for key, value in DEFAULT_PATHS.items():
        paths.setdefault(key, value)
    return migrated, "set schema_version and fill project/paths defaults"


_MIGRATIONS: Dict[int, Tuple[int, str, Any]] = {
    0: (1, "legacy config without schema_version", _migrate_0_to_1),
}


def plan_migrations(
    config: Dict[str, Any],
) -> Tuple[int, Dict[str, Any], List[MigrationAction]]:
    before = current_version(config)
    if before > SUPPORTED_SCHEMA_VERSION:
        raise ProjectError(
            "project schema_version {} is newer than supported version {}; "
            "upgrade sciharness".format(before, SUPPORTED_SCHEMA_VERSION)
        )
    current = copy.deepcopy(config)
    actions: List[MigrationAction] = []
    version = before
    while version < SUPPORTED_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            raise ProjectError(
                "no migration path from schema_version {}".format(version)
            )
        to_version, description, apply = migration
        current, detail = apply(current)
        actions.append(
            MigrationAction(
                from_version=version,
                to_version=to_version,
                description="{}: {}".format(description, detail),
            )
        )
        version = to_version
    return before, current, actions


def migrate_project(root: Path, dry_run: bool = False) -> MigrationResult:
    """Migrate ``.sci.yaml`` to the supported schema version."""
    root = Path(root)
    config = load_config(root)
    before, migrated, actions = plan_migrations(config)
    result = MigrationResult(before=before, after=SUPPORTED_SCHEMA_VERSION, actions=actions)
    if actions and not dry_run:
        path = root / CONFIG_NAME
        text = yaml.safe_dump(migrated, sort_keys=False, allow_unicode=True)
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            raise ProjectError(
                "cannot write migrated {}: {}".format(path, exc)
            ) from exc
    return result
