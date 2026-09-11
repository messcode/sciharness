"""``sci figure``: scaffolding, structural validation, and release checks."""
import subprocess

import pytest
import yaml

from sciharness.cli import main

FIGURE_LEAF_DIRS = (
    "working/exploratory",
    "working/validation",
    "working/cache",
    "working/legacy",
    "previews",
    "release/main/with_legend",
    "release/main/without_legend_text",
    "release/supplementary/with_text",
    "release/supplementary/without_text",
    "release/caption",
    "release/source_data",
)

RELEASE_GITKEEP_DIRS = (
    "release/main/with_legend",
    "release/main/without_legend_text",
    "release/supplementary/with_text",
    "release/supplementary/without_text",
    "release/caption",
    "release/source_data",
)


def _write_file(path, text="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_manifest(project, data, figure_id="figure3"):
    path = project / "manuscript" / "figures" / figure_id / "manifest.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _manifest(**overrides):
    data = {
        "schema_version": 1,
        "figure_id": "figure3",
        "status": "working",
        "style_file": None,
        "release": {"approved": False},
        "panels": {},
    }
    data.update(overrides)
    return data


def _create_experiment(project, experiment_id="EXP007"):
    folder = project / "experiments" / "{}-evidence".format(experiment_id)
    folder.mkdir(parents=True, exist_ok=True)
    front = (
        "---\nid: {0}\ntitle: Evidence\nstatus: completed\ncreated: '2026-01-01'\n"
        "---\n\n# {0}\n".format(experiment_id)
    )
    (folder / "README.md").write_text(front, encoding="utf-8")
    (folder / "config.yaml").write_text(
        "id: {0}\ntitle: Evidence\nstatus: completed\ncreated: '2026-01-01'\n".format(
            experiment_id
        ),
        encoding="utf-8",
    )
    return folder


def _main_panel(outputs=None, source_data=None, experiment="EXP007"):
    panel = {"role": "main"}
    if experiment is not None:
        panel["evidence"] = {"experiment": experiment}
    if outputs is not None:
        panel["outputs"] = outputs
    if source_data is not None:
        panel["source_data"] = source_data
    return panel


def _make_release_ready(project, figure_id="figure3"):
    assert main(["figure", "init", figure_id, "--path", str(project)]) == 0
    _create_experiment(project, "EXP007")
    figure = project / "manuscript" / "figures" / figure_id
    _write_file(figure / "release" / "main" / "with_legend" / "Fig3a.pdf", "pdf")
    _write_file(figure / "release" / "source_data" / "Fig3a.csv", "x,y\n1,2\n")
    data = _manifest(
        figure_id=figure_id,
        status="validated",
        release={"approved": True},
        panels={
            "A": {
                "role": "main",
                "evidence": {"experiment": "EXP007"},
                "generator": {"file": "scripts/figure3.py", "target": "panel_a"},
                "outputs": {"with_legend": "release/main/with_legend/Fig3a.pdf"},
                "source_data": {
                    "required": True,
                    "files": ["release/source_data/Fig3a.csv"],
                },
            }
        },
    )
    _write_manifest(project, data, figure_id)
    return data


def _is_ignored(project, relative):
    result = subprocess.run(
        ["git", "-C", str(project), "check-ignore", "--quiet", relative],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_figure_init_creates_intended_tree(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    figure = project / "manuscript" / "figures" / "figure3"
    assert (figure / "FIGURE.md").is_file()
    assert (figure / "manifest.yaml").is_file()
    for relative in FIGURE_LEAF_DIRS:
        assert (figure / relative).is_dir(), relative
    for relative in RELEASE_GITKEEP_DIRS:
        assert (figure / relative / ".gitkeep").is_file(), relative


def test_figure_init_does_not_create_placeholder_artifacts(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    figure = project / "manuscript" / "figures" / "figure3"
    artifacts = [
        path
        for path in figure.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]
    assert sorted(path.name for path in artifacts) == ["FIGURE.md", "manifest.yaml"]


def test_figure_init_duplicate_fails_safely(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    figure_md = project / "manuscript" / "figures" / "figure3" / "FIGURE.md"
    sentinel = figure_md.read_text(encoding="utf-8")

    assert main(["figure", "init", "figure3", "--path", str(project)]) == 1
    assert "already exists" in capsys.readouterr().err
    assert figure_md.read_text(encoding="utf-8") == sentinel


@pytest.mark.parametrize(
    "figure_id",
    ["../evil", "a/b", "a\\b", ".hidden", "..", "fig 3", ""],
)
def test_figure_init_rejects_unsafe_ids(project, figure_id):
    assert main(["figure", "init", figure_id, "--path", str(project)]) == 1
    assert not (project / "manuscript").exists()


def test_ordinary_init_does_not_create_manuscript(project):
    assert not (project / "manuscript").exists()


def test_figure_working_and_previews_ignored_release_tracked(git_project):
    assert main(["figure", "init", "figure3", "--path", str(git_project)]) == 0

    assert _is_ignored(git_project, "manuscript/figures/figure3/working/exploratory/p.py")
    assert _is_ignored(git_project, "manuscript/figures/figure3/working/validation/v.csv")
    assert _is_ignored(git_project, "manuscript/figures/figure3/previews/p.pdf")

    assert not _is_ignored(git_project, "manuscript/figures/figure3/FIGURE.md")
    assert not _is_ignored(git_project, "manuscript/figures/figure3/manifest.yaml")
    assert not _is_ignored(
        git_project, "manuscript/figures/figure3/release/main/with_legend/Fig3a.pdf"
    )
    assert not _is_ignored(
        git_project, "manuscript/figures/figure3/release/source_data/Fig3a.csv"
    )


def test_generated_manifest_parses(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    data = yaml.safe_load(
        (
            project / "manuscript" / "figures" / "figure3" / "manifest.yaml"
        ).read_text(encoding="utf-8")
    )
    assert data["schema_version"] == 1
    assert data["figure_id"] == "figure3"
    assert data["status"] == "working"
    assert data["style_file"] is None
    assert data["release"] == {"approved": False}
    assert data["panels"] == {}


def test_figure_md_distinguishes_message_and_release(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    text = (
        project / "manuscript" / "figures" / "figure3" / "FIGURE.md"
    ).read_text(encoding="utf-8")
    assert "# Figure figure3" in text
    assert "## Scientific message" in text
    assert "## Evidence basis" in text
    assert "Release requires explicit human approval." in text


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


def test_structural_validation_passes_for_fresh_figure(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_missing_figure_fails(project, capsys):
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "does not exist" in capsys.readouterr().out


def test_validate_mismatched_figure_id_fails(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(figure_id="figureX"))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "does not match directory name" in capsys.readouterr().out


@pytest.mark.parametrize("status", ["working", "validated", "released"])
def test_validate_accepts_valid_statuses(project, status):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(status=status))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_rejects_invalid_status(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(status="draft"))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "status 'draft'" in capsys.readouterr().out


@pytest.mark.parametrize("role", ["main", "supplementary"])
def test_validate_accepts_valid_panel_roles(project, role):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(panels={"A": {"role": role}}))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_rejects_invalid_panel_role(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(panels={"A": {"role": "sketch"}}))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "role 'sketch'" in capsys.readouterr().out


def test_validate_missing_evidence_experiment_fails(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project, _manifest(panels={"A": _main_panel(experiment="EXP999")})
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "EXP999" in capsys.readouterr().out


def test_validate_existing_evidence_experiment_passes(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _create_experiment(project, "EXP007")
    _write_manifest(
        project, _manifest(panels={"A": _main_panel(experiment="EXP007")})
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_rejects_path_traversal(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(panels={"A": _main_panel(outputs={"with_legend": "../../evil.pdf"})}),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "traversal" in capsys.readouterr().out


def test_validate_rejects_absolute_path(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(panels={"A": _main_panel(outputs={"with_legend": "/tmp/evil.pdf"})}),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "project-relative" in capsys.readouterr().out


def test_validate_rejects_release_output_in_working(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(panels={"A": _main_panel(outputs={"with_legend": "working/plot.pdf"})}),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "working/" in capsys.readouterr().out


def test_validate_rejects_release_output_in_previews(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(panels={"A": _main_panel(outputs={"with_legend": "previews/p.pdf"})}),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "previews/" in capsys.readouterr().out


def test_validate_rejects_source_data_in_working(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    source_data={
                        "required": True,
                        "files": ["working/validation/Fig3a.csv"],
                    }
                )
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "working/" in capsys.readouterr().out


def test_validate_rejects_duplicate_release_outputs(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(outputs={"with_legend": "release/main/x.pdf"}),
                "B": _main_panel(outputs={"with_legend": "release/main/x.pdf"}),
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "duplicates release output path" in capsys.readouterr().out


def test_validate_missing_style_file_fails(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(style_file="missing_style.py"))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "style_file does not exist" in capsys.readouterr().out


def test_validate_existing_style_file_passes(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_file(project / "style.py", "# project style\n")
    _write_manifest(project, _manifest(style_file="style.py"))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_null_style_file_passes(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(style_file=None))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_rejects_missing_figure_md(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    (project / "manuscript" / "figures" / "figure3" / "FIGURE.md").unlink()
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "missing FIGURE.md" in capsys.readouterr().out


def test_validate_rejects_unparseable_manifest(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    (
        project / "manuscript" / "figures" / "figure3" / "manifest.yaml"
    ).write_text("panels: [unclosed\n", encoding="utf-8")
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "invalid YAML" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Release validation
# ---------------------------------------------------------------------------


def test_release_validation_requires_approval(project, capsys):
    _make_release_ready(project)
    data = _manifest(
        figure_id="figure3",
        status="validated",
        release={"approved": False},
        panels={},
    )
    _write_manifest(project, data)

    # Ordinary structural validation still passes when approval is false.
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 1
    assert "release.approved must be true" in capsys.readouterr().out


def test_release_validation_requires_validated_status(project, capsys):
    _make_release_ready(project)
    data = _manifest(
        figure_id="figure3",
        status="working",
        release={"approved": True},
        panels={},
    )
    _write_manifest(project, data)
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 1
    assert "requires status 'validated'" in capsys.readouterr().out


def test_release_required_source_data_without_files_fails(project, capsys):
    _make_release_ready(project)
    data = _manifest(
        figure_id="figure3",
        status="validated",
        release={"approved": True},
        panels={
            "A": _main_panel(
                source_data={"required": True, "files": []},
            )
        },
    )
    _write_manifest(project, data)
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 1
    assert "declares no source-data files" in capsys.readouterr().out


def test_release_missing_required_source_data_fails(project, capsys):
    _make_release_ready(project)
    figure = project / "manuscript" / "figures" / "figure3"
    (figure / "release" / "source_data" / "Fig3a.csv").unlink()
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 1
    assert "required source data does not exist" in capsys.readouterr().out


def test_release_existing_required_source_data_passes(project):
    _make_release_ready(project)
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 0


def test_release_not_required_source_data_passes(project):
    _make_release_ready(project)
    data = _manifest(
        figure_id="figure3",
        status="validated",
        release={"approved": True},
        panels={
            "A": _main_panel(
                outputs={"with_legend": "release/main/with_legend/Fig3a.pdf"},
                source_data={"required": False, "files": []},
            )
        },
    )
    _write_manifest(project, data)
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 0


def test_release_missing_visual_output_fails(project, capsys):
    _make_release_ready(project)
    figure = project / "manuscript" / "figures" / "figure3"
    (figure / "release" / "main" / "with_legend" / "Fig3a.pdf").unlink()
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 1
    assert "declared release output does not exist" in capsys.readouterr().out


def test_complete_approved_validated_figure_passes(project):
    _make_release_ready(project)
    assert main(["figure", "validate", "figure3", "--release", "--path", str(project)]) == 0


# ---------------------------------------------------------------------------
# Compatibility and status
# ---------------------------------------------------------------------------


def test_ordinary_validate_ignores_figures(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    # A deliberately broken manifest does not affect ordinary validation.
    _write_manifest(project, _manifest(status="nonsense"))
    assert main(["validate", "--path", str(project)]) == 0


def test_old_style_project_without_figure_support_validates(project):
    # Simulate a v0.1.1 project: no manuscript/, guide, or figure skill.
    (project / "docs" / "guides" / "FIGURES.md").unlink()
    (project / ".agents" / "skills" / "scientific-figures" / "SKILL.md").unlink()
    (project / ".agents" / "skills" / "scientific-figures").rmdir()
    assert not (project / "manuscript").exists()
    assert main(["validate", "--path", str(project)]) == 0


def test_status_shows_figures_only_when_present(project, capsys):
    assert main(["status", "--path", str(project)]) == 0
    assert "Manuscript figures" not in capsys.readouterr().out

    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    assert main(["status", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "Manuscript figures" in out
    assert "figure3" in out
    assert "not approved" in out


# ---------------------------------------------------------------------------
# Manifest schema version
# ---------------------------------------------------------------------------


def test_validate_accepts_manifest_schema_version_one(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_rejects_wrong_manifest_schema_version(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(project, _manifest(schema_version=999))
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "schema_version must be 1" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Release boundary: a figure may certify only its own release/ tree
# ---------------------------------------------------------------------------


def test_validate_accepts_own_release_artifacts(project):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    experiment=None,
                    outputs={
                        "with_legend": "release/main/with_legend/Fig3a.pdf",
                        "without_legend_text": (
                            "manuscript/figures/figure3/release/main/"
                            "without_legend_text/Fig3a.pdf"
                        ),
                    },
                    source_data={
                        "required": True,
                        "files": [
                            "release/source_data/Fig3a.csv",
                            "manuscript/figures/figure3/release/source_data/Fig3b.csv",
                        ],
                    },
                )
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 0


def test_validate_rejects_output_in_other_figure_release(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    experiment=None,
                    outputs={
                        "with_legend": (
                            "manuscript/figures/figure4/release/main/with_legend/x.pdf"
                        )
                    },
                )
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "must resolve inside" in capsys.readouterr().out


def test_validate_rejects_output_in_unrelated_manuscript_dir(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    experiment=None,
                    outputs={
                        "with_legend": "manuscript/unrelated/release/main/x.pdf"
                    },
                )
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "must resolve inside" in capsys.readouterr().out


def test_validate_rejects_output_outside_release_dir(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    experiment=None,
                    outputs={"with_legend": "some-other-directory/x.pdf"},
                )
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "must resolve inside" in capsys.readouterr().out


def test_validate_rejects_source_data_in_other_figure(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    experiment=None,
                    source_data={
                        "required": True,
                        "files": [
                            "manuscript/figures/figure4/release/source_data/x.csv"
                        ],
                    },
                )
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "must resolve inside" in capsys.readouterr().out


def test_validate_rejects_source_data_outside_source_data_dir(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    experiment=None,
                    source_data={
                        "required": True,
                        "files": ["release/tables/Fig3a.csv"],
                    },
                )
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "release/source_data" in capsys.readouterr().out


def test_validate_detects_duplicate_resolved_release_paths(project, capsys):
    assert main(["figure", "init", "figure3", "--path", str(project)]) == 0
    _write_manifest(
        project,
        _manifest(
            panels={
                "A": _main_panel(
                    experiment=None,
                    outputs={"with_legend": "release/main/x.pdf"},
                ),
                "B": _main_panel(
                    experiment=None,
                    outputs={
                        "with_legend": (
                            "manuscript/figures/figure3/release/main/x.pdf"
                        )
                    },
                ),
            }
        ),
    )
    assert main(["figure", "validate", "figure3", "--path", str(project)]) == 1
    assert "duplicates release output path" in capsys.readouterr().out
