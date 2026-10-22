"""Core and extension build independently, with one-way dependencies."""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def test_separate_distributions_and_entrypoints(tmp_path):
    extension = Path(__file__).resolve().parents[1]
    repo = extension.parents[1]
    wheels = {}
    for name, source in (("core", repo), ("loop", extension)):
        copied = tmp_path / name
        copied.mkdir()
        for filename in ("pyproject.toml", "README.md", "LICENSE", "MANIFEST.in", "CHANGELOG.md"):
            if (source / filename).exists():
                shutil.copy2(source / filename, copied / filename)
        shutil.copytree(source / "src", copied / "src", ignore=shutil.ignore_patterns(
            "__pycache__", "*.egg-info"))
        output = tmp_path / (name + "-dist")
        result = subprocess.run([sys.executable, "-m", "build", str(copied), "--wheel",
                                 "--no-isolation", "--outdir", str(output)],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        wheels[name] = next(output.glob("*.whl"))
    with zipfile.ZipFile(wheels["core"]) as archive:
        names = archive.namelist()
        metadata = archive.read(next(n for n in names if n.endswith("/METADATA"))).decode()
        requirements = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]
        assert not any("sciharness-loop" in line for line in requirements)
        assert not any(n.startswith("sciharness_loop/") for n in names)
        entry = archive.read(next(n for n in names if n.endswith("/entry_points.txt"))).decode()
        assert "sci = sciharness.cli:main" in entry and "sci-loop" not in entry
    with zipfile.ZipFile(wheels["loop"]) as archive:
        names = archive.namelist()
        assert "sciharness_loop/executor.py" in names
        metadata = archive.read(next(n for n in names if n.endswith("/METADATA"))).decode()
        assert "Requires-Dist: sciharness" in metadata
        assert not any(n.startswith("sciharness/") for n in names)
    target = tmp_path / "installed"
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation",
                    "--target", str(target), str(wheels["core"]), str(wheels["loop"])],
                   check=True, capture_output=True, timeout=60)
    env = {**os.environ, "PYTHONPATH": str(target)}
    for module in ("sciharness.cli", "sciharness_loop.cli"):
        result = subprocess.run([sys.executable, "-m", module, "--version"],
                                cwd=tmp_path, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
