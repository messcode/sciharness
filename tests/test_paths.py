"""Configured ``.sci.yaml`` paths must stay inside the project root.

A malformed or agent-edited configuration must never let the CLI read or write
outside the SciHarness project.
"""
import pytest
import yaml

from sciharness.cli import main


def _set_paths(project, **paths):
    config = yaml.safe_load((project / ".sci.yaml").read_text(encoding="utf-8"))
    config["paths"].update(paths)
    (project / ".sci.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )


def test_safe_relative_paths_still_work(project):
    assert main(["new", "question", "Safe", "--path", str(project)]) == 0
    assert main(["validate", "--path", str(project)]) == 0


def test_relative_traversal_rejected_without_writing(project, tmp_path, capsys):
    outside = tmp_path / "outside-questions"
    _set_paths(project, questions="../outside-questions")

    assert main(["new", "question", "Escape", "--path", str(project)]) == 1
    assert not outside.exists()
    captured = capsys.readouterr()
    assert "paths.questions" in captured.err
    assert ".." in captured.err


def test_absolute_path_rejected_without_writing(project, tmp_path, capsys):
    outside = tmp_path / "abs-questions"
    _set_paths(project, questions=str(outside))

    assert main(["new", "question", "Escape", "--path", str(project)]) == 1
    assert not outside.exists()
    assert "project-relative" in capsys.readouterr().err


def test_windows_absolute_path_rejected(project, capsys):
    _set_paths(project, questions="C:\\outside\\questions")
    assert main(["new", "question", "Escape", "--path", str(project)]) == 1
    assert "project-relative" in capsys.readouterr().err


def test_home_relative_path_rejected(project, capsys):
    _set_paths(project, questions="~/outside-questions")
    assert main(["new", "question", "Escape", "--path", str(project)]) == 1
    assert "project-relative" in capsys.readouterr().err


def test_symlink_escape_rejected_without_writing(project, tmp_path, capsys):
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    link = project / "docs" / "questions-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported on this platform")
    _set_paths(project, questions="docs/questions-link")

    assert main(["new", "question", "Escape", "--path", str(project)]) == 1
    assert list(outside.iterdir()) == []
    assert "escapes the project root" in capsys.readouterr().err


def test_validate_reports_unsafe_configured_path(project, capsys):
    _set_paths(project, questions="../outside-questions")
    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "paths.questions" in out
    assert "traversal" in out


def test_unsafe_state_path_fails_validation(project, capsys):
    _set_paths(project, state="../STATE.md")
    assert main(["validate", "--path", str(project)]) == 1
    assert "paths.state" in capsys.readouterr().out
