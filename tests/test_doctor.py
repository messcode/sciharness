"""``sci doctor``: structure, scaffold drift, and ID claim diagnostics."""
import json

from sciharness.cli import main


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def test_doctor_clean_project(project, capsys):
    assert main(["doctor", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "sci doctor: OK" in out
    assert "no problems" in out


def test_doctor_json_is_machine_readable(project, capsys):
    assert main(["doctor", "--path", str(project), "--json"]) == 0
    data = _json(capsys)
    assert data["command"] == "doctor"
    assert data["ok"] is True
    assert data["diagnostics"] == []
    assert data["error_count"] == 0


def test_doctor_reports_local_scaffold_modification(project, capsys):
    agents = project / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8"
    )
    assert main(["doctor", "--path", str(project), "--json"]) == 0
    data = _json(capsys)
    codes = {item["code"] for item in data["diagnostics"]}
    assert "MANAGED_FILE_MODIFIED" in codes


def test_doctor_reports_missing_scaffold_baseline(project, capsys):
    (project / ".sci" / "scaffold.json").unlink()
    assert main(["doctor", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "SCAFFOLD_MISSING" in out


def test_doctor_fix_adopts_missing_baseline_and_marks_pending(project, capsys):
    agents = project / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8"
    )
    (project / ".sci" / "scaffold.json").unlink()

    assert main(["doctor", "--path", str(project), "--fix", "--json"]) == 0
    data = _json(capsys)
    codes = {item["code"] for item in data["diagnostics"]}
    assert "SCAFFOLD_ADOPTED" in codes

    manifest = json.loads(
        (project / ".sci" / "scaffold.json").read_text(encoding="utf-8")
    )
    assert "AGENTS.md" in manifest["pending"]


def test_doctor_fix_backfills_id_claims(project, capsys):
    assert main(["new", "question", "Claimed", "--path", str(project)]) == 0
    claim = project / ".sci" / "ids" / "Q001"
    claim.unlink()

    assert main(["doctor", "--path", str(project)]) == 0
    assert "ID_UNCLAIMED" in capsys.readouterr().out
    assert main(["doctor", "--path", str(project), "--fix"]) == 0
    assert claim.is_file()


def test_doctor_exits_nonzero_on_validation_error(project, capsys):
    (project / "docs" / "STATE.md").unlink()
    assert main(["doctor", "--path", str(project), "--json"]) == 1
    data = _json(capsys)
    assert data["ok"] is False
    assert data["error_count"] >= 1
