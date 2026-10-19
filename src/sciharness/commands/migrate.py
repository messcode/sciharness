"""``sci migrate``: apply sequential ``.sci.yaml`` schema migrations."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..migrations import migrate_project
from ..output import EXIT_OK, emit, envelope, project_info
from ..project import find_project_root


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    dry_run = bool(getattr(args, "dry_run", False))
    result = migrate_project(root, dry_run=dry_run)

    if getattr(args, "json", False):
        emit(
            envelope(
                "migrate",
                project=project_info(root),
                data={
                    "dry_run": dry_run,
                    "before": result.before,
                    "after": result.after,
                    "actions": [action.to_dict() for action in result.actions],
                },
            )
        )
        return EXIT_OK

    if not result.actions:
        print(
            "Project schema is current (schema_version {}).".format(result.after)
        )
        return EXIT_OK
    print(
        "{} schema migration(s) from version {} to {}{}".format(
            len(result.actions),
            result.before,
            result.after,
            " (dry run)" if dry_run else "",
        )
    )
    for action in result.actions:
        print(
            "  {} -> {}: {}".format(
                action.from_version, action.to_version, action.description
            )
        )
    if dry_run:
        print("  no files written; re-run without --dry-run to apply")
    return EXIT_OK
