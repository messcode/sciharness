"""Small DeepSeek tool harness, run ONLY inside an enforcing runtime.

Uses the documented Chat Completions tool-call protocol and Python's standard
library. It is not a host executor. Docker supplies the filesystem and process
boundary. Requests, tool results, and final artifacts are independently bounded.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # Never forward an API credential to a redirect target.


def validate(value, schema):
    if not isinstance(value, dict) or set(value) != set(schema["required"]):
        raise ValueError("final result does not match required fields")
    types = {"string": str, "boolean": bool, "array": list}
    for key, rule in schema["properties"].items():
        item = value[key]
        if type(item) is not types[rule["type"]]:
            raise ValueError("wrong final result type: " + key)
        if isinstance(item, str) and not item.strip():
            raise ValueError("empty final result field: " + key)
        if isinstance(item, list) and not all(isinstance(x, str) and x.strip() for x in item):
            raise ValueError("invalid final result list: " + key)
        if "enum" in rule and item not in rule["enum"]:
            raise ValueError("invalid final result choice: " + key)


def tool(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False}}}


class Runner:
    def __init__(self, model, base_url, key, *, input_root=Path("/input"),
                 work=Path("/work"), data=Path("/datasets"), max_turns=24,
                 context_bytes=1_000_000, completion_tokens=4096):
        self.model, self.url, self.key = model, base_url.rstrip("/") + "/chat/completions", key
        self.input, self.work, self.data = Path(input_root), Path(work), Path(data)
        self.max_turns, self.context_bytes = max_turns, context_bytes
        self.completion_tokens = completion_tokens
        self.opener = urllib.request.build_opener(NoRedirect)

    def path(self, name, write=False):
        path = Path(name)
        if not path.is_absolute():
            path = self.work / path
        roots = [self.work] if write else [self.input, self.work, self.data]
        for root in roots:
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if ".." in relative.parts:
                raise ValueError("path traversal is forbidden")
            current = root
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError("symlinks are forbidden")
            return current
        raise ValueError("path is outside the authorized workspace")

    def call_tool(self, name, arguments):
        if name == "read_file":
            path = self.path(arguments["path"])
            with path.open("rb") as stream:
                raw = stream.read(32001)
            return {"text": raw[:32000].decode("utf-8", errors="replace"),
                    "truncated": len(raw) > 32000}
        if name == "write_file":
            path = self.path(arguments["path"], write=True)
            content = arguments["content"]
            if not isinstance(content, str) or len(content.encode()) > self.context_bytes:
                raise ValueError("invalid or oversized file content")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"written": str(path)}
        if name == "shell":
            timeout = arguments["timeout_seconds"]
            if type(timeout) is not int or not 1 <= timeout <= 60:
                raise ValueError("shell timeout must be an integer in [1, 60]")
            result = subprocess.run(["/bin/sh", "-c", arguments["command"]], cwd=self.work,
                                    capture_output=True, timeout=timeout)
            return {"exit_code": result.returncode,
                    "stdout": result.stdout[:16000].decode(errors="replace"),
                    "stderr": result.stderr[:16000].decode(errors="replace"),
                    "truncated": len(result.stdout) > 16000 or len(result.stderr) > 16000}
        raise ValueError("unknown tool: " + name)

    def request(self, messages, tools):
        body = json.dumps({"model": self.model, "messages": messages, "tools": tools,
                           "thinking": {"type": "disabled"}, "stream": False,
                           "max_tokens": self.completion_tokens}).encode()
        if len(body) > self.context_bytes:
            raise ValueError("harness context budget exhausted; start a new bounded cycle")
        request = urllib.request.Request(self.url, body, headers={
            "Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(self.context_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise ValueError("DeepSeek HTTP error {}".format(exc.code)) from exc
        if len(raw) > self.context_bytes:
            raise ValueError("oversized model response")
        result = json.loads(raw)
        choice = result["choices"][0]
        if choice.get("finish_reason") not in ("stop", "tool_calls"):
            raise ValueError("model response was incomplete: " + str(choice.get("finish_reason")))
        print(json.dumps({"type": "model_response", "model": result.get("model", self.model),
                          "usage": result.get("usage"), "finish_reason": choice.get("finish_reason")}),
              flush=True)
        return choice["message"]

    def run(self, prompt):
        schema = json.loads((self.input / "schema.json").read_text(encoding="utf-8"))
        tools = [
            tool("read_file", "Read a selected input or workspace text file (32 KB maximum).",
                 {"path": {"type": "string"}}, ["path"]),
            tool("write_file", "Write a file inside the output workspace.",
                 {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
            tool("shell", "Run a bounded shell command inside the isolated container.",
                 {"command": {"type": "string"}, "timeout_seconds": {"type": "integer"}},
                 ["command", "timeout_seconds"]),
            {"type": "function", "function": {"name": "finish",
             "description": "Return the final structured result after saving evidence.", "parameters": schema}},
        ]
        messages = [{"role": "system", "content": (
            "Use the provided tools inside the isolated workspace. Read the selected inputs. "
            "Save exact scripts, commands, failures, and evidence as requested. "
            "Conclude with the finish tool or a JSON object matching this schema: " + json.dumps(schema))},
                    {"role": "user", "content": prompt}]
        for _ in range(self.max_turns):
            message = self.request(messages, tools)
            calls = message.get("tool_calls") or []
            if not calls:
                value = json.loads(message.get("content") or "")
                return self.finish(value, schema)
            messages.append({k: message[k] for k in ("role", "content", "tool_calls", "reasoning_content")
                             if k in message})
            for call in calls:
                name = call["function"]["name"]
                arguments = json.loads(call["function"]["arguments"])
                if name == "finish":
                    if len(calls) != 1:
                        raise ValueError("finish must be the only tool call in its turn")
                    return self.finish(arguments, schema)
                try:
                    output = self.call_tool(name, arguments)
                except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                    output = {"error": str(exc)}
                print(json.dumps({"type": "tool_result", "name": name,
                                  "arguments": arguments, "result": output}), flush=True)
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(output)})
        raise ValueError("harness turn budget exhausted")

    def finish(self, value, schema):
        validate(value, schema)
        target = self.path(str(self.work / "result.json"), write=True)
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"type": "completed", "result": value}), flush=True)
        return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--context-bytes", type=int, default=1_000_000)
    parser.add_argument("--completion-tokens", type=int, default=4096)
    args = parser.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY is required")
    runner = Runner(args.model, args.base_url, key, max_turns=args.max_turns,
                    context_bytes=args.context_bytes, completion_tokens=args.completion_tokens)
    runner.run(sys.stdin.read())


if __name__ == "__main__":
    main()
