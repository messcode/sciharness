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
import yaml

import sciharness

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILL = "sciharness/resources/skills/scientific-research/SKILL.md"
SCIENTIFIC_FIGURES_SKILL = (
    "sciharness/resources/skills/scientific-figures/SKILL.md"
)
PACKAGED_TEMPLATE_PATHS = (
    "sciharness/templates/project/.gitignore",
    "sciharness/templates/project/AGENTS.md",
    "sciharness/templates/project/docs/guides/FIGURES.md",
    "sciharness/templates/figure/FIGURE.md",
    "sciharness/templates/figure/manifest.yaml",
)
BUILD_TIMEOUT = 300


def _copy_source_tree(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("pyproject.toml", "README.md", "MANIFEST.in", "LICENSE"):
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


def test_wheel_contains_figure_skill_and_templates(distributions):
    with zipfile.ZipFile(str(distributions["wheel"])) as archive:
        names = archive.namelist()
    assert SCIENTIFIC_FIGURES_SKILL in names
    for relative in PACKAGED_TEMPLATE_PATHS:
        assert relative in names, relative


def test_sdist_contains_canonical_skill_resource(distributions):
    with tarfile.open(str(distributions["sdist"])) as archive:
        names = archive.getnames()
    assert any(name.endswith(CANONICAL_SKILL) for name in names)


def test_sdist_contains_figure_skill_and_templates(distributions):
    with tarfile.open(str(distributions["sdist"])) as archive:
        names = archive.getnames()
    assert any(name.endswith(SCIENTIFIC_FIGURES_SKILL) for name in names)
    for relative in PACKAGED_TEMPLATE_PATHS:
        assert any(name.endswith(relative) for name in names), relative


def test_distribution_name_uses_package_version(distributions):
    version = sciharness.__version__
    assert distributions["wheel"].name == "sciharness-{}-py3-none-any.whl".format(version)
    assert distributions["sdist"].name == "sciharness-{}.tar.gz".format(version)


def test_distributions_include_license(distributions):
    def has_license(names):
        for name in names:
            basename = name.replace("\\", "/").rsplit("/", 1)[-1].upper()
            if basename.startswith("LICENSE") and "dist-info" in name:
                return True
        return False

    with zipfile.ZipFile(str(distributions["wheel"])) as archive:
        # Newer setuptools (PEP 639) uses .dist-info/licenses/LICENSE; older
        # setuptools uses .dist-info/LICENSE.  Accept either layout.
        assert has_license(archive.namelist())

    with tarfile.open(str(distributions["sdist"])) as archive:
        names = archive.getnames()
    assert any(
        name.replace("\\", "/").rsplit("/", 1)[-1].upper().startswith("LICENSE")
        for name in names
    )


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


def test_init_deploys_exact_figure_skill(project):
    packaged = (
        Path(sciharness.__file__).resolve().parent
        / "resources"
        / "skills"
        / "scientific-figures"
        / "SKILL.md"
    )
    deployed = project / ".agents" / "skills" / "scientific-figures" / "SKILL.md"
    assert deployed.is_file()
    assert deployed.read_bytes() == packaged.read_bytes()


def test_generated_agents_md_routes_figure_work(project):
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/guides/FIGURES.md" in agents
    assert "scientific-figures" in agents
    # Routing only: the full figure workflow lives in the guide and skill.
    assert "working/" not in agents
    assert "source_data" not in agents


def test_clean_wheel_supports_v02_workflow(distributions, tmp_path):
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
    project = tmp_path / "test-project"

    def run(*args, cwd):
        return subprocess.run(
            [str(script)] + list(args),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd),
            timeout=60,
        )

    result = run("init", str(project), "--no-git", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    result = run("new", "question", "Does intervention alter geometry?", cwd=project)
    assert result.returncode == 0, result.stderr
    result = run("new", "exploration", "Initial signal", cwd=project)
    assert result.returncode == 0, result.stderr
    result = run("new", "experiment", "Formal test", cwd=project)
    assert result.returncode == 0, result.stderr

    result = run("context", cwd=project)
    assert result.returncode == 0, result.stderr
    assert "docs/CHARTER.md" in result.stdout
    assert "Q001" in result.stdout
    assert "X001" in result.stdout
    assert "EXP001" in result.stdout

    for record_id in ("Q001", "X001", "EXP001"):
        result = run("show", record_id, cwd=project)
        assert result.returncode == 0, result.stderr
        assert record_id in result.stdout

    result = run("validate", cwd=project)
    assert result.returncode == 0, result.stderr

    result = run("figure", "init", "figure3", cwd=project)
    assert result.returncode == 0, result.stderr
    result = run("figure", "validate", "figure3", cwd=project)
    assert result.returncode == 0, result.stderr

    # Synthetic validated + approved figure with complete release artifacts.
    figure = project / "manuscript" / "figures" / "figure3"
    (figure / "release" / "main" / "with_legend").mkdir(
        parents=True, exist_ok=True
    )
    (figure / "release" / "main" / "with_legend" / "Fig3a.pdf").write_text(
        "pdf", encoding="utf-8"
    )
    (figure / "release" / "source_data").mkdir(parents=True, exist_ok=True)
    (figure / "release" / "source_data" / "Fig3a.csv").write_text(
        "x,y\n1,2\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "figure_id": "figure3",
        "status": "validated",
        "style_file": None,
        "release": {"approved": True},
        "panels": {
            "A": {
                "role": "main",
                "evidence": {"experiment": "EXP001"},
                "outputs": {
                    "with_legend": "release/main/with_legend/Fig3a.pdf"
                },
                "source_data": {
                    "required": True,
                    "files": ["release/source_data/Fig3a.csv"],
                },
            }
        },
    }
    (figure / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    result = run("figure", "validate", "figure3", "--release", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr

    subprocess.run(
        ["git", "-C", str(project), "init", "-q"],
        check=True,
        capture_output=True,
        text=True,
    )

    def ignored(relative):
        result = subprocess.run(
            ["git", "-C", str(project), "check-ignore", "--quiet", relative],
            capture_output=True,
            text=True,
        )
        assert result.returncode in (0, 1), result.stderr
        return result.returncode == 0

    assert ignored("outputs/explorations/X001/plots/plot.png")
    assert ignored("outputs/experiments/EXP001/logs/run.log")
    assert ignored("manuscript/figures/figure3/working/cache/state.pkl")
    assert ignored("manuscript/figures/figure3/previews/preview.pdf")
    assert not ignored("explorations/X001-initial-signal/NOTE.md")
    assert not ignored("manuscript/figures/figure3/FIGURE.md")
    assert not ignored("manuscript/figures/figure3/release/main/with_legend/Fig3a.pdf")


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
