"""Read-only project Skills are bounded, copied, and review-bound inputs."""
import pytest

from conftest import set_policy
from sciharness_loop.controller import Controller
from sciharness_loop.policy import load_policy
from sciharness_loop.storage import LoopError, run_path


def write_skill(project, name="scientific-research"):
    folder = project / ".agents/skills" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\nname: " + name + "\ndescription: Fixture skill\n---\n"
        "Read the evidence before making claims.\n",
        encoding="utf-8")
    (folder / "references").mkdir(exist_ok=True)
    (folder / "references/notes.md").write_text("reference notes", encoding="utf-8")
    return folder


def test_skills_are_read_only_inputs_and_review_bound(project, executor):
    folder = write_skill(project)
    set_policy(project, skills=["scientific-research"])
    controller = Controller(project, executor)
    plan = controller.plan("Pilot")
    step = controller.step(plan["id"], plan["review_hash"], "Researcher")
    assert step["state"] == "pending_review"
    run_input = run_path(controller.base, step["id"]) / "input"
    assert (run_input / "project/.agents/skills/scientific-research/SKILL.md").is_file()
    assert (run_input / "project/.agents/skills/scientific-research/references/notes.md").is_file()
    assert "Read-only Agent Skills" in (run_input / "prompt.txt").read_text(encoding="utf-8")
    review = step["review_hash"]
    (folder / "SKILL.md").write_text("changed", encoding="utf-8")
    with pytest.raises(LoopError, match="inputs changed"):
        Controller(project, executor).accept(step["id"], review, "Researcher")


def test_skill_policy_validation_and_missing_skill(project):
    set_policy(project, skills=["../secret"])
    with pytest.raises(LoopError, match="skills"):
        load_policy(project)
    set_policy(project, skills=["absent-skill"])
    with pytest.raises(LoopError, match="skill must be"):
        Controller(project).snapshot()
    set_policy(project, skills=["a", "a"])
    with pytest.raises(LoopError, match="duplicate"):
        load_policy(project)


def test_skill_symlink_and_metadata_are_rejected(project):
    folder = write_skill(project)
    (folder / "linked").symlink_to(folder / "SKILL.md")
    set_policy(project, skills=["scientific-research"])
    with pytest.raises(LoopError, match="symlink"):
        Controller(project).snapshot()


def test_skill_budget_fails_closed(project):
    write_skill(project)
    set_policy(project, skills=["scientific-research"], read_files=[],
               max_input_bytes=10)
    with pytest.raises(LoopError, match="input budget"):
        Controller(project).snapshot()
