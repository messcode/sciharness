"""Provenance edges: Decision.evidence and Exploration/Experiment.motivated_by.

These tests cover CLI creation, structural validation, legacy compatibility,
and display. They exercise relationships only; no scientific judgment is made.
"""
from pathlib import Path

import pytest
import yaml

from sciharness.cli import main
from sciharness.project import read_front_matter


def _base(project):
    """Create Q001, X001, EXP001, and a decision without provenance fields."""
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
    assert main(["new", "decision", "D", "--question", "Q001", "--path", str(project)]) == 0


def _decision_path(project):
    return sorted((project / "docs" / "decisions").glob("D*.md"))[0]


def _exploration_path(project):
    return sorted((project / "explorations").glob("X*"))[0] / "NOTE.md"


def _experiment_path(project):
    return sorted((project / "experiments").glob("EXP*"))[0] / "README.md"


def _patch(path, **fields):
    data = read_front_matter(path)
    data.update(fields)
    text = "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n\n# record\n"
    Path(path).write_text(text, encoding="utf-8")


def _write(path, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "---\n" + yaml.safe_dump(fields, sort_keys=False) + "---\n\n# record\n"
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI creation
# ---------------------------------------------------------------------------


def test_decision_single_evidence(project):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    assert main(["new", "exploration", "X", "--question", "Q001", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "decision",
            "D",
            "--question",
            "Q001",
            "--evidence",
            "X001",
            "--path",
            str(project),
        ]
    ) == 0
    data = read_front_matter(_decision_path(project))
    assert data["evidence"] == ["X001"]
    assert "experiment" not in data


def test_decision_multiple_evidence(project):
    _base(project)
    assert main(
        [
            "new",
            "decision",
            "D2",
            "--question",
            "Q001",
            "--evidence",
            "X001",
            "--evidence",
            "EXP001",
            "--path",
            str(project),
        ]
    ) == 0
    data = read_front_matter(sorted((project / "docs" / "decisions").glob("D002*.md"))[0])
    assert data["evidence"] == ["X001", "EXP001"]


def test_decision_mixed_evidence_preserves_order(project):
    _base(project)
    assert main(
        [
            "new",
            "decision",
            "D2",
            "--question",
            "Q001",
            "--evidence",
            "EXP001",
            "--evidence",
            "X001",
            "--path",
            str(project),
        ]
    ) == 0
    data = read_front_matter(sorted((project / "docs" / "decisions").glob("D002*.md"))[0])
    assert data["evidence"] == ["EXP001", "X001"]


def test_decision_legacy_experiment_is_canonicalized(project):
    assert main(["new", "experiment", "E", "--path", str(project)]) == 0
    assert main(
        ["new", "decision", "D", "--experiment", "EXP001", "--path", str(project)]
    ) == 0
    data = read_front_matter(_decision_path(project))
    assert data["evidence"] == ["EXP001"]
    assert "experiment" not in data


def test_decision_experiment_and_evidence_merge(project):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    assert main(["new", "exploration", "X", "--question", "Q001", "--path", str(project)]) == 0
    for title in ("E1", "E2"):
        assert main(["new", "experiment", title, "--question", "Q001", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "decision",
            "D",
            "--question",
            "Q001",
            "--experiment",
            "EXP001",
            "--evidence",
            "X001",
            "--evidence",
            "EXP002",
            "--path",
            str(project),
        ]
    ) == 0
    data = read_front_matter(_decision_path(project))
    assert data["evidence"] == ["EXP001", "X001", "EXP002"]
    assert "experiment" not in data


def test_decision_duplicate_cli_inputs_are_deduplicated(project):
    _base(project)
    assert main(
        [
            "new",
            "decision",
            "D2",
            "--experiment",
            "EXP001",
            "--evidence",
            "X001",
            "--evidence",
            "X001",
            "--evidence",
            "EXP001",
            "--path",
            str(project),
        ]
    ) == 0
    data = read_front_matter(sorted((project / "docs" / "decisions").glob("D002*.md"))[0])
    assert data["evidence"] == ["EXP001", "X001"]


def test_decision_rejects_evidence_of_wrong_type(project, capsys):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    assert main(
        ["new", "decision", "D", "--evidence", "Q001", "--path", str(project)]
    ) == 1
    assert "must reference an existing X### or EXP###" in capsys.readouterr().err


def test_exploration_motivated_by_single(project):
    assert main(["new", "decision", "D", "--path", str(project)]) == 0
    assert main(
        ["new", "exploration", "X", "--motivated-by", "D001", "--path", str(project)]
    ) == 0
    data = read_front_matter(_exploration_path(project))
    assert data["motivated_by"] == ["D001"]


def test_exploration_motivated_by_multiple(project):
    assert main(["new", "decision", "D1", "--path", str(project)]) == 0
    assert main(["new", "decision", "D2", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "exploration",
            "X",
            "--motivated-by",
            "D001",
            "--motivated-by",
            "D002",
            "--path",
            str(project),
        ]
    ) == 0
    data = read_front_matter(_exploration_path(project))
    assert data["motivated_by"] == ["D001", "D002"]


def test_experiment_motivated_by_single(project):
    assert main(["new", "decision", "D", "--path", str(project)]) == 0
    assert main(
        ["new", "experiment", "E", "--motivated-by", "D001", "--path", str(project)]
    ) == 0
    data = read_front_matter(_experiment_path(project))
    assert data["motivated_by"] == ["D001"]
    config = yaml.safe_load(
        (_experiment_path(project).parent / "config.yaml").read_text(encoding="utf-8")
    )
    assert config["motivated_by"] == ["D001"]


def test_experiment_motivated_by_multiple(project):
    assert main(["new", "decision", "D1", "--path", str(project)]) == 0
    assert main(["new", "decision", "D2", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "experiment",
            "E",
            "--motivated-by",
            "D001",
            "--motivated-by",
            "D002",
            "--path",
            str(project),
        ]
    ) == 0
    data = read_front_matter(_experiment_path(project))
    assert data["motivated_by"] == ["D001", "D002"]


def test_experiment_rejects_motivated_by_of_wrong_type(project, capsys):
    assert main(["new", "exploration", "X", "--path", str(project)]) == 0
    assert main(
        ["new", "experiment", "E", "--motivated-by", "X001", "--path", str(project)]
    ) == 1
    assert "must reference an existing D###" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


def test_validate_accepts_evidence_and_motivated_by(project):
    _base(project)
    _patch(_decision_path(project), evidence=["X001", "EXP001"])
    _patch(_exploration_path(project), motivated_by=["D001"])
    _patch(_experiment_path(project), motivated_by=["D001"])
    assert main(["validate", "--path", str(project)]) == 0


def test_validate_rejects_non_list_evidence(project, capsys):
    _base(project)
    _patch(_decision_path(project), evidence="X001")
    assert main(["validate", "--path", str(project)]) == 1
    assert "evidence must be a YAML list" in capsys.readouterr().out


def test_validate_rejects_non_list_motivated_by(project, capsys):
    _base(project)
    _patch(_exploration_path(project), motivated_by="D001")
    assert main(["validate", "--path", str(project)]) == 1
    assert "motivated_by must be a YAML list" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["Q001", "D001"])
def test_validate_rejects_wrong_evidence_type(project, capsys, bad):
    _base(project)
    _patch(_decision_path(project), evidence=[bad])
    assert main(["validate", "--path", str(project)]) == 1
    assert "must be an ID of type X### or EXP###" in capsys.readouterr().out


def test_validate_rejects_wrong_motivated_by_type(project, capsys):
    _base(project)
    _patch(_experiment_path(project), motivated_by=["EXP001"])
    assert main(["validate", "--path", str(project)]) == 1
    assert "must be an ID of type D###" in capsys.readouterr().out


def test_validate_rejects_non_string_evidence(project, capsys):
    _base(project)
    _patch(_decision_path(project), evidence=[123])
    assert main(["validate", "--path", str(project)]) == 1
    assert "must be a non-empty string ID" in capsys.readouterr().out


def test_validate_rejects_missing_evidence_ref(project, capsys):
    _base(project)
    _patch(_decision_path(project), evidence=["EXP999"])
    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "EXP999" in out
    assert "not found" in out


def test_validate_rejects_missing_motivated_by_ref(project, capsys):
    _base(project)
    _patch(_exploration_path(project), motivated_by=["D999"])
    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "D999" in out
    assert "not found" in out


def test_validate_rejects_duplicate_evidence(project, capsys):
    _base(project)
    _patch(_decision_path(project), evidence=["EXP001", "EXP001"])
    assert main(["validate", "--path", str(project)]) == 1
    assert "duplicate ID 'EXP001'" in capsys.readouterr().out


def test_validate_rejects_duplicate_motivated_by(project, capsys):
    _base(project)
    _patch(_experiment_path(project), motivated_by=["D001", "D001"])
    assert main(["validate", "--path", str(project)]) == 1
    assert "duplicate ID 'D001'" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Legacy compatibility
# ---------------------------------------------------------------------------


def test_validate_accepts_legacy_decision_experiment(project):
    assert main(["new", "experiment", "E", "--path", str(project)]) == 0
    _write(
        project / "docs" / "decisions" / "D001-legacy.md",
        {
            "id": "D001",
            "title": "Legacy decision",
            "status": "active",
            "created": "2026-01-01",
            "experiment": "EXP001",
        },
    )
    assert main(["validate", "--path", str(project)]) == 0


def test_validate_accepts_records_without_new_fields(project):
    _base(project)
    data = read_front_matter(_decision_path(project))
    assert "evidence" not in data
    assert main(["validate", "--path", str(project)]) == 0


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def test_show_decision_displays_evidence(project, capsys):
    _base(project)
    _patch(_decision_path(project), evidence=["X001", "EXP001"])
    assert main(["show", "D001", "--path", str(project)]) == 0
    assert "Evidence: X001, EXP001" in capsys.readouterr().out


def test_show_exploration_displays_motivated_by(project, capsys):
    _base(project)
    _patch(_exploration_path(project), motivated_by=["D001"])
    assert main(["show", "X001", "--path", str(project)]) == 0
    assert "Motivated by: D001" in capsys.readouterr().out


def test_show_experiment_displays_motivated_by(project, capsys):
    _base(project)
    _patch(_experiment_path(project), motivated_by=["D001"])
    assert main(["show", "EXP001", "--path", str(project)]) == 0
    assert "Motivated by: D001" in capsys.readouterr().out


def test_show_legacy_decision_displays_experiment(project, capsys):
    assert main(["new", "experiment", "E", "--path", str(project)]) == 0
    _write(
        project / "docs" / "decisions" / "D001-legacy.md",
        {
            "id": "D001",
            "title": "Legacy decision",
            "status": "active",
            "created": "2026-01-01",
            "experiment": "EXP001",
        },
    )
    assert main(["show", "D001", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "Experiment: EXP001" in out
    assert "Evidence:" not in out
