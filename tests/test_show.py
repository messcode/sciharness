"""``sci show``: deterministic ID resolution and canonical locations."""
from sciharness.cli import main


def test_show_resolves_question(project, capsys):
    assert main(["new", "question", "A question", "--path", str(project)]) == 0
    assert main(["show", "Q001", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "Q001" in out
    assert "Title: A question" in out
    assert "Status: open" in out
    assert "docs/questions/Q001-a-question.md" in out


def test_show_resolves_exploration_with_question_and_outputs(project, capsys):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    assert main(
        ["new", "exploration", "X", "--question", "Q001", "--path", str(project)]
    ) == 0
    assert main(["show", "X001", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "X001" in out
    assert "Question: Q001" in out
    assert "explorations/X001-x/NOTE.md" in out
    assert "outputs/explorations/X001/" in out


def test_show_resolves_experiment_with_references(project, capsys):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    assert main(
        ["new", "exploration", "X", "--question", "Q001", "--path", str(project)]
    ) == 0
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
    assert main(["show", "EXP001", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "EXP001" in out
    assert "Question: Q001" in out
    assert "Source exploration: X001" in out
    assert "experiments/EXP001-e/README.md" in out
    assert "outputs/experiments/EXP001/" in out


def test_show_resolves_decision_and_supersedes(project, capsys):
    assert main(["new", "decision", "First", "--path", str(project)]) == 0
    assert main(
        ["new", "decision", "Second", "--supersedes", "D001", "--path", str(project)]
    ) == 0
    assert main(["show", "D002", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "D002" in out
    assert "Supersedes: D001" in out
    assert "docs/decisions/D002-second.md" in out


def test_show_accepts_lowercase_id(project, capsys):
    assert main(["new", "question", "A question", "--path", str(project)]) == 0
    assert main(["show", "q001", "--path", str(project)]) == 0
    assert "Q001" in capsys.readouterr().out


def test_show_unknown_id_fails(project, capsys):
    assert main(["show", "Q999", "--path", str(project)]) == 1
    assert "no question record with id 'Q999'" in capsys.readouterr().err


def test_show_unrecognized_id_fails(project, capsys):
    assert main(["show", "nonsense", "--path", str(project)]) == 1
    assert "unrecognized record id" in capsys.readouterr().err


def test_show_ambiguous_id_fails(project, capsys):
    directory = project / "docs" / "questions"
    for suffix in ("alpha", "beta"):
        (directory / "Q001-{}.md".format(suffix)).write_text(
            "---\n"
            "id: Q001\n"
            "title: Duplicate {}\n"
            "status: open\n"
            "created: 2026-01-01\n"
            "---\n\n"
            "# Q001\n".format(suffix),
            encoding="utf-8",
        )
    assert main(["show", "Q001", "--path", str(project)]) == 1
    assert "ambiguous" in capsys.readouterr().err


def test_show_outside_a_project_fails(tmp_path, capsys):
    assert main(["show", "Q001", "--path", str(tmp_path)]) == 1
    assert "no .sci.yaml" in capsys.readouterr().err
