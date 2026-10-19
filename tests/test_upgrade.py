"""``sci upgrade``: update unmodified scaffold files, preserve local edits."""
import hashlib
import json

from sciharness import __version__
from sciharness.cli import main


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest(project):
    return json.loads(
        (project / ".sci" / "scaffold.json").read_text(encoding="utf-8")
    )


def test_upgrade_is_a_noop_on_a_fresh_project(project, capsys):
    assert main(["upgrade", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "scaffold is up to date" in out


def test_upgrade_updates_an_unmodified_file(project, capsys):
    agents = project / "AGENTS.md"
    original = agents.read_text(encoding="utf-8")
    old = "# old scaffold\n"
    agents.write_text(old, encoding="utf-8")

    manifest = _manifest(project)
    manifest["files"]["AGENTS.md"] = _sha256(old)
    (project / ".sci" / "scaffold.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert main(["upgrade", "--path", str(project), "--dry-run"]) == 0
    dry_out = capsys.readouterr().out
    assert "update" in dry_out
    assert "AGENTS.md" in dry_out
    assert agents.read_text(encoding="utf-8") == old

    assert main(["upgrade", "--path", str(project)]) == 0
    assert agents.read_text(encoding="utf-8") == original
    updated = _manifest(project)
    assert updated["sciharness_version"] == __version__
    assert updated["files"]["AGENTS.md"] == _sha256(original)
    assert "pending" not in updated


def test_upgrade_preserves_local_edits_with_a_sidecar(project, capsys):
    agents = project / "AGENTS.md"
    original = agents.read_text(encoding="utf-8")
    local = original + "\nlocal note\n"
    agents.write_text(local, encoding="utf-8")

    assert main(["upgrade", "--path", str(project), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert any(
        action["path"] == "AGENTS.md" and action["action"] == "sidecar"
        for action in data["actions"]
    )
    assert data["pending"] == ["AGENTS.md"]
    assert agents.read_text(encoding="utf-8") == local
    assert (project / "AGENTS.md.new").read_text(encoding="utf-8") == original

    # Reviewing the sidecar and accepting it resolves the pending state.
    (project / "AGENTS.md.new").replace(agents)
    assert main(["upgrade", "--path", str(project)]) == 0
    assert "pending" not in _manifest(project)


def test_upgrade_force_overwrites_local_edits(project, capsys):
    agents = project / "AGENTS.md"
    original = agents.read_text(encoding="utf-8")
    agents.write_text(original + "\nlocal note\n", encoding="utf-8")

    assert main(["upgrade", "--path", str(project), "--force"]) == 0
    assert agents.read_text(encoding="utf-8") == original
    assert "pending" not in _manifest(project)
    assert not (project / "AGENTS.md.new").exists()


def test_upgrade_requires_a_scaffold_baseline(project, capsys):
    (project / ".sci" / "scaffold.json").unlink()
    assert main(["upgrade", "--path", str(project)]) == 3
    assert "no scaffold baseline" in capsys.readouterr().err


def test_upgrade_reports_actions_as_json(project, capsys):
    assert main(["upgrade", "--path", str(project), "--dry-run", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["command"] == "upgrade"
    assert data["dry_run"] is True
    assert data["pending"] == []
    assert data["actions"]
