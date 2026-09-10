"""Command-line interface for sciharness."""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import __version__
from .commands import init as init_command
from .commands import new as new_command
from .commands import status as status_command
from .commands import validate as validate_command
from .project import ProjectError


def _add_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        default=".",
        help="Project directory (default: current directory; parent directories are searched).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sci",
        description=(
            "A lightweight, cross-agent scientific research harness. "
            "Scientific state lives in Markdown/YAML files."
        ),
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s {}".format(__version__)
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Create a new independent scientific project"
    )
    init_parser.add_argument(
        "target", help="Target directory (must be absent or empty)."
    )
    init_parser.add_argument(
        "--name",
        default=None,
        help="Project name (default: the target directory name).",
    )
    init_parser.add_argument(
        "--no-git",
        action="store_true",
        help="Do not initialize a Git repository in the new project.",
    )
    init_parser.set_defaults(func=init_command.run)

    status_parser = subparsers.add_parser(
        "status", help="Summarize project metadata from the filesystem"
    )
    _add_path_argument(status_parser)
    status_parser.set_defaults(func=status_command.run)

    validate_parser = subparsers.add_parser(
        "validate", help="Check structure, IDs, and references"
    )
    _add_path_argument(validate_parser)
    validate_parser.set_defaults(func=validate_command.run)

    new_parser = subparsers.add_parser("new", help="Create a scientific record")
    new_subparsers = new_parser.add_subparsers(dest="record_kind", required=True)

    question_parser = new_subparsers.add_parser(
        "question", help="Create a formal question (Q###)"
    )
    question_parser.add_argument("title", help="Short human-readable title.")
    _add_path_argument(question_parser)
    question_parser.set_defaults(func=new_command.run)

    exploration_parser = new_subparsers.add_parser(
        "exploration", help="Create a lightweight exploration (X###)"
    )
    exploration_parser.add_argument("title", help="Short human-readable title.")
    _add_path_argument(exploration_parser)
    exploration_parser.add_argument(
        "--question", default=None, help="Link an existing question, e.g. Q001."
    )
    exploration_parser.set_defaults(func=new_command.run)

    experiment_parser = new_subparsers.add_parser(
        "experiment", help="Create an evidence-bearing experiment (EXP###)"
    )
    experiment_parser.add_argument("title", help="Short human-readable title.")
    _add_path_argument(experiment_parser)
    experiment_parser.add_argument(
        "--question", default=None, help="Link an existing question, e.g. Q001."
    )
    experiment_parser.add_argument(
        "--exploration", default=None, help="Link an existing exploration, e.g. X001."
    )
    experiment_parser.set_defaults(func=new_command.run)

    decision_parser = new_subparsers.add_parser(
        "decision", help="Record a scientific decision (D###)"
    )
    decision_parser.add_argument("title", help="Short human-readable title.")
    _add_path_argument(decision_parser)
    decision_parser.add_argument(
        "--question", default=None, help="Link an existing question, e.g. Q001."
    )
    decision_parser.add_argument(
        "--experiment", default=None, help="Link an existing experiment, e.g. EXP001."
    )
    decision_parser.add_argument(
        "--supersedes", default=None, help="An earlier decision this one replaces, e.g. D001."
    )
    decision_parser.set_defaults(func=new_command.run)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ProjectError as exc:
        print("sci: error: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
