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
from .commands import doctor as doctor_command
from .commands import figure as figure_command
from .commands import init as init_command
from .commands import migrate as migrate_command
from .commands import new as new_command
from .commands import show as show_command
from .commands import start as start_command
from .commands import status as status_command
from .commands import upgrade as upgrade_command
from .commands import validate as validate_command
from .commands import web as web_command
from .output import EXIT_PROJECT, emit, error_envelope
from .project import ProjectError


def _add_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        default=".",
        help="Project directory (default: current directory; parent directories are searched).",
    )


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    _add_path_argument(parser)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one machine-readable JSON object (stable schema_version).",
    )


def _command_name(args: argparse.Namespace) -> str:
    command = getattr(args, "command", "sci")
    if command == "new":
        return "new.{}".format(getattr(args, "record_kind", "unknown"))
    if command == "figure":
        return "figure.{}".format(getattr(args, "figure_command", "unknown"))
    return command


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
    init_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one machine-readable JSON object (stable schema_version).",
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
    _add_output_arguments(status_parser)
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
    _add_output_arguments(context_parser)
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
    show_parser.add_argument(
        "--related",
        action="store_true",
        help="Also list incoming references (backlinks) from other records.",
    )
    _add_output_arguments(show_parser)
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
    validate_parser.add_argument(
        "--verify-hashes",
        action="store_true",
        help="Also verify declared local dataset sha256 values.",
    )
    _add_output_arguments(validate_parser)
    validate_parser.set_defaults(func=validate_command.run)

    start_parser = subparsers.add_parser(
        "start",
        help="Start a planned experiment and freeze its pre-registration",
        description=(
            "Move a planned experiment to status 'running' and record a hash of\n"
            "its pre-registered hypotheses, design, estimand, and decision rule\n"
            "in experiments/EXP###/run.yaml. Editing those sections afterwards\n"
            "makes `sci validate` fail."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    start_parser.add_argument("record_id", help="Experiment ID, e.g. EXP001.")
    _add_output_arguments(start_parser)
    start_parser.set_defaults(func=start_command.run)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose project structure, scaffold drift, and ID claims",
        description=(
            "Diagnose a project without changing it.\n\n"
            "Checks configuration and records with the same validator as `sci\n"
            "validate`, compares managed scaffold files with the recorded\n"
            "baseline and the installed package, and reports records that have\n"
            "no permanent ID claim. Use --fix to backfill ID claims and adopt a\n"
            "missing scaffold baseline."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arguments(doctor_parser)
    doctor_parser.add_argument(
        "--fix",
        action="store_true",
        help="Backfill missing ID claims and adopt a missing scaffold baseline.",
    )
    doctor_parser.set_defaults(func=doctor_command.run)

    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Update packaged scaffold files without clobbering local edits",
        description=(
            "Update the project's managed scaffold files.\n\n"
            "Files whose current hash still matches the recorded baseline are\n"
            "updated. Locally modified files are preserved and receive a .new\n"
            "sidecar unless --force is used. Use --dry-run to preview actions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arguments(upgrade_parser)
    upgrade_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned actions without writing files.",
    )
    upgrade_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite locally modified managed files instead of writing .new.",
    )
    upgrade_parser.set_defaults(func=upgrade_command.run)

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Migrate .sci.yaml to the supported schema version",
        description=(
            "Apply explicit, sequential project-config migrations.\n\n"
            "Migrates only .sci.yaml; records, figures, and scaffold files are\n"
            "handled by `sci upgrade` and their own schema_version fields. Use\n"
            "--dry-run to inspect the planned changes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arguments(migrate_parser)
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned migrations without writing .sci.yaml.",
    )
    migrate_parser.set_defaults(func=migrate_command.run)

    web_parser = subparsers.add_parser(
        "web",
        help="Serve a read-only decision-chain viewer",
        description=(
            "Serve a read-only local web viewer for the project's decision\n"
            "chain, provenance graph, and timeline.\n\n"
            "The server binds to 127.0.0.1 by default and only exposes the\n"
            "embedded UI plus a read-only graph API. Press Ctrl-C to stop."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_output_arguments(web_parser)
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1; use with care beyond localhost).",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port (default: 8765; use 0 for an ephemeral port).",
    )
    web_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the viewer in the default browser.",
    )
    web_parser.set_defaults(func=web_command.run)

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
    _add_output_arguments(question_parser)
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
    _add_output_arguments(exploration_parser)
    exploration_parser.add_argument(
        "--question", default=None, help="Link an existing question, e.g. Q001."
    )
    exploration_parser.add_argument(
        "--motivated-by",
        action="append",
        default=None,
        metavar="D###",
        help=(
            "Link a decision that motivated this exploration; repeatable, "
            "e.g. --motivated-by D001."
        ),
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
    _add_output_arguments(experiment_parser)
    experiment_parser.add_argument(
        "--question", default=None, help="Link an existing question, e.g. Q001."
    )
    experiment_parser.add_argument(
        "--exploration", default=None, help="Link an existing exploration, e.g. X001."
    )
    experiment_parser.add_argument(
        "--dataset",
        dest="datasets",
        action="append",
        default=None,
        metavar="DS###",
        help=(
            "Link a dataset declared in data/registry.yaml; repeatable, "
            "e.g. --dataset DS001."
        ),
    )
    experiment_parser.add_argument(
        "--motivated-by",
        action="append",
        default=None,
        metavar="D###",
        help=(
            "Link a decision that motivated this experiment; repeatable, "
            "e.g. --motivated-by D012."
        ),
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
    _add_output_arguments(decision_parser)
    decision_parser.add_argument(
        "--question", default=None, help="Link an existing question, e.g. Q001."
    )
    decision_parser.add_argument(
        "--experiment",
        default=None,
        help=(
            "Legacy compatibility input: link an existing experiment, e.g. "
            "EXP001. Recorded as Decision evidence."
        ),
    )
    decision_parser.add_argument(
        "--evidence",
        action="append",
        default=None,
        metavar="X###|EXP###",
        help=(
            "Link a scientific record reviewed as evidence; repeatable, "
            "e.g. --evidence X014 --evidence EXP007."
        ),
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
            "data. `sci figure approve` records review hashes; there is no\n"
            "`sci figure release` in v0.2."
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
    _add_output_arguments(figure_init_parser)
    figure_init_parser.set_defaults(func=figure_command.run)

    figure_approve_parser = figure_subparsers.add_parser(
        "approve",
        help="Record explicit approval of a validated figure",
        description=(
            "Record explicit human approval of a validated manuscript figure.\n\n"
            "Captures who approved it (--by), when, the current Git commit, and\n"
            "hashes of the manifest, FIGURE.md, release artifacts, and paired\n"
            "source data. `sci figure validate --release` re-checks those hashes,\n"
            "so later edits invalidate the approval. This command does not render\n"
            "or export anything."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    figure_approve_parser.add_argument(
        "figure_id", help="Figure identifier, e.g. figure3."
    )
    figure_approve_parser.add_argument(
        "--by",
        dest="approved_by",
        default=None,
        help="Who approves the figure (default: Git user.name, then $USER).",
    )
    _add_output_arguments(figure_approve_parser)
    figure_approve_parser.set_defaults(func=figure_command.run)

    figure_validate_parser = figure_subparsers.add_parser(
        "validate",
        help="Validate a manuscript figure",
        description=(
            "Validate the structure of a manuscript figure.\n\n"
            "Checks the figure directory, FIGURE.md, manifest.yaml, figure id,\n"
            "statuses, panel roles, declared paths, path escapes, release/output\n"
            "separation, duplicate release paths, declared experiments, and the\n"
            "declared style file. No scientific judgment is made.\n\n"
            "With --release, additionally require status 'validated' or\n"
            "'released', an explicit approval record written by `sci figure\n"
            "approve`, matching manifest/FIGURE/artifact hashes, every declared\n"
            "release output on disk, and every required paired source-data file\n"
            "on disk. Validation never mutates status or approval."
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
    _add_output_arguments(figure_validate_parser)
    figure_validate_parser.set_defaults(func=figure_command.run)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ProjectError as exc:
        if getattr(args, "json", False):
            emit(error_envelope(_command_name(args), str(exc)))
        else:
            print("sci: error: {}".format(exc), file=sys.stderr)
        # Usage/parser errors exit 2 via argparse; validation failures exit 1.
        # A missing or malformed project is a distinct category for agents.
        return EXIT_PROJECT


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
