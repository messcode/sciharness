#!/usr/bin/env python3
"""Codex launcher that optionally stages project AGENTS.md and Skills.

Codex reads AGENTS.md and its skill discovery from CODEX_HOME.  The Loop keeps
the project read-only at /input/project and runs Codex in /work, so the opt-in
capability copies only those reviewed files into CODEX_HOME before exec'ing
Codex.  Nothing is written into /work, preserving the plan artifact contract.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    agents_md = skills = False
    while args:
        if args[0] == "--agents-md":
            agents_md = True
            args = args[1:]
        elif args[0] == "--skills":
            skills = True
            args = args[1:]
        elif args[0] == "--":
            args = args[1:]
            break
        else:
            break
    project = Path("/input/project")
    home = Path(os.environ.get("CODEX_HOME", "/tmp/codex"))
    home.mkdir(parents=True, exist_ok=True)
    if agents_md and (project / "AGENTS.md").is_file():
        shutil.copy2(project / "AGENTS.md", home / "AGENTS.md")
    if skills and (project / ".agents/skills").is_dir():
        target = home / "skills"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(project / ".agents/skills", target)
    os.execvp("codex", ["codex"] + args)


if __name__ == "__main__":
    raise SystemExit(main())
