"""Generated YAML and front matter must parse with a standard YAML parser."""
import yaml

from sciharness.cli import main
from sciharness.project import read_front_matter


def _create_all_records(project):
    assert main(["new", "question", "Parsing question", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "exploration",
            "Parsing exploration",
            "--question",
            "Q001",
            "--path",
            str(project),
        ]
    ) == 0
    assert main(
        [
            "new",
            "experiment",
            "Parsing experiment",
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
            "Parsing decision",
            "--question",
            "Q001",
            "--experiment",
            "EXP001",
            "--path",
            str(project),
        ]
    ) == 0


def test_generated_yaml_parses(project):
    config = yaml.safe_load((project / ".sci.yaml").read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    assert config["schema_version"] == 1
    assert config["project"]["name"] == "Test Project"

    registry = yaml.safe_load((project / "data" / "registry.yaml").read_text(encoding="utf-8"))
    assert isinstance(registry, dict)
    assert registry["datasets"] == []


def test_generated_front_matter_parses(project):
    _create_all_records(project)

    question = read_front_matter(
        project / "docs" / "questions" / "Q001-parsing-question.md"
    )
    assert question["id"] == "Q001"
    assert question["title"] == "Parsing question"
    assert question["status"] == "open"
    assert question["created"]

    exploration = read_front_matter(
        project / "explorations" / "X001-parsing-exploration" / "NOTE.md"
    )
    assert exploration["id"] == "X001"
    assert exploration["question"] == "Q001"

    experiment_readme = read_front_matter(
        project / "experiments" / "EXP001-parsing-experiment" / "README.md"
    )
    assert experiment_readme["id"] == "EXP001"
    assert experiment_readme["question"] == "Q001"
    assert experiment_readme["exploration"] == "X001"

    experiment_config = yaml.safe_load(
        (
            project / "experiments" / "EXP001-parsing-experiment" / "config.yaml"
        ).read_text(encoding="utf-8")
    )
    assert experiment_config["id"] == experiment_readme["id"]
    assert experiment_config["title"] == experiment_readme["title"]

    decision = read_front_matter(
        project / "docs" / "decisions" / "D001-parsing-decision.md"
    )
    assert decision["id"] == "D001"
    assert decision["question"] == "Q001"
    # ``--experiment`` is a legacy compatibility input recorded canonically as
    # Decision evidence; new records do not write a separate ``experiment``.
    assert decision["evidence"] == ["EXP001"]
    assert "experiment" not in decision
