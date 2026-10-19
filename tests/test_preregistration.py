"""Experiment pre-registration hashing and ``sci start``."""
import json

import yaml

from sciharness.cli import main


def _seed_design(project):
    assert main(["new", "experiment", "Prereg experiment", "--path", str(project)]) == 0
    record = project / "experiments" / "EXP001-prereg-experiment" / "README.md"
    text = record.read_text(encoding="utf-8")
    text = text.replace(
        "## Competing hypotheses\n",
        "## Competing hypotheses\n\nH1: forcing accumulates. H0: no effect.\n",
    )
    text = text.replace(
        "## Design\n", "## Design\n\nRandomized intervention with 30 units.\n"
    )
    text = text.replace(
        "## Primary estimand\n", "## Primary estimand\n\nMean difference in R_k.\n"
    )
    text = text.replace(
        "## Falsification / decision rule\n",
        "## Falsification / decision rule\n\nReject H0 if the 95% interval excludes 0.\n",
    )
    record.write_text(text, encoding="utf-8")
    return record


def test_start_freezes_preregistration_and_writes_run(project, capsys):
    _seed_design(project)
    capsys.readouterr()
    assert main(["start", "EXP001", "--path", str(project), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["record"] == "EXP001"
    assert data["run"] == "experiments/EXP001-prereg-experiment/run.yaml"
    assert len(data["preregistration_sha256"]) == 64

    record = project / "experiments" / "EXP001-prereg-experiment" / "README.md"
    front = yaml.safe_load(record.read_text(encoding="utf-8").split("---", 2)[1])
    assert front["status"] == "running"
    assert front["started"]

    run = yaml.safe_load(
        (
            project / "experiments" / "EXP001-prereg-experiment" / "run.yaml"
        ).read_text(encoding="utf-8")
    )
    assert run["record"] == "EXP001"
    assert run["preregistration_sha256"] == data["preregistration_sha256"]
    assert run["started_at"]
    assert main(["validate", "--path", str(project)]) == 0


def test_editing_preregistration_after_start_fails_validation(project, capsys):
    record = _seed_design(project)
    assert main(["start", "EXP001", "--path", str(project)]) == 0
    text = record.read_text(encoding="utf-8").replace(
        "H1: forcing accumulates. H0: no effect.",
        "H1: a different hypothesis.",
    )
    record.write_text(text, encoding="utf-8")

    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "pre-registration changed" in out


def test_editing_results_after_start_does_not_fail(project):
    record = _seed_design(project)
    assert main(["start", "EXP001", "--path", str(project)]) == 0
    text = record.read_text(encoding="utf-8").replace(
        "<!-- Fill in after the experiment is run. -->",
        "Observed a positive effect.",
    )
    record.write_text(text, encoding="utf-8")
    assert main(["validate", "--path", str(project)]) == 0


def test_start_requires_a_planned_experiment(project, capsys):
    _seed_design(project)
    assert main(["start", "EXP001", "--path", str(project)]) == 0
    capsys.readouterr()
    assert main(["start", "EXP001", "--path", str(project)]) == 3
    assert "must be 'planned'" in capsys.readouterr().err


def test_start_requires_an_experiment(project, capsys):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    capsys.readouterr()
    assert main(["start", "Q001", "--path", str(project)]) == 3
    assert "no experiment record" in capsys.readouterr().err
