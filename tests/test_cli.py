"""CLI-level behavior: version reporting and semantic help text."""
import pytest

from sciharness import __version__
from sciharness.cli import main


def _help(*argv):
    with pytest.raises(SystemExit) as excinfo:
        main(list(argv) + ["--help"])
    assert excinfo.value.code == 0


def test_version_flag_reports_package_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == "sci {}".format(__version__)


def test_top_level_help_lists_commands(capsys):
    _help()
    out = capsys.readouterr().out
    for command in ("init", "status", "context", "show", "validate", "new", "figure"):
        assert command in out
    assert "Scientific state" in out


def test_new_help_lists_record_kinds(capsys):
    _help("new")
    out = capsys.readouterr().out
    for kind in ("question", "exploration", "experiment", "decision"):
        assert kind in out


def test_new_exploration_help_describes_adaptive_work(capsys):
    _help("new", "exploration")
    out = capsys.readouterr().out
    assert "adaptive" in out
    assert "outputs/explorations/X###/" in out


def test_new_experiment_help_describes_evidence_and_alternative(capsys):
    _help("new", "experiment")
    out = capsys.readouterr().out
    assert "evidence-bearing" in out
    assert "negative result" in out
    assert "sci new exploration" in out


def test_figure_help_variants(capsys):
    _help("figure")
    assert "manuscript" in capsys.readouterr().out

    _help("figure", "init")
    init_out = capsys.readouterr().out
    assert "lazily" in init_out
    assert "manifest.yaml" in init_out

    _help("figure", "validate")
    validate_out = capsys.readouterr().out
    assert "--release" in validate_out
    assert "release.approved" in validate_out


def test_context_and_show_help(capsys):
    _help("context")
    assert "read" in capsys.readouterr().out

    _help("show")
    assert "record" in capsys.readouterr().out
