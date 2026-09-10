"""Distribution checks: packaged resources, archives, and clean installation.

These tests build the real wheel and sdist from a copy of the source tree. The
``dev`` extra provides ``build`` and ``setuptools`` so the build runs with
``--no-isolation``.
"""
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

import sciharness

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILL = "sciharness/resources/skills/scientific-research/SKILL.md"
BUILD_TIMEOUT = 300


def _copy_source_tree(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("pyproject.toml", "README.md", "MANIFEST.in"):
        shutil.copy2(REPO_ROOT / name, destination / name)
    shutil.copytree(
        REPO_ROOT / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )


@pytest.fixture(scope="session")
def distributions(tmp_path_factory):
    source = tmp_path_factory.mktemp("sciharness-source")
    _copy_source_tree(source)
    output = tmp_path_factory.mktemp("sciharness-dist")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            str(source),
            "--no-isolation",
            "--sdist",
            "--wheel",
            "--outdir",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT,
    )
    assert result.returncode == 0, "build failed:\n{}\n{}".format(
        result.stdout, result.stderr
    )
    wheels = sorted(output.glob("sciharness-*.whl"))
    sdists = sorted(output.glob("sciharness-*.tar.gz"))
    assert len(wheels) == 1, "expected exactly one wheel, found: {}".format(wheels)
    assert len(sdists) == 1, "expected exactly one sdist, found: {}".format(sdists)
    return {"wheel": wheels[0], "sdist": sdists[0]}


def test_wheel_contains_canonical_skill_resource(distributions):
    with zipfile.ZipFile(str(distributions["wheel"])) as archive:
        names = archive.namelist()
    assert CANONICAL_SKILL in names


def test_sdist_contains_canonical_skill_resource(distributions):
    with tarfile.open(str(distributions["sdist"])) as archive:
        names = archive.getnames()
    assert any(name.endswith(CANONICAL_SKILL) for name in names)


def test_distribution_name_uses_package_version(distributions):
    version = sciharness.__version__
    assert distributions["wheel"].name == "sciharness-{}-py3-none-any.whl".format(version)
    assert distributions["sdist"].name == "sciharness-{}.tar.gz".format(version)


def test_wheel_installs_and_reports_version_in_clean_target(distributions, tmp_path):
    site = tmp_path / "site"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--target",
            str(site),
            str(distributions["wheel"]),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT,
    )

    scripts = [site / "bin" / "sci", site / "Scripts" / "sci.exe"]
    script = next((path for path in scripts if path.is_file()), None)
    assert script is not None, "console script `sci` was not installed"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(site)
    result = subprocess.run(
        [str(script), "--version"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "sci {}".format(sciharness.__version__)


def test_init_deploys_exact_canonical_skill(project):
    packaged = (
        Path(sciharness.__file__).resolve().parent
        / "resources"
        / "skills"
        / "scientific-research"
        / "SKILL.md"
    )
    deployed = project / ".agents" / "skills" / "scientific-research" / "SKILL.md"
    assert deployed.is_file()
    assert deployed.read_bytes() == packaged.read_bytes()


def test_generated_agents_md_is_minimal_bootstrap(project):
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "SciHarness" in agents
    assert "docs/CHARTER.md" in agents
    assert "docs/STATE.md" in agents
    assert ".agents/skills/scientific-research/SKILL.md" in agents
    assert "sci validate" in agents
    # The bootstrap must not duplicate the full research workflow.
    assert "Competing hypotheses" not in agents
    assert "Falsification" not in agents
    assert len(agents.splitlines()) <= 40
