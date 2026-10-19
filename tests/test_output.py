"""Machine-readable output, diagnostics, and stable exit codes."""
import json

from sciharness.cli import main
from sciharness.output import EXIT_OK, EXIT_PROJECT, EXIT_VALIDATION


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def test_init_json_reports_project_and_manifest(tmp_path, capsys):
    target = tmp_path / "json-project"
    assert (
        main(["init", str(target), "--name", "JSON Project", "--no-git", "--json"])
        == EXIT_OK
    )
    data = _json(capsys)
    assert data["schema_version"] == 1
    assert data["command"] == "init"
    assert data["ok"] is True
    assert data["project"]["name"] == "JSON Project"
    assert data["diagnostics"] == []
    assert (target / ".sci" / "scaffold.json").is_file()


def test_new_json_reports_record_and_outputs(project, capsys):
    assert (
        main(
            [
                "new",
                "experiment",
                "JSON experiment",
                "--path",
                str(project),
                "--json",
            ]
        )
        == EXIT_OK
    )
    data = _json(capsys)
    assert data["command"] == "new.experiment"
    assert data["kind"] == "experiment"
    assert data["id"] == "EXP001"
    assert data["record"].endswith("README.md")
    assert data["config"].endswith("config.yaml")
    assert data["outputs"].startswith("outputs/experiments/EXP001")


def test_status_and_context_json_are_stable(project, capsys):
    assert main(["new", "question", "JSON question", "--path", str(project)]) == EXIT_OK
    capsys.readouterr()

    assert main(["status", "--path", str(project), "--json"]) == EXIT_OK
    status = _json(capsys)
    assert status["command"] == "status"
    assert status["active"]["questions"][0]["id"] == "Q001"
    assert status["diagnostics"] == []

    assert main(["context", "--path", str(project), "--json"]) == EXIT_OK
    context = _json(capsys)
    assert context["command"] == "context"
    assert context["read_first"] == ["docs/CHARTER.md", "docs/STATE.md"]
    assert context["active"]["questions"][0]["id"] == "Q001"
    assert context["diagnostics"] == []


def test_show_json_includes_forward_and_backlinks(project, capsys):
    assert main(["new", "question", "Q", "--path", str(project)]) == EXIT_OK
    assert main(["new", "exploration", "X", "--question", "Q001", "--path", str(project)]) == EXIT_OK
    assert main(
        [
            "new",
            "decision",
            "D",
            "--evidence",
            "X001",
            "--path",
            str(project),
        ]
    ) == EXIT_OK
    capsys.readouterr()

    assert main(["show", "X001", "--path", str(project), "--json"]) == EXIT_OK
    data = _json(capsys)
    record = data["record"]
    assert record["id"] == "X001"
    assert record["references"][0]["target"] == "Q001"
    assert any(link["source"] == "D001" for link in record["backlinks"])


def test_json_validation_failure_exits_one(project, capsys):
    (project / "docs" / "STATE.md").unlink()
    assert main(["validate", "--path", str(project), "--json"]) == EXIT_VALIDATION
    data = _json(capsys)
    assert data["ok"] is False
    assert data["diagnostics"]
    assert data["diagnostics"][0]["severity"] == "error"
    assert data["diagnostics"][0]["path"] == ".sci.yaml"


def test_json_project_error_exits_three(project, capsys):
    assert main(["show", "Q999", "--path", str(project), "--json"]) == EXIT_PROJECT
    data = _json(capsys)
    assert data["ok"] is False
    assert data["command"] == "show"
    assert data["diagnostics"][0]["code"] == "PROJECT_ERROR"


def test_context_json_reports_stale_state(project, capsys):
    assert main(["new", "question", "Q", "--path", str(project)]) == EXIT_OK
    capsys.readouterr()
    state = project / "docs" / "STATE.md"
    lines = [
        "Updated: 2020-01-01" if line.startswith("Updated:") else line
        for line in state.read_text(encoding="utf-8").splitlines()
    ]
    state.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert main(["context", "--path", str(project), "--json"]) == EXIT_OK
    data = _json(capsys)
    assert any(
        item["code"] == "STATE_STALE" for item in data["diagnostics"]
    )


def test_figure_json_outputs_and_errors(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project), "--json"]) == EXIT_OK
    init_data = _json(capsys)
    assert init_data["command"] == "figure.init"
    assert init_data["path"].endswith("manuscript/figures/figure3")

    assert main(
        ["figure", "validate", "figure3", "--path", str(project), "--json"]
    ) == EXIT_OK
    validate_data = _json(capsys)
    assert validate_data["command"] == "figure.validate"
    assert validate_data["ok"] is True
    assert validate_data["diagnostics"] == []

    assert main(
        ["figure", "validate", "missing", "--path", str(project), "--json"]
    ) == EXIT_VALIDATION
    missing_data = _json(capsys)
    assert missing_data["ok"] is False
    assert "does not exist" in missing_data["diagnostics"][0]["message"]
