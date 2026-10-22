#!/usr/bin/env python3
"""A tiny MCP stdio server used by proxy and real-DSH allowlist tests."""
import json
import os
import sys

TOOLS = [
    {"name": "lookup", "description": "Allowed lookup",
     "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}},
    {"name": "secret", "description": "Must be filtered",
     "inputSchema": {"type": "object", "properties": {}}},
]


def reply(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        continue
    if not isinstance(request, dict):
        continue
    method, request_id = request.get("method"), request.get("id")
    if method == "initialize":
        reply({"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": (request.get("params") or {}).get("protocolVersion", "2026-07-28"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sciharness-fixture", "version": "1.0"},
        }})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        reply({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = request.get("params") or {}
        if params.get("name") == "lookup":
            reply({"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text",
                             "text": "allowed:" + str((params.get("arguments") or {}).get("q", ""))
                                     + ":token=" + str(os.environ.get("MCP_TOKEN", ""))}],
            }})
        else:
            reply({"jsonrpc": "2.0", "id": request_id, "error": {
                "code": -32601, "message": "unknown tool"}})
    elif method == "ping":
        reply({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif request_id is not None:
        reply({"jsonrpc": "2.0", "id": request_id, "error": {
            "code": -32601, "message": "method not found"}})
