#!/usr/bin/env python3
"""A stdio MCP allowlist proxy for the SciHarness Loop.

DSH's MCP client exposes every tool an MCP server advertises.  The Loop policy
must be able to restrict that set, so each configured server is reached through
this proxy: it forwards JSON-RPC, filters ``tools/list`` responses to the
allowlist, rejects non-allowlisted ``tools/call`` requests, and starts the real
server with only the explicitly named credential variables.

The server command and its allowlist come from a JSON file written by
``dsh_runner.py`` under /tmp; credential values are read from this process's
environment and never written to that file or the policy.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path


def load_config(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("MCP proxy config must be an object")
    command = value.get("command")
    tools = value.get("tools")
    if (not isinstance(command, list) or not command
            or not all(isinstance(part, str) and part for part in command)):
        raise ValueError("MCP proxy command must be a non-empty string list")
    if (not isinstance(tools, list) or not tools
            or not all(isinstance(tool, str) and tool for tool in tools)):
        raise ValueError("MCP proxy tools must be a non-empty string list")
    env = value.get("env", [])
    if not isinstance(env, list) or not all(isinstance(name, str) for name in env):
        raise ValueError("MCP proxy env must be a list of names")
    return command, tools, env


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: mcp_proxy.py CONFIG.json", file=sys.stderr)
        return 2
    try:
        command, tools, env_names = load_config(argv[0])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("mcp-proxy: " + str(exc), file=sys.stderr)
        return 2
    allowed = set(tools)
    environment = {"PATH": os.environ.get("PATH", ""),
                   "HOME": os.environ.get("HOME", "/tmp")}
    for name in env_names:
        if name in os.environ:
            environment[name] = os.environ[name]

    try:
        server = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=sys.stderr, text=True, encoding="utf-8", env=environment,
            bufsize=1,
        )
    except OSError as exc:
        print("mcp-proxy: cannot start server: " + str(exc), file=sys.stderr)
        return 1
    assert server.stdin is not None and server.stdout is not None

    def client_to_server():
        try:
            for line in sys.stdin:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    server.stdin.write(line)
                    server.stdin.flush()
                    continue
                if isinstance(message, dict) and message.get("method") == "tools/call":
                    params = message.get("params")
                    name = params.get("name") if isinstance(params, dict) else None
                    if name not in allowed:
                        response = {
                            "jsonrpc": "2.0", "id": message.get("id"),
                            "error": {"code": -32601,
                                      "message": "MCP tool not allowlisted: " + str(name)},
                        }
                        sys.stdout.write(json.dumps(response) + "\n")
                        sys.stdout.flush()
                        continue
                server.stdin.write(line)
                server.stdin.flush()
        finally:
            try:
                server.stdin.close()
            except OSError:
                pass

    def server_to_client():
        for line in server.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                sys.stdout.write(line)
                sys.stdout.flush()
                continue
            if (isinstance(message, dict) and isinstance(message.get("result"), dict)
                    and isinstance(message["result"].get("tools"), list)):
                message["result"]["tools"] = [
                    tool for tool in message["result"]["tools"]
                    if isinstance(tool, dict) and tool.get("name") in allowed
                ]
            sys.stdout.write(json.dumps(message) + "\n")
            sys.stdout.flush()

    client = threading.Thread(target=client_to_server, daemon=True)
    serving = threading.Thread(target=server_to_client, daemon=True)
    client.start()
    serving.start()
    serving.join()
    try:
        return server.wait()
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()


if __name__ == "__main__":
    raise SystemExit(main())
