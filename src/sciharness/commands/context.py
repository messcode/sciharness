"""``sci context``: deterministic agent bootstrap and routing.

This command answers one question: *what should an agent read now?*  It never
interprets scientific content, summarizes conclusions, or inspects generated
artifacts.  It is deliberately distinct from ``sci status`` (which reports what
scientific objects exist) and ``sci show`` (which locates one record).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from ..project import (
    Record,
    config_path,
    find_project_root,
    id_number,
    load_config,
    load_records,
    relative_path,
)

RECENT_DECISIONS = 5
FIGURE_GUIDE = Path("docs") / "guides" / "FIGURES.md"


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    config = load_config(root)
    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    name = (project or {}).get("name") or root.name

    print("Project")
    print("  {}".format(name))

    print("\nRead first")
    for key in ("charter", "state"):
        print("  {}".format(relative_path(root, config_path(root, key))))

    questions, _ = load_records(root, "question")
    explorations, _ = load_records(root, "exploration")
    experiments, _ = load_records(root, "experiment")
    decisions, _ = load_records(root, "decision")

    _section("Active questions", [r for r in questions if r.status == "open"], root)
    _section(
        "Active explorations", [r for r in explorations if r.status == "active"], root
    )
    _section(
        "Active experiments",
        [r for r in experiments if r.status in ("planned", "running")],
        root,
    )
    recent = sorted(decisions, key=lambda record: id_number(record.id), reverse=True)
    _section("Recent decisions", recent[:RECENT_DECISIONS], root)

    guide = root / FIGURE_GUIDE
    if guide.is_file():
        print("\nConditional guidance")
        print("  manuscript figures → {}".format(relative_path(root, guide)))
    return 0


def _section(title: str, records: List[Record], root: Path) -> None:
    print("\n{}".format(title))
    if not records:
        print("  (none)")
        return
    for record in records:
        print("  {} → {}".format(record.id, relative_path(root, record.path)))
