"""``sci migrate``: explicit .sci.yaml schema migrations."""
import json

import yaml

from sciharness.cli import main


def _write_config(project, data):
    (project / ".sci.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def test_migrate_adds_missing_schema_version(project, capsys):
    config = yaml.safe_load((project / ".sci.yaml").read_text(encoding="utf-8"))
    config.pop("schema_version", None)
    _write_config(project, config)

    assert main(["validate", "--path", str(project)]) == 1
    assert "run `sci migrate`" in capsys.readouterr().out

    assert main(["migrate", "--path", str(project), "--dry-run"]) == 0
    assert "dry run" in capsys.readouterr().out
    assert "schema_version" not in (
        project / ".sci.yaml"
    ).read_text(encoding="utf-8")

    assert main(["migrate", "--path", str(project)]) == 0
    migrated = yaml.safe_load((project / ".sci.yaml").read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 1
    assert main(["validate", "--path", str(project)]) == 0


def test_migrate_is_idempotent(project, capsys):
    assert main(["migrate", "--path", str(project)]) == 0
    assert "schema is current" in capsys.readouterr().out


def test_migrate_json_reports_actions(project, capsys):
    config = yaml.safe_load((project / ".sci.yaml").read_text(encoding="utf-8"))
    config.pop("schema_version", None)
    _write_config(project, config)
    capsys.readouterr()

    assert main(["migrate", "--path", str(project), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["command"] == "migrate"
    assert data["before"] == 0
    assert data["after"] == 1
    assert data["actions"][0]["to_version"] == 1


def test_migrate_refuses_newer_schema(project, capsys):
    config = yaml.safe_load((project / ".sci.yaml").read_text(encoding="utf-8"))
    config["schema_version"] = 99
    _write_config(project, config)
    capsys.readouterr()

    assert main(["migrate", "--path", str(project)]) == 3
    assert "newer than supported" in capsys.readouterr().err
