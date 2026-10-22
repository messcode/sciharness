"""Standalone deadline supervisor without credentials or project imports.

Launched before docker start in its own session. Controller death does not
cancel the deadline. Machine shutdown suspends local workers; service-level
recovery is still required after a host restart.
"""
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path


def supervise(docker, container, deadline, ready, cancel, *, clock=time.time, wait=time.sleep):
    if not re.fullmatch(r"[0-9a-f]{64}", container) or not Path(docker).is_absolute():
        raise ValueError("invalid watchdog target")
    ready.write_text(json.dumps({"pid": os.getpid(), "deadline": deadline,
                                "container_id": container}), encoding="utf-8")
    command = [docker, "--host", "unix:///var/run/docker.sock"]
    while not cancel.exists():
        remaining = deadline - clock()
        if remaining <= 0:
            try:
                stopped = subprocess.run(command + ["rm", "--force", container],
                                         capture_output=True, timeout=5)
                if not stopped.returncode or b"No such container" in stopped.stderr:
                    return "deadline"
            except subprocess.TimeoutExpired:
                pass
            print(json.dumps({"event": "deadline_stop_pending"}), flush=True)
            wait(1)  # Keep trying if a temporarily unavailable daemon returns.
            continue
        try:
            exists = subprocess.run(command + ["inspect", container], capture_output=True,
                                    timeout=min(2, remaining))
        except subprocess.TimeoutExpired:
            continue
        if exists.returncode and b"No such" in exists.stderr:
            return "stopped"
        wait(min(1, remaining))
    return "cancelled"


def main():
    parser = argparse.ArgumentParser()
    for flag in ("docker", "container", "ready", "cancel"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    reason = supervise(args.docker, args.container, args.deadline,
                       Path(args.ready), Path(args.cancel))
    print(json.dumps({"stop_reason": reason}), flush=True)


if __name__ == "__main__":
    main()
