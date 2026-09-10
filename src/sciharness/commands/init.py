"""``sci init``: create a new, independent scientific project."""
from __future__ import annotations

import datetime
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

import yaml

from ..project import (
    CONFIG_NAME,
    DEFAULT_PATHS,
    REQUIRED_DIRECTORIES,
    SUPPORTED_SCHEMA_VERSION,
    ProjectError,
)

TEMPLATE_DIR = (
    Path(__file__).resolve().parent.parent / "templates" / "project"
)

PLACEHOLDER_NAME = "{{PROJECT_NAME}}"
PLACEHOLDER_DATE = "{{PROJECT_DATE}}"

_COMMIT_MESSAGE = "Initialize scientific project"


def run(args: Any) -> int:
    target = Path(args.target).expanduser().resolve()
    name = (args.name or "").strip() or target.name
    today = datetime.date.today().isoformat()

    _prepare_target(target)
    _copy_template(TEMPLATE_DIR, target, {PLACEHOLDER_NAME: name, PLACEHOLDER_DATE: today})
    _create_directories(target)
    _write_config(target, name, today)

    if args.no_git:
        git_status = "skipped Git initialization (--no-git)"
    else:
        git_status = _init_git(target)

    print("Initialized scientific project {!r} in {}".format(name, target))
    print("  {}".format(git_status))
    print("  next: sci status --path {}".format(target))
    return 0


def _prepare_target(target: Path) -> None:
    if target.exists():
        if not target.is_dir():
            raise ProjectError(
                "target exists and is not a directory: {}".format(target)
            )
        entries = sorted(target.iterdir())
        if entries:
            shown = ", ".join(entry.name for entry in entries[:5])
            suffix = ", ..." if len(entries) > 5 else ""
            raise ProjectError(
                "target directory is not empty: {} ({}{})".format(target, shown, suffix)
            )
    else:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError("cannot create target directory {}: {}".format(target, exc)) from exc


def _copy_template(source: Path, target: Path, replacements: Dict[str, str]) -> None:
    if not source.is_dir():
        raise ProjectError("bundled project template is missing: {}".format(source))
    for entry in sorted(source.iterdir(), key=lambda path: path.name):
        if entry.name in (".git", "__pycache__"):
            continue
        destination = target / entry.name
        if entry.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            _copy_template(entry, destination, replacements)
            continue
        text = entry.read_text(encoding="utf-8")
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)
        destination.write_text(text, encoding="utf-8")


def _create_directories(target: Path) -> None:
    for relative in REQUIRED_DIRECTORIES:
        (target / relative).mkdir(parents=True, exist_ok=True)


def _write_config(target: Path, name: str, today: str) -> None:
    config = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "project": {"name": name, "created": today},
        "paths": dict(DEFAULT_PATHS),
    }
    text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    (target / CONFIG_NAME).write_text(text, encoding="utf-8")


def _init_git(target: Path) -> str:
    if shutil.which("git") is None:
        return "git not found; skipped Git initialization"
    try:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=str(target),
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(target),
            check=True,
            capture_output=True,
            text=True,
        )
        commit = ["git", "commit", "-q", "-m", _COMMIT_MESSAGE]
        result = subprocess.run(
            commit, cwd=str(target), capture_output=True, text=True
        )
        if result.returncode != 0:
            # Fall back to an explicit identity rather than modifying the
            # user's Git configuration; the initial commit still stands alone.
            fallback = [
                "git",
                "-c",
                "user.name=sciharness",
                "-c",
                "user.email=sciharness@localhost",
                "commit",
                "-q",
                "-m",
                _COMMIT_MESSAGE,
            ]
            subprocess.run(
                fallback,
                cwd=str(target),
                check=True,
                capture_output=True,
                text=True,
            )
    except (OSError, subprocess.CalledProcessError) as exc:
        return "warning: Git initialization failed ({}); project files are intact".format(
            exc
        )
    return "initialized Git repository with a fresh initial commit"
