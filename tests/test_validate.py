"""``sci validate``: structural checks and broken-reference detection."""
from sciharness.cli import main


def _seed_valid_records(project):
    assert main(["new", "question", "A question", "--path", str(project)]) == 0
    assert main(
        ["new", "exploration", "An exploration", "--question", "Q001", "--path", str(project)]
    ) == 0
    assert main(
        [
            "new",
            "experiment",
            "An experiment",
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
            "A decision",
            "--question",
            "Q001",
            "--experiment",
            "EXP001",
            "--path",
            str(project),
        ]
    ) == 0


def test_validate_freshly_initialized_project(project):
    assert main(["validate", "--path", str(project)]) == 0


def test_validate_clean_project(project, capsys):
    _seed_valid_records(project)
    assert main(["validate", "--path", str(project)]) == 0
    assert "Validation OK" in capsys.readouterr().out


def test_validate_catches_broken_reference(project, capsys):
    broken = project / "explorations" / "X001-broken"
    broken.mkdir()
    (broken / "NOTE.md").write_text(
        "---\n"
        "id: X001\n"
        "title: Broken reference\n"
        "status: active\n"
        "created: 2026-01-01\n"
        "question: Q999\n"
        "---\n\n"
        "# X001\n",
        encoding="utf-8",
    )

    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "Q999" in out
    assert "question records" in out


def test_validate_catches_duplicate_ids(project, capsys):
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

    assert main(["validate", "--path", str(project)]) == 1
    out = capsys.readouterr().out
    assert "duplicate id" in out


def test_validate_catches_missing_configured_path(project, capsys):
    (project / "docs" / "STATE.md").unlink()
    assert main(["validate", "--path", str(project)]) == 1
    assert "paths.state" in capsys.readouterr().out


def test_validate_catches_unparseable_front_matter(project, capsys):
    (project / "docs" / "questions" / "Q001-bad.md").write_text(
        "This file has no front matter.\n", encoding="utf-8"
    )
    assert main(["validate", "--path", str(project)]) == 1
    assert "missing YAML front matter" in capsys.readouterr().out


def test_validate_catches_mismatched_experiment_config(project, capsys):
    assert main(["new", "experiment", "Config mismatch", "--path", str(project)]) == 0
    config = project / "experiments" / "EXP001-config-mismatch" / "config.yaml"
    config.write_text(
        "id: EXP999\ntitle: Config mismatch\nstatus: planned\ncreated: 2026-01-01\n",
        encoding="utf-8",
    )
    assert main(["validate", "--path", str(project)]) == 1
    assert "does not match README.md front matter" in capsys.readouterr().out


def test_validate_checks_supersedes_order(project, capsys):
    assert main(["new", "decision", "First", "--path", str(project)]) == 0
    directory = project / "docs" / "decisions"
    (directory / "D002-replacement.md").write_text(
        "---\n"
        "id: D002\n"
        "title: Replacement\n"
        "status: active\n"
        "created: 2026-01-02\n"
        "supersedes: D003\n"
        "---\n\n"
        "# D002\n",
        encoding="utf-8",
    )
    (directory / "D003-other.md").write_text(
        "---\n"
        "id: D003\n"
        "title: Other\n"
        "status: active\n"
        "created: 2026-01-03\n"
        "---\n\n"
        "# D003\n",
        encoding="utf-8",
    )
    assert main(["validate", "--path", str(project)]) == 1
    assert "earlier decision" in capsys.readouterr().out
