"""``sci figure``: scaffold, approve, and validate manuscript figures.

SciHarness only structures and validates figure production.  It does not render
plots, export source data, or infer human approval.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..figures import approve_figure, init_figure, validate_figure
from ..output import (
    EXIT_OK,
    EXIT_VALIDATION,
    diagnostics_from_problems,
    emit,
    envelope,
    project_info,
)
from ..project import ProjectError, find_project_root, relative_path


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    json_mode = bool(getattr(args, "json", False))
    if args.figure_command == "init":
        return _run_init(root, args.figure_id, json_mode)
    if args.figure_command == "approve":
        return _run_approve(root, args.figure_id, args.approved_by, json_mode)
    if args.figure_command == "validate":
        return _run_validate(
            root, args.figure_id, bool(args.release), json_mode
        )
    raise ProjectError("unknown figure command: {}".format(args.figure_command))


def _run_init(root: Path, figure_id: str, json_mode: bool) -> int:
    target = init_figure(root, figure_id)
    relative = relative_path(root, target)
    if json_mode:
        emit(
            envelope(
                "figure.init",
                project=project_info(root),
                data={
                    "figure_id": figure_id,
                    "path": relative,
                    "next": "sci figure validate {}".format(figure_id),
                },
            )
        )
        return EXIT_OK
    print("Initialized manuscript figure {!r}".format(figure_id))
    print("  {}".format(relative))
    print("  next: sci figure validate {}".format(figure_id))
    return EXIT_OK


def _run_approve(
    root: Path, figure_id: str, approved_by: Any, json_mode: bool
) -> int:
    approval_path = approve_figure(root, figure_id, approved_by)
    relative = relative_path(root, approval_path)
    if json_mode:
        emit(
            envelope(
                "figure.approve",
                project=project_info(root),
                data={
                    "figure_id": figure_id,
                    "approval": relative,
                    "next": "sci figure validate {} --release".format(figure_id),
                },
            )
        )
        return EXIT_OK
    print("Approved manuscript figure {!r}".format(figure_id))
    print("  {}".format(relative))
    print("  review hashes recorded; `sci figure validate --release` will verify them")
    return EXIT_OK


def _run_validate(
    root: Path, figure_id: str, release: bool, json_mode: bool
) -> int:
    problems = validate_figure(root, figure_id, release=release)
    diagnostics = diagnostics_from_problems(problems)
    if json_mode:
        emit(
            envelope(
                "figure.validate",
                project=project_info(root),
                ok=not problems,
                diagnostics=diagnostics,
                data={
                    "figure_id": figure_id,
                    "release": release,
                    "problem_count": len(problems),
                },
            )
        )
        return EXIT_OK if not problems else EXIT_VALIDATION
    if problems:
        print(
            "Figure validation failed: {} problem(s) for {!r}".format(
                len(problems), figure_id
            )
        )
        for problem in problems:
            print("  - {}".format(problem))
        return EXIT_VALIDATION
    if release:
        print("Figure release validation OK: {!r}".format(figure_id))
        print(
            "  status is validated or released; approval hashes match; "
            "declared artifacts and source data exist."
        )
    else:
        print("Figure validation OK: {!r}".format(figure_id))
        print("  structure, paths, roles, and references are valid.")
    return EXIT_OK
