"""``sci doctor``: diagnose project structure, scaffold drift, and ID claims."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..output import (
    EXIT_OK,
    EXIT_VALIDATION,
    emit,
    envelope,
    project_info,
)
from ..project import find_project_root
from ..scaffold import doctor


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    diagnostics = doctor(root, fix=bool(getattr(args, "fix", False)))
    errors = [item for item in diagnostics if item.severity == "error"]
    warnings = [item for item in diagnostics if item.severity == "warning"]
    ok = not errors

    if getattr(args, "json", False):
        emit(
            envelope(
                "doctor",
                project=project_info(root),
                ok=ok,
                diagnostics=diagnostics,
                data={
                    "fix": bool(getattr(args, "fix", False)),
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                },
            )
        )
        return EXIT_OK if ok else EXIT_VALIDATION

    print(
        "sci doctor: {}".format(
            "OK" if ok else "problems found"
        )
    )
    if not diagnostics:
        print("  no problems")
        return EXIT_OK
    for item in diagnostics:
        location = "{}: ".format(item.path) if item.path else ""
        print(
            "  [{}] {}: {}{}".format(
                item.severity, item.code, location, item.message
            )
        )
        if item.hint:
            print("      hint: {}".format(item.hint))
    return EXIT_OK if ok else EXIT_VALIDATION
