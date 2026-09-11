"""Generated-output workspaces and the tracked/ignored filesystem contract.

``outputs/`` holds generated computational artifacts and is gitignored.  The
exploration/experiment record directories remain Git tracked.
"""
import subprocess

from sciharness.cli import main

EXPLORATION_OUTPUT_DIRS = ("plots", "tables", "logs", "cache")
EXPERIMENT_OUTPUT_DIRS = ("plots", "tables", "logs", "checkpoints", "cache")


def _is_ignored(project, relative):
    result = subprocess.run(
        ["git", "-C", str(project), "check-ignore", "--quiet", relative],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


def test_new_exploration_creates_record_and_output_workspace(project):
    assert main(["new", "exploration", "Initial signal", "--path", str(project)]) == 0

    record = project / "explorations" / "X001-initial-signal" / "NOTE.md"
    assert record.is_file()
    for sub in EXPLORATION_OUTPUT_DIRS:
        assert (project / "outputs" / "explorations" / "X001" / sub).is_dir()


def test_new_experiment_creates_record_and_output_workspace(project):
    assert main(["new", "experiment", "Formal test", "--path", str(project)]) == 0

    folder = project / "experiments" / "EXP001-formal-test"
    assert (folder / "README.md").is_file()
    assert (folder / "config.yaml").is_file()
    for sub in EXPERIMENT_OUTPUT_DIRS:
        assert (project / "outputs" / "experiments" / "EXP001" / sub).is_dir()


def test_exploration_note_documents_relevant_outputs(project):
    assert main(["new", "exploration", "Initial signal", "--path", str(project)]) == 0
    text = (
        project / "explorations" / "X001-initial-signal" / "NOTE.md"
    ).read_text(encoding="utf-8")
    assert "## Relevant outputs" in text
    assert "outputs/explorations/X001/" in text


def test_experiment_readme_documents_generated_outputs(project):
    assert main(["new", "experiment", "Formal test", "--path", str(project)]) == 0
    text = (
        project / "experiments" / "EXP001-formal-test" / "README.md"
    ).read_text(encoding="utf-8")
    assert "## Generated outputs" in text
    assert "outputs/experiments/EXP001/" in text


def test_output_workspaces_are_gitignored(git_project):
    assert main(["new", "exploration", "Initial signal", "--path", str(git_project)]) == 0
    assert main(["new", "experiment", "Formal test", "--path", str(git_project)]) == 0

    assert _is_ignored(git_project, "outputs/explorations/X001/plots/thing.png")
    assert _is_ignored(git_project, "outputs/explorations/X001/tables/thing.csv")
    assert _is_ignored(git_project, "outputs/experiments/EXP001/logs/run.log")
    assert _is_ignored(git_project, "outputs/experiments/EXP001/checkpoints/ckpt.bin")


def test_record_directories_are_not_gitignored(git_project):
    assert main(["new", "exploration", "Initial signal", "--path", str(git_project)]) == 0
    assert main(["new", "experiment", "Formal test", "--path", str(git_project)]) == 0

    assert not _is_ignored(git_project, "explorations/X001-initial-signal/NOTE.md")
    assert not _is_ignored(git_project, "experiments/EXP001-formal-test/README.md")
    assert not _is_ignored(git_project, "experiments/EXP001-formal-test/config.yaml")
    assert not _is_ignored(git_project, "docs/guides/FIGURES.md")
