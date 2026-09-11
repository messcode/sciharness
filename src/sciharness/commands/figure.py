"""``sci figure``: scaffold and validate manuscript figures.

SciHarness only structures and validates figure production.  It does not render
plots, export source data, or infer human approval.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..figures import init_figure, validate_figure
from ..project import ProjectError, find_project_root, relative_path


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    if args.figure_command == "init":
        return _run_init(root, args.figure_id)
    if args.figure_command == "validate":
        return _run_validate(root, args.figure_id, bool(args.release))
    raise ProjectError("unknown figure command: {}".format(args.figure_command))


def _run_init(root: Path, figure_id: str) -> int:
    target = init_figure(root, figure_id)
    print("Initialized manuscript figure {!r}".format(figure_id))
    print("  {}".format(relative_path(root, target)))
    print("  next: sci figure validate {}".format(figure_id))
    return 0


def _run_validate(root: Path, figure_id: str, release: bool) -> int:
    problems = validate_figure(root, figure_id, release=release)
    if problems:
        print(
            "Figure validation failed: {} problem(s) for {!r}".format(
                len(problems), figure_id
            )
        )
        for problem in problems:
            print("  - {}".format(problem))
        return 1
    if release:
        print("Figure release validation OK: {!r}".format(figure_id))
        print(
            "  status is validated; release is explicitly approved; declared "
            "artifacts and source data exist."
        )
    else:
        print("Figure validation OK: {!r}".format(figure_id))
        print("  structure, paths, roles, and references are valid.")
    return 0
