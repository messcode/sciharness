"""Deterministic ID allocation and reference checks for ``sci new``."""
from sciharness.cli import main
from sciharness.project import read_front_matter


def test_question_ids_increment(project):
    assert main(["new", "question", "First question", "--path", str(project)]) == 0
    assert main(["new", "question", "Second question", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "docs/questions").glob("*.md"))
    assert names == ["Q001-first-question.md", "Q002-second-question.md"]


def test_question_ids_scan_existing_files(project):
    manual = project / "docs" / "questions" / "Q010-manual.md"
    manual.write_text(
        "---\nid: Q010\ntitle: Manual\nstatus: open\ncreated: 2026-01-01\n---\n\n# Q010\n",
        encoding="utf-8",
    )
    assert main(["new", "question", "Next", "--path", str(project)]) == 0
    assert (project / "docs" / "questions" / "Q011-next.md").is_file()


def test_exploration_ids_increment(project):
    assert main(["new", "exploration", "Inspect early trajectory", "--path", str(project)]) == 0
    assert main(["new", "exploration", "Second exploration", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "explorations").iterdir() if path.is_dir())
    assert names == ["X001-inspect-early-trajectory", "X002-second-exploration"]
    for name in names:
        assert (project / "explorations" / name / "NOTE.md").is_file()


def test_experiment_ids_increment(project):
    assert main(["new", "experiment", "Test accumulated forcing", "--path", str(project)]) == 0
    assert main(["new", "experiment", "Second experiment", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "experiments").iterdir() if path.is_dir())
    assert names == ["EXP001-test-accumulated-forcing", "EXP002-second-experiment"]
    first = project / "experiments" / names[0]
    assert (first / "README.md").is_file()
    assert (first / "config.yaml").is_file()


def test_decision_ids_increment(project):
    assert main(["new", "decision", "First decision", "--path", str(project)]) == 0
    assert main(["new", "decision", "Second decision", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "docs/decisions").glob("*.md"))
    assert names == ["D001-first-decision.md", "D002-second-decision.md"]


def test_new_rejects_missing_reference(project, capsys):
    assert main(
        ["new", "exploration", "Broken", "--question", "Q999", "--path", str(project)]
    ) == 1
    assert "Q999" in capsys.readouterr().err
    assert list((project / "explorations").iterdir()) == []


def test_new_records_existing_reference(project):
    assert main(["new", "question", "Linked question", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "exploration",
            "Linked exploration",
            "--question",
            "Q001",
            "--path",
            str(project),
        ]
    ) == 0

    note = project / "explorations" / "X001-linked-exploration" / "NOTE.md"
    data = read_front_matter(note)
    assert data["id"] == "X001"
    assert data["question"] == "Q001"
    assert data["status"] == "active"


def test_experiment_and_decision_links_are_recorded(project):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    assert main(["new", "exploration", "X", "--question", "Q001", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "experiment",
            "E",
            "--question",
            "Q001",
            "--exploration",
            "X001",
            "--path",
            str(project),
        ]
    ) == 0
    assert main(
        [
            "new",
            "decision",
            "D",
            "--question",
            "Q001",
            "--experiment",
            "EXP001",
            "--supersedes",
            "D000",
            "--path",
            str(project),
        ]
    ) == 1  # D000 does not exist


def test_slug_handles_punctuation(project):
    assert main(["new", "question", "What predicts R_k(t)?", "--path", str(project)]) == 0
    assert (project / "docs" / "questions" / "Q001-what-predicts-r-k-t.md").is_file()
