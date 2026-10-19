"""Dataset registry validation and experiment dataset links."""
import hashlib

import yaml

from sciharness.cli import main


def _write_registry(project, datasets):
    (project / "data" / "registry.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": 1, "datasets": datasets}, sort_keys=False
        ),
        encoding="utf-8",
    )


def _local_dataset(project, identifier="DS001", name="Run 01", path="data/raw/run01.csv"):
    target = project / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x,y\n1,2\n", encoding="utf-8")
    return {
        "id": identifier,
        "name": name,
        "path": path,
        "source": "simulation",
        "acquired": "2026-01-01",
    }


def test_valid_local_dataset_registry_passes(project):
    _write_registry(project, [_local_dataset(project)])
    assert main(["validate", "--path", str(project)]) == 0


def test_registry_rejects_bad_ids_and_duplicates(project, capsys):
    _write_registry(
        project,
        [
            _local_dataset(project, "DS001", "A", "data/a.csv"),
            _local_dataset(project, "DS001", "B", "data/b.csv"),
            _local_dataset(project, "dataset", "C", "data/c.csv"),
        ],
    )
    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "duplicate dataset id" in out
    assert "must look like DS###" in out


def test_registry_requires_local_path_and_external_uri(project, capsys):
    _write_registry(
        project,
        [
            {"id": "DS001", "name": "No path"},
            {"id": "DS002", "name": "No uri", "storage": "external"},
        ],
    )
    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "path is required" in out
    assert "uri is required" in out


def test_registry_checks_missing_local_file(project, capsys):
    _write_registry(
        project,
        [{"id": "DS001", "name": "Missing", "path": "data/missing.csv"}],
    )
    assert main(["validate", "--path", str(project)]) == 1
    assert "does not exist" in capsys.readouterr().out


def test_registry_schema_version_is_required(project, capsys):
    (project / "data" / "registry.yaml").write_text(
        yaml.safe_dump({"datasets": []}), encoding="utf-8"
    )
    assert main(["validate", "--path", str(project)]) == 1
    assert "schema_version must be 1" in capsys.readouterr().out


def test_verify_hashes_checks_local_sha256(project, capsys):
    dataset = _local_dataset(project)
    digest = hashlib.sha256(
        (project / dataset["path"]).read_bytes()
    ).hexdigest()
    dataset["sha256"] = digest
    _write_registry(project, [dataset])
    assert main(["validate", "--verify-hashes", "--path", str(project)]) == 0

    dataset["sha256"] = "0" * 64
    _write_registry(project, [dataset])
    assert main(["validate", "--verify-hashes", "--path", str(project)]) == 1
    assert "does not match" in capsys.readouterr().out


def test_new_experiment_links_declared_dataset(project):
    _write_registry(project, [_local_dataset(project)])
    assert (
        main(
            [
                "new",
                "experiment",
                "Dataset experiment",
                "--dataset",
                "DS001",
                "--path",
                str(project),
            ]
        )
        == 0
    )
    record = project / "experiments" / "EXP001-dataset-experiment" / "README.md"
    front = yaml.safe_load(
        record.read_text(encoding="utf-8").split("---", 2)[1]
    )
    assert front["datasets"] == ["DS001"]
    assert main(["validate", "--path", str(project)]) == 0


def test_new_experiment_rejects_undeclared_dataset(project, capsys):
    assert (
        main(
            [
                "new",
                "experiment",
                "Bad dataset",
                "--dataset",
                "DS999",
                "--path",
                str(project),
            ]
        )
        == 3
    )
    assert "data/registry.yaml" in capsys.readouterr().err


def test_experiment_dataset_reference_must_exist(project, capsys):
    assert main(["new", "experiment", "E", "--path", str(project)]) == 0
    record = project / "experiments" / "EXP001-e" / "README.md"
    text = record.read_text(encoding="utf-8").replace(
        "status: planned", "status: planned\ndatasets: [DS999]"
    )
    record.write_text(text, encoding="utf-8")
    assert main(["validate", "--path", str(project)]) == 1
    assert "not declared in data/registry.yaml" in capsys.readouterr().out


def test_show_displays_datasets(project, capsys):
    _write_registry(project, [_local_dataset(project)])
    assert (
        main(
            [
                "new",
                "experiment",
                "Dataset experiment",
                "--dataset",
                "DS001",
                "--path",
                str(project),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["show", "EXP001", "--path", str(project)]) == 0
    assert "Datasets: DS001" in capsys.readouterr().out


def test_run_yaml_is_validated(project):
    _write_registry(project, [_local_dataset(project)])
    assert main(["new", "experiment", "E", "--path", str(project)]) == 0
    folder = project / "experiments" / "EXP001-e"
    (folder / "run.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "record": "EXP001",
                "command": "python scripts/run.py",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T01:00:00+00:00",
                "code_commit": "abc123",
                "environment": {"python": "3.12"},
                "datasets": ["DS001"],
                "seeds": {"numpy": 0},
                "outputs_manifest": "outputs/experiments/EXP001/manifest.json",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert main(["validate", "--path", str(project)]) == 0


def test_run_yaml_rejects_bad_record_and_timestamp(project, capsys):
    assert main(["new", "experiment", "E", "--path", str(project)]) == 0
    folder = project / "experiments" / "EXP001-e"
    (folder / "run.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "record": "EXP999",
                "started_at": "yesterday",
                "datasets": ["DS999"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "does not match EXP001" in out
    assert "ISO timestamp" in out
    assert "DS999" in out
