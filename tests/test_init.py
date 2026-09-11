"""``sci init``: scaffold creation, safety, and independent Git history."""
import subprocess

import yaml

from sciharness.cli import main

EXPECTED_DIRS = (
    "docs",
    "docs/questions",
    "docs/decisions",
    "docs/guides",
    "data",
    "explorations",
    "experiments",
    "outputs",
    "outputs/explorations",
    "outputs/experiments",
    "src",
    "scripts",
    "tests",
)

EXPECTED_FILES = (
    "README.md",
    "AGENTS.md",
    ".gitignore",
    ".sci.yaml",
    ".agents/skills/scientific-research/SKILL.md",
    ".agents/skills/scientific-figures/SKILL.md",
    "docs/CHARTER.md",
    "docs/STATE.md",
    "docs/guides/FIGURES.md",
    "data/README.md",
    "data/registry.yaml",
)


def test_init_creates_intended_structure(tmp_path):
    target = tmp_path / "example"
    assert main(["init", str(target), "--name", "Example Scientific Project", "--no-git"]) == 0

    for relative in EXPECTED_DIRS:
        assert (target / relative).is_dir(), relative
    for relative in EXPECTED_FILES:
        assert (target / relative).is_file(), relative


def test_init_fills_name_and_date(tmp_path):
    target = tmp_path / "example"
    assert main(["init", str(target), "--name", "Example Scientific Project", "--no-git"]) == 0

    config = yaml.safe_load((target / ".sci.yaml").read_text(encoding="utf-8"))
    assert config["schema_version"] == 1
    assert config["project"]["name"] == "Example Scientific Project"
    assert config["project"]["created"]
    assert config["paths"]["questions"] == "docs/questions"
    assert config["paths"]["experiments"] == "experiments"

    for relative in ("README.md", "docs/CHARTER.md", "docs/STATE.md"):
        text = (target / relative).read_text(encoding="utf-8")
        assert "{{PROJECT_NAME}}" not in text
        assert "{{PROJECT_DATE}}" not in text
    assert "Example Scientific Project" in (target / "README.md").read_text(encoding="utf-8")


def test_init_defaults_name_to_directory(tmp_path):
    target = tmp_path / "my-project"
    assert main(["init", str(target), "--no-git"]) == 0
    config = yaml.safe_load((target / ".sci.yaml").read_text(encoding="utf-8"))
    assert config["project"]["name"] == "my-project"


def test_init_into_existing_empty_directory(tmp_path):
    target = tmp_path / "empty"
    target.mkdir()
    assert main(["init", str(target), "--name", "Empty Target", "--no-git"]) == 0
    assert (target / ".sci.yaml").is_file()


def test_init_into_non_empty_directory_fails_safely(tmp_path, capsys):
    target = tmp_path / "occupied"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("keep me\n", encoding="utf-8")

    assert main(["init", str(target), "--name", "Nope", "--no-git"]) == 1
    assert sentinel.read_text(encoding="utf-8") == "keep me\n"
    assert not (target / ".sci.yaml").exists()
    assert "not empty" in capsys.readouterr().err


def test_init_into_existing_file_fails(tmp_path, capsys):
    target = tmp_path / "a-file"
    target.write_text("data\n", encoding="utf-8")
    assert main(["init", str(target), "--name", "Nope", "--no-git"]) == 1
    assert "not a directory" in capsys.readouterr().err


def test_init_no_git_leaves_no_git_directory(tmp_path):
    target = tmp_path / "no-git"
    assert main(["init", str(target), "--name", "No Git", "--no-git"]) == 0
    assert not (target / ".git").exists()


def test_generated_project_has_independent_git_history(tmp_path):
    target = tmp_path / "git-project"
    assert main(["init", str(target), "--name", "Git Project"]) == 0

    assert (target / ".git").is_dir()

    log = subprocess.run(
        ["git", "log", "--format=%H %P %s"],
        cwd=str(target),
        check=True,
        capture_output=True,
        text=True,
    )
    lines = log.stdout.strip().splitlines()
    assert len(lines) == 1
    _sha, parents, subject = lines[0].split(" ", 2)
    # A root commit with no parents proves there is no inherited history.
    assert parents == ""
    assert subject == "Initialize scientific project"

    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(target),
        check=True,
        capture_output=True,
        text=True,
    )
    assert count.stdout.strip() == "1"

    remotes = subprocess.run(
        ["git", "remote"],
        cwd=str(target),
        check=True,
        capture_output=True,
        text=True,
    )
    assert remotes.stdout.strip() == ""

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=str(target),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert ".agents/skills/scientific-research/SKILL.md" in tracked.splitlines()
    assert ".agents/skills/scientific-figures/SKILL.md" in tracked.splitlines()
    assert "docs/guides/FIGURES.md" in tracked.splitlines()
    assert not any(line.startswith("outputs/") for line in tracked.splitlines())


def test_init_does_not_create_manuscript(project):
    assert not (project / "manuscript").exists()


def test_init_default_fails_when_git_unavailable(tmp_path, monkeypatch, capsys):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    target = tmp_path / "no-git-binary"

    assert main(["init", str(target), "--name", "No Git Binary"]) == 1
    # The scaffold exists, but init must not claim success.
    assert (target / ".sci.yaml").is_file()
    assert not (target / ".git").exists()
    captured = capsys.readouterr()
    assert "Git" in captured.err
    assert "Initialized scientific project" not in captured.out


def test_init_default_fails_when_git_command_fails(tmp_path, monkeypatch, capsys):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))
    target = tmp_path / "git-fails"

    assert main(["init", str(target), "--name", "Git Fails"]) == 1
    assert (target / ".sci.yaml").is_file()
    assert not (target / ".git").exists()
    captured = capsys.readouterr()
    assert "Git initialization" in captured.err
    assert "Initialized scientific project" not in captured.out


def test_init_no_git_succeeds_when_git_unavailable(tmp_path, monkeypatch):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    target = tmp_path / "explicit-no-git"

    assert main(["init", str(target), "--no-git"]) == 0
    assert (target / ".sci.yaml").is_file()
    assert not (target / ".git").exists()
