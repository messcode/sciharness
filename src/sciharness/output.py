"""Stable machine-readable output, diagnostics, and exit codes.

Human output remains the default.  ``--json`` emits one object per command with
a ``schema_version``, an ``ok`` flag, and a ``diagnostics`` list.  Error paths
also emit JSON when ``--json`` was requested, so an agent never has to parse
prose to discover what went wrong.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_USAGE = 2
EXIT_PROJECT = 3


@dataclass
class Diagnostic:
    """One structural problem, warning, or informational finding."""

    code: str
    severity: str
    message: str
    path: Optional[str] = None
    field: Optional[str] = None
    hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.path is not None:
            data["path"] = self.path
        if self.field is not None:
            data["field"] = self.field
        if self.hint is not None:
            data["hint"] = self.hint
        return data

    @classmethod
    def from_problem(
        cls, problem: str, severity: str = "error"
    ) -> "Diagnostic":
        path, message = _split_location(str(problem))
        return cls(
            code=_classify(message),
            severity=severity,
            message=message,
            path=path,
        )


def _split_location(problem: str) -> tuple:
    """Split ``path: message`` when the prefix looks like a project path."""
    prefix, separator, rest = problem.partition(": ")
    if not separator:
        return None, problem
    if (
        "/" in prefix
        or prefix.endswith((".md", ".yaml", ".yml", ".py", ".json"))
        or prefix == ".sci.yaml"
    ):
        return prefix, rest
    return None, problem


def _classify(message: str) -> str:
    lowered = message.lower()
    if "duplicate" in lowered:
        return "DUPLICATE"
    if (
        "not found" in lowered
        or "does not exist" in lowered
        or "missing" in lowered
    ):
        return "NOT_FOUND"
    if (
        "traversal" in lowered
        or "escapes the project" in lowered
        or "project-relative" in lowered
    ):
        return "UNSAFE_PATH"
    if (
        "must be" in lowered
        or "must contain" in lowered
        or "must declare" in lowered
        or "invalid" in lowered
        or "requires" in lowered
    ):
        return "INVALID"
    return "VALIDATION"


def diagnostics_from_problems(
    problems: Iterable[str], severity: str = "error"
) -> List[Diagnostic]:
    return [Diagnostic.from_problem(problem, severity) for problem in problems]


def project_info(root: Any, name: Optional[str] = None) -> Dict[str, Any]:
    info: Dict[str, Any] = {"root": str(root)}
    if name:
        info["name"] = name
    return info


def envelope(
    command: str,
    *,
    project: Optional[Dict[str, Any]] = None,
    ok: bool = True,
    diagnostics: Iterable[Diagnostic] = (),
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "ok": bool(ok),
    }
    if project is not None:
        payload["project"] = project
    if data:
        payload.update(data)
    payload["diagnostics"] = [
        diagnostic.to_dict() for diagnostic in diagnostics
    ]
    return payload


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))


def error_envelope(command: str, message: str) -> Dict[str, Any]:
    return envelope(
        command,
        ok=False,
        diagnostics=[
            Diagnostic(
                code="PROJECT_ERROR",
                severity="error",
                message=message,
            )
        ],
    )
