"""Shared fixtures for the sciharness test-suite."""
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciharness.cli import main  # noqa: E402


@pytest.fixture
def project(tmp_path):
    """An initialized project with Git disabled (faster, filesystem only)."""
    target = tmp_path / "project"
    assert main(["init", str(target), "--name", "Test Project", "--no-git"]) == 0
    return target


@pytest.fixture
def git_project(project):
    """A project with a real Git repository for ignore checks."""
    subprocess.run(
        ["git", "-C", str(project), "init", "-q"],
        check=True,
        capture_output=True,
        text=True,
    )
    return project
