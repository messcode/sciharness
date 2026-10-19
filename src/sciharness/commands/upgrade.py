"""``sci upgrade``: update managed scaffold files without clobbering edits."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..output import EXIT_OK, emit, envelope, project_info
from ..project import find_project_root
from ..scaffold import upgrade


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    dry_run = bool(getattr(args, "dry_run", False))
    actions, pending = upgrade(
        root,
        dry_run=dry_run,
        force=bool(getattr(args, "force", False)),
    )
    changed = [action for action in actions if action.action != "current"]
    ok = not pending

    if getattr(args, "json", False):
        emit(
            envelope(
                "upgrade",
                project=project_info(root),
                ok=ok,
                data={
                    "dry_run": dry_run,
                    "actions": [action.to_dict() for action in actions],
                    "pending": pending,
                },
            )
        )
        return EXIT_OK

    print(
        "sci upgrade{}: {} file(s) need attention".format(
            " (dry run)" if dry_run else "", len(changed)
        )
    )
    if not changed:
        print("  scaffold is up to date")
    for action in changed:
        print("  {:<9} {}".format(action.action, action.path))
        if action.detail:
            print("            {}".format(action.detail))
    if pending:
        print(
            "  pending: review {} .new sidecar(s) and re-run "
            "`sci upgrade`".format(len(pending))
        )
    return EXIT_OK
