"""Explicit manual steps, approved bounded runs, and scheduled dispatch."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .controller import Controller
from .core import find_root
from .missions import MissionRunner
from .storage import LoopError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sci-loop")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "step", "status", "run"):
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
        elif name == "status":
            command.add_argument("run_id", nargs="?")
            group = command.add_mutually_exclusive_group()
            group.add_argument("--mission", help="Inspect one budgeted research run")
            group.add_argument("--missions", action="store_true", help="List budgeted runs")
        else:
            group = command.add_mutually_exclusive_group(required=True)
            group.add_argument("--spec", help="Prepare a run for review without executing")
            group.add_argument("--start", help="Approve and run/schedule a prepared mission")
            group.add_argument("--resume", help="Approve continuation of a paused/failed mission")
            group.add_argument("--pause", help="Request a pause without resetting its budget")
            group.add_argument("--recover", help="Stop orphaned actions and retain reservations")
            group.add_argument("--dispatch", action="store_true", help="Run due approved missions")
            command.add_argument("--review-hash")
            command.add_argument("--by")
    args = parser.parse_args(argv)
    try:
        root = find_root(Path(args.path))
        controller = Controller(root)
        if args.command == "run":
            runner = MissionRunner(root)
            if (args.start is None and args.resume is None
                    and (args.review_hash is not None or args.by is not None)):
                raise LoopError("approval options apply only to --start/--resume")
            if args.spec is not None:
                result = runner.prepare(args.spec)
            elif args.start is not None or args.resume is not None:
                resuming = args.resume is not None
                mission_id = args.resume if resuming else args.start
                result = runner.approve(mission_id, args.review_hash, args.by, resume=resuming)
            elif args.pause is not None:
                result = runner.pause(args.pause)
            elif args.recover is not None:
                result = runner.recover(args.recover)
            elif args.dispatch:
                result = runner.dispatch()
            else:
                raise LoopError("choose exactly one run action")
        elif args.command == "plan":
            result = controller.plan(args.task)
        elif args.command == "status":
            if args.run_id and (args.mission or args.missions):
                raise LoopError("choose execution status or mission status")
            result = (MissionRunner(root).status(args.mission) if args.mission or args.missions
                      else controller.status(args.run_id))
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
