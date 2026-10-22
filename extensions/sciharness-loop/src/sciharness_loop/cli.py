"""Explicit commands only: no daemon, background work, or autonomous run mode."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .controller import Controller
from .core import find_root
from .storage import LoopError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sci-loop")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "step", "status"):
        command = commands.add_parser(name)
        command.add_argument("--path", default=".")
        command.add_argument("--json", action="store_true")
        if name == "plan":
            command.add_argument("--task", required=True)
        elif name == "step":
            group = command.add_mutually_exclusive_group(required=True)
            group.add_argument("--plan", help="Execute one approved suggested plan")
            group.add_argument("--accept", help="Accept a completed exploration after review")
            group.add_argument("--recover", help="Stop and checkpoint an interrupted executor")
            command.add_argument("--review-hash")
            command.add_argument("--by", help="Identity of the human approving this exact action")
            command.add_argument("--retry-of", help="Explicitly retry the last failed execution")
        else:
            command.add_argument("run_id", nargs="?")
    args = parser.parse_args(argv)
    try:
        controller = Controller(find_root(Path(args.path)))
        if args.command == "plan":
            result = controller.plan(args.task)
        elif args.command == "status":
            result = controller.status(args.run_id)
        elif args.recover:
            if args.retry_of or args.by or args.review_hash:
                raise LoopError("--recover cannot be combined with approval or retry options")
            result = controller.recover(args.recover)
        elif args.accept:
            if args.retry_of:
                raise LoopError("--retry-of is only for execution")
            result = controller.accept(args.accept, args.review_hash, args.by)
        else:
            result = controller.step(args.plan, args.review_hash, args.by, args.retry_of)
        value = {"schema_version": 1, "ok": True, "command": args.command, "result": result}
        code = 0
    except (LoopError, OSError, ValueError, subprocess.SubprocessError) as exc:
        value = {"schema_version": 1, "ok": False, "command": args.command, "error": str(exc)}
        code = 1
    if args.json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    elif value["ok"]:
        print(json.dumps(value["result"], indent=2, ensure_ascii=False))
    else:
        print("sci-loop: " + value["error"], file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
