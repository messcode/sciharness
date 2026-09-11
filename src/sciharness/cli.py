"""Command-line interface for sciharness.

The CLI performs deterministic bookkeeping, navigation, and validation.
Scientific interpretation stays with the researcher and the host agent.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import __version__
from .commands import context as context_command
from .commands import figure as figure_command
from .commands import init as init_command
from .commands import new as new_command
from .commands import show as show_command
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
            "A lightweight, cross-agent scientific research harness.\n\n"
            "Scientific state lives in Markdown/YAML files. The `sci` CLI performs\n"
            "deterministic bookkeeping, navigation, and validation; scientific\n"
            "interpretation stays with the researcher and the host agent."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s {}".format(__version__)
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="COMMAND"
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Create a new independent scientific project",
        description=(
            "Create a new independent scientific project.\n\n"
            "Copies the bundled scaffold, fills the project name and date, deploys\n"
            "the portable Agent Skills, writes .sci.yaml, and initializes a fresh\n"
            "Git repository with a single root commit (use --no-git to skip). The\n"
            "generated project never inherits SciHarness history or remotes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "status",
        help="Summarize the scientific objects that exist",
        description=(
            "Summarize the scientific objects and their states.\n\n"
            "Use `sci context` to learn what an agent should read now, and\n"
            "`sci show ID` to locate one specific record."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_path_argument(status_parser)
    status_parser.set_defaults(func=status_command.run)

    context_parser = subparsers.add_parser(
        "context",
        help="Show what an agent should read now",
        description=(
            "Print deterministic agent bootstrap/routing for this project.\n\n"
            "Shows the project name, the files to read first, active questions,\n"
            "explorations, and experiments, recent decisions, and conditional\n"
            "guidance. It does not summarize scientific conclusions or inspect\n"
            "generated artifacts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_path_argument(context_parser)
    context_parser.set_defaults(func=context_command.run)

    show_parser = subparsers.add_parser(
        "show",
        help="Locate one record by its stable ID",
        description=(
            "Resolve a stable record ID (Q###, X###, EXP###, D###) to its\n"
            "canonical record path and generated-output workspace.\n\n"
            "Deterministic navigation only: it does not dump full scientific\n"
            "content or summarize with an LLM."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show_parser.add_argument("record_id", help="Record ID, e.g. Q003, X014, EXP012, D008.")
    _add_path_argument(show_parser)
    show_parser.set_defaults(func=show_command.run)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Check structure, IDs, and references",
        description=(
            "Check project configuration, expected paths, IDs, required fields,\n"
            "and references. Validation never makes scientific judgments."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_path_argument(validate_parser)
    validate_parser.set_defaults(func=validate_command.run)

    new_parser = subparsers.add_parser(
        "new",
        help="Create a scientific record",
        description=(
            "Create a scientific record with a deterministic ID.\n\n"
            "Records: question (Q###), exploration (X###), experiment (EXP###),\n"
            "decision (D###). IDs are allocated by the CLI, never by hand."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    new_subparsers = new_parser.add_subparsers(
        dest="record_kind", required=True, metavar="KIND"
    )

    question_parser = new_subparsers.add_parser(
        "question",
        help="Create a formal question (Q###)",
        description=(
            "Create a formal scientific question (Q###).\n\n"
            "A question is an unresolved scientific issue the project is trying\n"
            "to resolve — not a task and not a passing curiosity."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    question_parser.add_argument("title", help="Short human-readable title.")
    _add_path_argument(question_parser)
    question_parser.set_defaults(func=new_command.run)

    exploration_parser = new_subparsers.add_parser(
        "exploration",
        help="Create a lightweight exploration (X###)",
        description=(
            "Create a lightweight exploration (X###).\n\n"
            "Use an exploration for adaptive, revisable work: trying metrics,\n"
            "inspecting plots, following unexpected signals. Explorations do not\n"
            "require preregistered endpoints or formal decision thresholds.\n\n"
            "Generated artifacts belong under outputs/explorations/X###/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    exploration_parser.add_argument("title", help="Short human-readable title.")
    _add_path_argument(exploration_parser)
    exploration_parser.add_argument(
        "--question", default=None, help="Link an existing question, e.g. Q001."
    )
    exploration_parser.set_defaults(func=new_command.run)

    experiment_parser = new_subparsers.add_parser(
        "experiment",
        help="Create an evidence-bearing experiment (EXP###)",
        description=(
            "Create an evidence-bearing scientific experiment (EXP###).\n\n"
            "Use an experiment when a scientific question is important enough to\n"
            "test with an explicit design and a negative result would still be\n"
            "scientifically informative. Declare competing hypotheses, design,\n"
            "primary estimand, and the decision/falsification rule before running.\n\n"
            "For adaptive exploratory work, use:\n"
            "    sci new exploration"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "decision",
        help="Record a scientific decision (D###)",
        description=(
            "Record a scientific decision (D###).\n\n"
            "A decision records a change in scientific belief, hypothesis status,\n"
            "or research direction — not an ordinary implementation choice.\n"
            "Decisions are append-only; supersede an earlier decision instead of\n"
            "rewriting it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    figure_parser = subparsers.add_parser(
        "figure",
        help="Scaffold and validate manuscript figures",
        description=(
            "Scaffold and validate manuscript figures.\n\n"
            "Figure production is separate from the scientific experiment\n"
            "lifecycle. SciHarness defines and validates structure; project-\n"
            "specific scripts render the final visual and export paired source\n"
            "data. There is no `sci figure release` in v0.2."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    figure_subparsers = figure_parser.add_subparsers(
        dest="figure_command", required=True, metavar="ACTION"
    )

    figure_init_parser = figure_subparsers.add_parser(
        "init",
        help="Create a manuscript figure workspace",
        description=(
            "Create a manuscript figure workspace (lazily).\n\n"
            "Creates manuscript/figures/<id>/ with FIGURE.md, manifest.yaml,\n"
            "mutable working/ and previews/, and a Git-tracked release/\n"
            "structure. Ordinary `sci init` never creates figure directories."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    figure_init_parser.add_argument(
        "figure_id", help="Figure identifier, e.g. figure3."
    )
    _add_path_argument(figure_init_parser)
    figure_init_parser.set_defaults(func=figure_command.run)

    figure_validate_parser = figure_subparsers.add_parser(
        "validate",
        help="Validate a manuscript figure",
        description=(
            "Validate the structure of a manuscript figure.\n\n"
            "Checks the figure directory, FIGURE.md, manifest.yaml, figure id,\n"
            "statuses, panel roles, declared paths, path escapes, release/output\n"
            "separation, duplicate release paths, declared experiments, and the\n"
            "declared style file. No scientific judgment is made.\n\n"
            "With --release, additionally require status 'validated', explicit\n"
            "human approval (release.approved: true), every declared release\n"
            "output on disk, and every required paired source-data file on disk.\n"
            "Validation never mutates status or approval."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    figure_validate_parser.add_argument(
        "figure_id", help="Figure identifier, e.g. figure3."
    )
    figure_validate_parser.add_argument(
        "--release",
        action="store_true",
        help="Also check release readiness (approval, artifacts, source data).",
    )
    _add_path_argument(figure_validate_parser)
    figure_validate_parser.set_defaults(func=figure_command.run)

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
