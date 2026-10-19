"""``sci start``: begin a planned experiment and freeze pre-registration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..output import EXIT_OK, emit, envelope, project_info
from ..preregistration import start_experiment
from ..project import find_project_root


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    result = start_experiment(root, args.record_id)
    if getattr(args, "json", False):
        emit(
            envelope(
                "start",
                project=project_info(root),
                data={
                    "record": result["record"],
                    "record_path": result["record_path"],
                    "run": result["run"],
                    "preregistration_sha256": result[
                        "preregistration_sha256"
                    ],
                },
            )
        )
        return EXIT_OK

    print("Started experiment {}".format(result["record"]))
    print("  preregistration: {}".format(result["preregistration_sha256"]))
    print("  run: {}".format(result["run"]))
    print("  next: fill run.yaml and Results/Interpretation after running")
    return EXIT_OK
