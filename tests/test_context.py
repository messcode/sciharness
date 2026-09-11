"""``sci context``: deterministic agent routing, not scientific summary."""
import shutil

from sciharness.cli import main


def _seed(project):
    assert main(["new", "question", "What predicts R_k(t)?", "--path", str(project)]) == 0
    assert main(
        [
            "new",
            "exploration",
            "Early trajectory",
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
            "Second-order forcing",
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
            "Product law weakened",
            "--question",
            "Q001",
            "--experiment",
            "EXP001",
            "--path",
            str(project),
        ]
    ) == 0


def test_context_resolves_project_and_canonical_paths(project, capsys):
    _seed(project)
    assert main(["context", "--path", str(project)]) == 0
    out = capsys.readouterr().out

    assert "Project" in out
    assert "Test Project" in out

    assert "Read first" in out
    assert "docs/CHARTER.md" in out
    assert "docs/STATE.md" in out

    assert "Active questions" in out
    assert "Q001 → docs/questions/Q001-what-predicts-r-k-t.md" in out

    assert "Active explorations" in out
    assert "X001 → explorations/X001-early-trajectory/NOTE.md" in out

    assert "Active experiments" in out
    assert "EXP001 → experiments/EXP001-second-order-forcing/README.md" in out

    assert "Recent decisions" in out
    assert "D001 → docs/decisions/D001-product-law-weakened.md" in out

    assert "Conditional guidance" in out
    assert "docs/guides/FIGURES.md" in out


def test_context_is_deterministic(project, capsys):
    _seed(project)
    capsys.readouterr()
    assert main(["context", "--path", str(project)]) == 0
    first = capsys.readouterr().out
    assert main(["context", "--path", str(project)]) == 0
    assert capsys.readouterr().out == first


def test_context_does_not_require_generated_outputs(project, capsys):
    assert main(["new", "exploration", "Initial signal", "--path", str(project)]) == 0
    shutil.rmtree(project / "outputs")
    assert main(["context", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "X001" in out


def test_context_handles_empty_project(project, capsys):
    assert main(["context", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "(none)" in out


def test_context_omits_figure_guidance_when_absent(project, capsys):
    guide = project / "docs" / "guides" / "FIGURES.md"
    guide.unlink()
    assert main(["context", "--path", str(project)]) == 0
    assert "Conditional guidance" not in capsys.readouterr().out


def test_context_outside_a_project_fails(tmp_path, capsys):
    assert main(["context", "--path", str(tmp_path)]) == 1
    assert "no .sci.yaml" in capsys.readouterr().err


def test_old_v011_project_supports_navigation(project, capsys):
    # Simulate a v0.1.1 project: no figure guide, figure skill, or manuscript.
    guide_dir = project / "docs" / "guides"
    (guide_dir / "FIGURES.md").unlink()
    guide_dir.rmdir()
    figure_skill = project / ".agents" / "skills" / "scientific-figures"
    (figure_skill / "SKILL.md").unlink()
    figure_skill.rmdir()
    assert not (project / "manuscript").exists()

    assert main(["new", "question", "Old question", "--path", str(project)]) == 0
    assert main(["status", "--path", str(project)]) == 0
    assert main(["context", "--path", str(project)]) == 0
    assert main(["show", "Q001", "--path", str(project)]) == 0
    assert main(["validate", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "Q001" in out
    assert "Conditional guidance" not in out
