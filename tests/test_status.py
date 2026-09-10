"""``sci status``: deterministic summaries and graceful failure."""
from sciharness.cli import main


def test_status_reports_active_records(project, capsys):
    assert main(["new", "question", "What predicts R_k(t)?", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "experiment",
            "Test accumulated forcing",
            "--question",
            "Q001",
            "--path",
            str(project),
        ]
    ) == 0

    assert main(["status", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "Project: Test Project" in out
    assert "Active questions" in out
    assert "Q001  What predicts R_k(t)?" in out
    assert "Active experiments" in out
    assert "EXP001  Test accumulated forcing" in out
    assert "no problems" in out


def test_status_handles_empty_project(project, capsys):
    assert main(["status", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "Validation" in out
    assert out.count("(none)") >= 1


def test_status_outside_a_project_fails(tmp_path, capsys):
    assert main(["status", "--path", str(tmp_path)]) == 1
    assert "no .sci.yaml" in capsys.readouterr().err
