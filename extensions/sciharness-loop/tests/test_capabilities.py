"""Policy-gated agent capabilities: default bounded, explicit opt-in."""
import pytest

from conftest import set_policy
from sciharness_loop.adapters import CodexAdapter, DshAdapter
from sciharness_loop.dsh_runner import patch_text
from sciharness_loop.policy import Policy, load_policy
from sciharness_loop.storage import LoopError


def test_capabilities_default_to_bounded(project):
    policy = load_policy(project)
    assert policy.capabilities["dsh"]["tools"] == []
    assert policy.capabilities["dsh"]["session"] == "action"
    assert policy.capabilities["codex"]["agents_md"] is False
    assert policy.capabilities["codex"]["skills"] is False


def test_capabilities_are_fingerprinted(project):
    set_policy(project, capabilities={
        "dsh": {"tools": ["subagents", "web"]},
        "codex": {"agents_md": True, "skills": True},
    })
    first = load_policy(project)
    set_policy(project, capabilities={
        "dsh": {"tools": ["subagents"]},
        "codex": {"agents_md": True, "skills": True},
    })
    assert first.fingerprint != load_policy(project).fingerprint


@pytest.mark.parametrize("capabilities, message", [
    ({"dsh": {"tools": ["unknown"]}}, "allowlist"),
    ({"dsh": {"session": "mission"}}, "action-scoped"),
    ({"codex": {"agents_md": "yes"}}, "codex"),
    ({"other": {}}, "dsh and codex"),
])
def test_capability_policy_fails_closed(project, capabilities, message):
    set_policy(project, capabilities=capabilities)
    with pytest.raises(LoopError, match=message):
        load_policy(project)


def test_dsh_capability_enables_only_selected_tool_groups():
    policy = Policy(backend="dsh", model="fixture",
                    capabilities={"dsh": {"tools": ["subagents", "web"]},
                                  "codex": {"agents_md": False, "skills": False}})
    invocation = DshAdapter().invocation(policy)
    assert invocation.args[invocation.args.index("--allow-tools") + 1] == "subagents,web"
    patch = patch_text("fixture", allow_tools={"subagents", "web"})
    assert "- id: tool-subagent" not in patch
    assert "- id: tool-web" not in patch
    assert "- id: tool-jobs" in patch and "disabled: true" in patch
    assert "- id: tool-workflow" in patch and "- id: tool-goal" in patch


def test_codex_capability_stages_project_instructions_and_skills():
    policy = Policy(capabilities={"dsh": {"tools": []},
                                  "codex": {"agents_md": True, "skills": True}})
    invocation = CodexAdapter().invocation(policy)
    assert invocation.entrypoint == "python3"
    assert invocation.args[0].endswith("codex_runner.py")
    assert "--agents-md" in invocation.args and "--skills" in invocation.args
    assert "--" in invocation.args
    assert "--output-schema" in invocation.args and "/work/result.json" in invocation.args
    assert invocation.credentials == ("CODEX_API_KEY",)


def test_codex_default_does_not_stage_project_instructions():
    invocation = CodexAdapter().invocation(Policy())
    assert "--agents-md" not in invocation.args
    assert "--skills" not in invocation.args
    assert invocation.entrypoint == "python3"
