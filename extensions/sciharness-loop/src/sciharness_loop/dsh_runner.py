#!/usr/bin/env python3
"""Run one DSH headless task and adapt it to the SciHarness Loop contract.

DSH is not a plain command runner: it boots a profile made of plugin bundles.
This wrapper uses the shipped ``headless`` one-shot bundle, keeps the model and
credentials in DSH's own config/environment, pins the non-interactive permission
mode, limits the exposed tool surface to one bounded action, and turns the
headless NDJSON contract into ``/work/result.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# These DSH tools exceed the Loop's "one bounded exploratory action" contract:
# they can spawn other agents, orchestrate workflows, run background jobs, or
# browse the web.  The file, shell, skill, todo, and working-directory tools stay
# available.  The Docker container remains the actual isolation boundary.
DISABLED_TOOLS = (
    "tool-jobs",
    "tool-subagent-control",
    "tool-subagent-list-agents",
    "tool-subagent",
    "tool-subagent-fork",
    "tool-workflow",
    "tool-goal",
    "tool-web",
)


def contract_note(input_dir, work_dir):
    return (
        "\n\n## Harness result contract (SciHarness Loop)\n"
        "The JSON Schema for the required result is at "
        + input_dir + "/schema.json. Read it before writing the result.\n"
        "Write the final JSON object to " + work_dir + "/result.json "
        "(UTF-8, no markdown fences). Your final answer must be the same JSON object.\n"
        "For a plan action, write no other file. For a step action, also write "
        + work_dir + "/proposal.md and put scripts, commands, logs, and outputs under "
        + work_dir + "/artifacts/ as instructed.\n"
        "Do not write outside the provided work directory. Do not ask the user "
        "questions; this is a non-interactive run.\n"
    )


def patch_text(model):
    rows = []
    if model:
        rows.extend([
            "- id: agent-default-model",
            "  config:",
            "    provider: deepseek-official",
            "    model: " + json.dumps(model),
        ])
    for name in DISABLED_TOOLS:
        rows.extend(["- id: " + name, "  disabled: true"])
    return "\n".join(rows) + "\n"


def parse_final(text):
    value = (text or "").strip()
    if not value:
        raise ValueError("DSH produced no final answer")
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("DSH final answer is not a JSON object")
        parsed = json.loads(value[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("DSH final answer is not a JSON object")
    return parsed


def read_result(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def run(args):
    input_dir = Path(os.environ.get("SCI_LOOP_INPUT", "/input"))
    work_dir = Path(os.environ.get("SCI_LOOP_WORK", "/work"))
    work_dir.mkdir(parents=True, exist_ok=True)
    patch = Path("/tmp/dsh-sci-loop-patch.yml")
    patch.write_text(patch_text(args.model), encoding="utf-8")

    # The runtime mounts the container root read-only and provides only /tmp as
    # writable scratch.  DSH needs a writable home for sessions/storages, so copy
    # the image-baked profile into /tmp once per container.  A custom image may
    # set its own writable DSH_HOME; the image-baked /opt/dsh-home is never used
    # directly at runtime because it is on the read-only root filesystem.
    environment = dict(os.environ)
    configured_home = environment.get("DSH_HOME")
    target_home = (Path(configured_home) if configured_home
                   and configured_home != "/opt/dsh-home" else Path("/tmp/dsh-home"))
    source_home = Path("/opt/dsh-home")
    if not target_home.exists():
        if source_home.is_dir():
            shutil.copytree(source_home, target_home)
        else:
            target_home.mkdir(parents=True, exist_ok=True)
    environment["DSH_HOME"] = str(target_home)
    # Headless has no interactive approver.  The Docker container is the
    # boundary, so use DSH's documented non-interactive permission mode rather
    # than letting tool calls block on an approval prompt that nobody can answer.
    environment.setdefault("DSH_PERMISSION_MODE", "danger-full-access")
    if args.base_url:
        environment["DEEPSEEK_BASE_URL"] = args.base_url

    prompt = sys.stdin.read()
    if not prompt.strip():
        raise ValueError("empty task prompt")
    prompt += contract_note(str(input_dir), str(work_dir))

    command = [
        os.environ.get("DSH_BIN", "dsh"),
        "--profile", "headless",
        "--patch", str(patch),
        "--json", "-",
    ]
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            env=environment,
        )
    except OSError as exc:
        raise RuntimeError("cannot start dsh: " + str(exc)) from exc

    final, error = None, None
    assert process.stdin is not None and process.stdout is not None
    try:
        process.stdin.write(prompt)
        process.stdin.close()
        for line in process.stdout:
            # Stream the headless event/diagnostic line into the executor log as
            # it arrives; a long DSH run must leave visible progress.
            sys.stdout.write(line)
            sys.stdout.flush()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "session":
                print("dsh session: " + str(event.get("sessionId", "")), file=sys.stderr)
            elif event.get("type") == "final":
                final = event.get("text", "")
            elif event.get("type") == "error":
                error = event.get("message") or "DSH emitted an error event"
        code = process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    if error:
        raise RuntimeError(error)
    if code != 0:
        raise RuntimeError("dsh exited with status {}".format(code))

    result_path = work_dir / "result.json"
    result = read_result(result_path)
    if result is None:
        result = parse_final(final)
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="",
                        help="DSH model id; omitted uses the profile default")
    parser.add_argument("--base-url", default="",
                        help="DSH Messages API root (DEEPSEEK_BASE_URL)")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print("dsh: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
