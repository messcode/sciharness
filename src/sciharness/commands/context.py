"""``sci context``: deterministic agent bootstrap and routing.

This command answers one question: *what should an agent read now?*  It never
interprets scientific content, summarizes conclusions, or inspects generated
artifacts.  It is deliberately distinct from ``sci status`` (which reports what
scientific objects exist) and ``sci show`` (which locates one record).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from ..output import (
    EXIT_OK,
    EXIT_VALIDATION,
    Diagnostic,
    diagnostics_from_problems,
    emit,
    envelope,
    project_info,
)
from ..project import (
    ProjectError,
    Record,
    config_path,
    find_project_root,
    id_number,
    load_config,
    load_records,
    relative_path,
)
from .validate import validate_project

RECENT_DECISIONS = 5
FIGURE_GUIDE = Path("docs") / "guides" / "FIGURES.md"
_UPDATED_RE = re.compile(r"^Updated:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    config = load_config(root)
    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    name = (project or {}).get("name") or root.name

    questions, _ = load_records(root, "question")
    explorations, _ = load_records(root, "exploration")
    experiments, _ = load_records(root, "experiment")
    decisions, _ = load_records(root, "decision")

    active_questions = [r for r in questions if r.status == "open"]
    active_explorations = [r for r in explorations if r.status == "active"]
    active_experiments = [
        r for r in experiments if r.status in ("planned", "running")
    ]
    recent = sorted(
        decisions, key=lambda record: id_number(record.id), reverse=True
    )[:RECENT_DECISIONS]

    read_first = [
        relative_path(root, config_path(root, key)) for key in ("charter", "state")
    ]
    guidance: List[Dict[str, str]] = []
    guide = root / FIGURE_GUIDE
    if guide.is_file():
        guidance.append(
            {
                "name": "manuscript figures",
                "path": relative_path(root, guide),
            }
        )

    diagnostics = diagnostics_from_problems(validate_project(root))
    diagnostics.extend(
        _state_diagnostics(
            root,
            config,
            questions + explorations + experiments + decisions,
        )
    )
    diagnostics.sort(
        key=lambda item: (
            {"error": 0, "warning": 1, "info": 2}.get(item.severity, 3),
            item.code,
        )
    )
    ok = not any(item.severity == "error" for item in diagnostics)

    if getattr(args, "json", False):
        emit(
            envelope(
                "context",
                project=project_info(root, name),
                ok=ok,
                diagnostics=diagnostics,
                data={
                    "read_first": read_first,
                    "active": {
                        "questions": [
                            _record_data(root, r) for r in active_questions
                        ],
                        "explorations": [
                            _record_data(root, r) for r in active_explorations
                        ],
                        "experiments": [
                            _record_data(root, r) for r in active_experiments
                        ],
                    },
                    "recent_decisions": [
                        _record_data(root, r) for r in recent
                    ],
                    "guidance": guidance,
                },
            )
        )
        return EXIT_OK if ok else EXIT_VALIDATION

    print("Project")
    print("  {}".format(name))

    print("\nRead first")
    for relative in read_first:
        print("  {}".format(relative))

    _section("Active questions", active_questions, root)
    _section("Active explorations", active_explorations, root)
    _section("Active experiments", active_experiments, root)
    _section("Recent decisions", recent, root)

    if guidance:
        print("\nConditional guidance")
        for item in guidance:
            print("  {} → {}".format(item["name"], item["path"]))

    print("\nDiagnostics")
    if not diagnostics:
        print("  no problems")
    else:
        for diagnostic in diagnostics:
            print(
                "  [{:<7}] {}: {}".format(
                    diagnostic.severity,
                    diagnostic.code,
                    _describe(diagnostic),
                )
            )
    return EXIT_OK if ok else EXIT_VALIDATION


def _record_data(root: Path, record: Record) -> Dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "created": record.created,
        "path": relative_path(root, record.path),
    }


def _describe(diagnostic: Diagnostic) -> str:
    if diagnostic.path and not diagnostic.message.startswith(diagnostic.path):
        return "{}: {}".format(diagnostic.path, diagnostic.message)
    return diagnostic.message


def _state_diagnostics(
    root: Path, config: Dict[str, Any], records: List[Record]
) -> List[Diagnostic]:
    """Warn when STATE.md predates the newest record."""
    try:
        state_path = config_path(root, "state")
    except ProjectError:
        return []
    if not state_path.is_file():
        return []
    text = state_path.read_text(encoding="utf-8")
    match = _UPDATED_RE.search(text)
    dates = [
        record.created
        for record in records
        if record.created and re.match(r"^\d{4}-\d{2}-\d{2}$", record.created)
    ]
    if not dates:
        return []
    newest = max(dates)
    if match is None:
        return [
            Diagnostic(
                code="STATE_DATE_MISSING",
                severity="warning",
                message="STATE.md has no 'Updated: YYYY-MM-DD' line",
                path=relative_path(root, state_path),
                hint="add an Updated date so agents can detect staleness",
            )
        ]
    if match.group(1) < newest:
        return [
            Diagnostic(
                code="STATE_STALE",
                severity="warning",
                message=(
                    "STATE.md is dated {}, older than the newest record ({})"
                    .format(match.group(1), newest)
                ),
                path=relative_path(root, state_path),
                hint="update docs/STATE.md to reflect current understanding",
            )
        ]
    return []


def _section(title: str, records: List[Record], root: Path) -> None:
    print("\n{}".format(title))
    if not records:
        print("  (none)")
        return
    for record in records:
        print("  {} → {}".format(record.id, relative_path(root, record.path)))
