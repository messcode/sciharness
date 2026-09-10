"""CLI-level behavior such as ``sci --version``."""
import pytest

from sciharness import __version__
from sciharness.cli import main


def test_version_flag_reports_package_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == "sci {}".format(__version__)
