"""Deterministic ID allocation and reference checks for ``sci new``."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sciharness.cli import main
from sciharness.project import read_front_matter


def test_question_ids_increment(project):
    assert main(["new", "question", "First question", "--path", str(project)]) == 0
    assert main(["new", "question", "Second question", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "docs/questions").glob("*.md"))
    assert names == ["Q001-first-question.md", "Q002-second-question.md"]


def test_question_ids_scan_existing_files(project):
    manual = project / "docs" / "questions" / "Q010-manual.md"
    manual.write_text(
        "---\nid: Q010\ntitle: Manual\nstatus: open\ncreated: 2026-01-01\n---\n\n# Q010\n",
        encoding="utf-8",
    )
    assert main(["new", "question", "Next", "--path", str(project)]) == 0
    assert (project / "docs" / "questions" / "Q011-next.md").is_file()
    # The manually created record is adopted into the permanent claim ledger.
    assert (project / ".sci" / "ids" / "Q010").is_file()


def test_exploration_ids_increment(project):
    assert main(["new", "exploration", "Inspect early trajectory", "--path", str(project)]) == 0
    assert main(["new", "exploration", "Second exploration", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "explorations").iterdir() if path.is_dir())
    assert names == ["X001-inspect-early-trajectory", "X002-second-exploration"]
    for name in names:
        assert (project / "explorations" / name / "NOTE.md").is_file()


def test_experiment_ids_increment(project):
    assert main(["new", "experiment", "Test accumulated forcing", "--path", str(project)]) == 0
    assert main(["new", "experiment", "Second experiment", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "experiments").iterdir() if path.is_dir())
    assert names == ["EXP001-test-accumulated-forcing", "EXP002-second-experiment"]
    first = project / "experiments" / names[0]
    assert (first / "README.md").is_file()
    assert (first / "config.yaml").is_file()


def test_decision_ids_increment(project):
    assert main(["new", "decision", "First decision", "--path", str(project)]) == 0
    assert main(["new", "decision", "Second decision", "--path", str(project)]) == 0

    names = sorted(path.name for path in (project / "docs/decisions").glob("*.md"))
    assert names == ["D001-first-decision.md", "D002-second-decision.md"]


def test_new_rejects_missing_reference(project, capsys):
    assert main(
        ["new", "exploration", "Broken", "--question", "Q999", "--path", str(project)]
    ) == 1
    assert "Q999" in capsys.readouterr().err
    assert [p for p in (project / "explorations").iterdir() if p.name != ".gitkeep"] == []


def test_new_records_existing_reference(project):
    assert main(["new", "question", "Linked question", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "exploration",
            "Linked exploration",
            "--question",
            "Q001",
            "--path",
            str(project),
        ]
    ) == 0

    note = project / "explorations" / "X001-linked-exploration" / "NOTE.md"
    data = read_front_matter(note)
    assert data["id"] == "X001"
    assert data["question"] == "Q001"
    assert data["status"] == "active"


def test_experiment_and_decision_links_are_recorded(project):
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
    assert main(
        [
            "new",
            "decision",
            "D",
            "--question",
            "Q001",
            "--experiment",
            "EXP001",
            "--supersedes",
            "D000",
            "--path",
            str(project),
        ]
    ) == 1  # D000 does not exist


def test_slug_handles_punctuation(project):
    assert main(["new", "question", "What predicts R_k(t)?", "--path", str(project)]) == 0
    assert (project / "docs" / "questions" / "Q001-what-predicts-r-k-t.md").is_file()


def test_deleted_highest_id_is_not_reused(project):
    for index in (1, 2):
        assert main(
            ["new", "experiment", "E{}".format(index), "--path", str(project)]
        ) == 0

    shutil.rmtree(project / "experiments" / "EXP002-e2")
    assert (project / ".sci" / "ids" / "EXP002").is_file()

    assert main(["new", "experiment", "After delete", "--path", str(project)]) == 0
    names = sorted(
        path.name for path in (project / "experiments").iterdir() if path.is_dir()
    )
    assert names == ["EXP001-e1", "EXP003-after-delete"]
    assert (project / "outputs" / "experiments" / "EXP003").is_dir()


def test_concurrent_new_explorations_get_distinct_ids(project):
    source = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = source + os.pathsep + env.get("PYTHONPATH", "")
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "sciharness.cli",
                "new",
                "exploration",
                "Parallel {}".format(index),
                "--path",
                str(project),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(6)
    ]
    for process in processes:
        _stdout, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, stderr

    names = sorted(
        path.name for path in (project / "explorations").iterdir() if path.is_dir()
    )
    ids = [name.split("-", 1)[0] for name in names]
    assert ids == ["X001", "X002", "X003", "X004", "X005", "X006"]
    assert main(["validate", "--path", str(project)]) == 0


def test_new_creates_missing_record_directory(project):
    shutil.rmtree(project / "explorations")
    assert main(["new", "exploration", "Recreated", "--path", str(project)]) == 0
    record = project / "explorations" / "X001-recreated" / "NOTE.md"
    assert record.is_file()
    assert (project / "explorations" / ".gitkeep").is_file()


def test_unicode_title_keeps_readable_filename(project):
    assert main(["new", "question", "中文标题测试", "--path", str(project)]) == 0
    assert (project / "docs" / "questions" / "Q001-中文标题测试.md").is_file()


def test_title_without_words_falls_back_to_record_id(project):
    assert main(["new", "question", "???", "--path", str(project)]) == 0
    assert (project / "docs" / "questions" / "Q001-Q001.md").is_file()
