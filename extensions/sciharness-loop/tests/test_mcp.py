"""Default-off MCP allowlist: policy, filtering proxy, and DSH invocation."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import set_policy
from sciharness_loop.adapters import DshAdapter
from sciharness_loop.policy import Policy, load_policy
from sciharness_loop.storage import LoopError

FIXTURES = Path(__file__).parent / "fixtures"
PROXY = Path(__file__).parents[1] / "src/sciharness_loop/mcp_proxy.py"


def mcp_policy(*, tools=("lookup",), env=("MCP_TOKEN",)):
    return {"servers": [{
        "name": "fixture",
        "command": [sys.executable, str(FIXTURES / "mcp_fixture_server.py")],
        "tools": list(tools),
        "env": list(env),
        "timeout_seconds": 5,
    }]}


def test_mcp_is_default_off_and_allowlist_is_fingerprinted(project):
    assert load_policy(project).mcp is None
    set_policy(project, mcp=mcp_policy())
    first = load_policy(project)
    assert first.mcp["servers"][0]["tools"] == ["lookup"]
    set_policy(project, mcp=mcp_policy(tools=("lookup", "other")))
    second = load_policy(project)
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize("mcp, message", [
    ({"servers": [{"name": "fixture", "command": ["/bin/x"], "tools": []}]}, "allowlist"),
    ({"servers": [{"name": "bad name", "command": ["/bin/x"], "tools": ["lookup"]}]}, "name"),
    ({"servers": [{"name": "fixture", "command": [], "tools": ["lookup"]}]}, "command"),
    ({"servers": [{"name": "fixture", "command": ["/bin/x"], "tools": ["lookup"],
                    "env": ["bad-name"]}]}, "env"),
    ({"servers": [{"name": "fixture", "command": ["/bin/x"], "tools": ["lookup"],
                    "timeout_seconds": 0}]}, "timeout"),
])
def test_mcp_policy_rejects_unsafe_configuration(project, mcp, message):
    set_policy(project, mcp=mcp)
    with pytest.raises(LoopError, match=message):
        load_policy(project)


def test_mcp_adapter_passes_allowlist_and_credentials():
    policy = Policy(backend="dsh", model="fixture-model", mcp=mcp_policy())
    invocation = DshAdapter().invocation(policy)
    assert "--mcp-json" in invocation.args
    payload = json.loads(invocation.args[invocation.args.index("--mcp-json") + 1])
    assert payload["servers"][0]["tools"] == ["lookup"]
    assert "DEEPSEEK_API_KEY" in invocation.credentials
    assert "MCP_TOKEN" in invocation.credentials


def test_mcp_proxy_filters_tools_and_blocks_calls(tmp_path):
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({
        "command": [sys.executable, str(FIXTURES / "mcp_fixture_server.py")],
        "env": ["MCP_TOKEN"], "tools": ["lookup"], "timeout_seconds": 5,
    }), encoding="utf-8")
    env = {**os.environ, "MCP_TOKEN": "fixture-token"}
    proxy = subprocess.Popen([sys.executable, str(PROXY), str(config)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
    assert proxy.stdin is not None and proxy.stdout is not None

    def send(message):
        proxy.stdin.write(json.dumps(message) + "\n")
        proxy.stdin.flush()

    def receive():
        line = proxy.stdout.readline()
        assert line, proxy.stderr.read() if proxy.stderr else ""
        return json.loads(line)

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2026-07-28", "capabilities": {},
                         "clientInfo": {"name": "test", "version": "1"}}})
        assert receive()["id"] == 1
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert [tool["name"] for tool in receive()["result"]["tools"]] == ["lookup"]
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "lookup", "arguments": {"q": "x"}}})
        result = receive()
        assert "allowed:x:token=fixture-token" in result["result"]["content"][0]["text"]
        send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
              "params": {"name": "secret", "arguments": {}}})
        blocked = receive()
        assert blocked["id"] == 4 and "not allowlisted" in blocked["error"]["message"]
    finally:
        proxy.stdin.close()
        proxy.terminate()
        proxy.wait(timeout=5)
