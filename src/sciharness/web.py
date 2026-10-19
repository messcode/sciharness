"""Read-only local web viewer for decision chains and provenance."""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import yaml

from . import __version__
from .datasets import load_registry
from .figures import FIGURES_DIR, list_figures
from .output import diagnostics_from_problems
from .project import (
    KINDS,
    RELATIONS,
    ProjectError,
    config_path,
    id_number,
    load_config,
    load_records,
    relative_path,
)

WEB_DIR = Path(__file__).resolve().parent / "resources" / "web"
INDEX_HTML = WEB_DIR / "index.html"

_KIND_ORDER = {
    "question": 0,
    "exploration": 1,
    "experiment": 2,
    "decision": 3,
    "figure": 4,
    "dataset": 5,
}

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_UPDATED_RE = re.compile(r"^Updated:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_PREFERRED_SECTIONS = {
    "decision": ("Rationale", "Decision", "Evidence"),
    "experiment": ("Results", "Interpretation", "Primary estimand", "Design"),
    "exploration": ("Motivation", "Notes"),
    "question": ("Question", "Context"),
}
_SKIP_SECTIONS = {"relevant outputs", "generated outputs"}


def _body(path: Path) -> str:
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            newline = text.find("\n", end + 4)
            text = text[newline + 1:] if newline != -1 else ""
    return text


def _sections(text: str) -> Dict[str, str]:
    matches = list(_SECTION_RE.finditer(text))
    result: Dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1).strip().lower()] = text[match.end():end].strip()
    return result


def _plain(text: str, limit: int = 280) -> str:
    text = _COMMENT_RE.sub("", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        lines.append(stripped)
    plain = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if len(plain) > limit:
        plain = plain[: limit - 1].rstrip() + "…"
    return plain


def _excerpt(record: Any, limit: int = 280) -> str:
    try:
        sections = _sections(_body(record.path))
    except OSError:
        return ""
    for heading in _PREFERRED_SECTIONS.get(record.kind, ()):
        value = sections.get(heading.lower())
        if value:
            plain = _plain(value, limit)
            if plain:
                return plain
    for heading, value in sections.items():
        if heading in _SKIP_SECTIONS:
            continue
        plain = _plain(value, limit)
        if plain and "Generated artifacts belong under" not in plain:
            return plain
    return ""


def _state_summary(root: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    try:
        path = config_path(root, "state")
    except ProjectError:
        return {}
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    sections = _sections(text)
    updated = _UPDATED_RE.search(text)
    return {
        "updated": updated.group(1) if updated else "",
        "current_understanding": _plain(
            sections.get("current understanding", ""), 520
        ),
        "next_actions": _plain(sections.get("next actions", ""), 420),
        "open_lines": _plain(sections.get("open lines", ""), 420),
    }


def _values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dataset_nodes(root: Path) -> List[Dict[str, Any]]:
    try:
        registry = load_registry(root)
    except ProjectError:
        return []
    if registry is None:
        return []
    entries = registry.get("datasets")
    if not isinstance(entries, list):
        return []
    nodes: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        storage = entry.get("storage", "local")
        nodes.append(
            {
                "id": identifier.strip(),
                "kind": "dataset",
                "title": str(entry.get("name") or identifier),
                "status": str(storage or "local"),
                "created": str(entry.get("acquired") or entry.get("created") or ""),
                "path": str(entry.get("path") or entry.get("uri") or ""),
                "external": storage == "external",
                "excerpt": str(entry.get("source") or storage or ""),
            }
        )
    return nodes


def _figure_nodes(root: Path) -> List[Dict[str, Any]]:
    """Read figure manifests and turn their evidence links into graph edges."""
    directory = Path(root) / FIGURES_DIR
    if not directory.is_dir():
        return []
    result: List[Dict[str, Any]] = []
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        manifest = entry / "manifest.yaml"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        release = data.get("release")
        approved = (
            isinstance(release, dict) and release.get("approved") is True
        )
        identifier = "figure:{}".format(entry.name)
        result.append(
            {
                "id": identifier,
                "label": entry.name,
                "kind": "figure",
                "title": "Figure {}".format(entry.name),
                "status": str(data.get("status") or "unknown"),
                "created": "",
                "path": relative_path(root, entry),
                "approved": approved,
                "excerpt": "Publication figure",
                "evidence": _figure_evidence(data),
            }
        )
    return result


def _figure_evidence(data: Dict[str, Any]) -> List[str]:
    panels = data.get("panels")
    if not isinstance(panels, dict):
        return []
    evidence: List[str] = []
    for panel in panels.values():
        if not isinstance(panel, dict):
            continue
        raw = panel.get("evidence")
        if not isinstance(raw, dict):
            continue
        values: List[str] = []
        single = raw.get("experiment")
        if isinstance(single, str) and single.strip():
            values.append(single.strip())
        for field in ("experiments", "explorations", "datasets"):
            items = raw.get(field)
            if isinstance(items, list):
                values.extend(
                    str(item).strip()
                    for item in items
                    if isinstance(item, str) and item.strip()
                )
        for value in values:
            if value not in evidence:
                evidence.append(value)
    return evidence


def build_graph(root: Path) -> Dict[str, Any]:
    """Build the read-only payload consumed by the web UI."""
    root = Path(root)
    config = load_config(root)
    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    name = str((project or {}).get("name") or root.name)

    records_by_id: Dict[str, Any] = {}
    nodes: Dict[str, Dict[str, Any]] = {}
    for kind in KINDS:
        records, _problems = load_records(root, kind)
        for record in records:
            records_by_id[record.id] = record
            nodes[record.id] = {
                "id": record.id,
                "kind": record.kind,
                "title": record.title,
                "status": record.status,
                "created": record.created,
                "path": relative_path(root, record.path),
                "excerpt": _excerpt(record),
            }

    for dataset in _dataset_nodes(root):
        nodes.setdefault(dataset["id"], dataset)

    figure_edges: List[Dict[str, str]] = []
    for figure in _figure_nodes(root):
        evidence = figure.pop("evidence", [])
        nodes.setdefault(figure["id"], figure)
        for target in evidence:
            figure_edges.append(
                {
                    "source": figure["id"],
                    "target": target,
                    "relation": "evidence",
                    "inverse": "figures",
                }
            )

    edges: List[Dict[str, str]] = []
    seen: set = set()

    def add_edge(source: str, target: str, relation: str, inverse: str) -> None:
        key = (source, target, relation)
        if key in seen or source not in nodes or target not in nodes:
            return
        seen.add(key)
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "inverse": inverse,
            }
        )

    for relation in RELATIONS:
        for source_id, record in records_by_id.items():
            if record.kind not in relation.sources:
                continue
            for target in _values(record.data.get(relation.name)):
                add_edge(source_id, target, relation.name, relation.inverse)

    # Dataset links are not record-to-record edges, but they belong in the
    # provenance graph.
    for source_id, record in records_by_id.items():
        if record.kind != "experiment":
            continue
        for target in _values(record.data.get("datasets")):
            add_edge(source_id, target, "datasets", "experiments")

    for figure_edge in figure_edges:
        add_edge(
            figure_edge["source"],
            figure_edge["target"],
            figure_edge["relation"],
            figure_edge["inverse"],
        )

    from .commands.validate import validate_project

    diagnostics = diagnostics_from_problems(validate_project(root))
    figures = [
        {
            "id": figure_id,
            "status": status or "unknown",
            "approved": approved,
        }
        for figure_id, status, approved in list_figures(root)
    ]

    ordered_nodes = sorted(
        nodes.values(),
        key=lambda item: (
            _KIND_ORDER.get(item["kind"], 99),
            id_number(item["id"]),
            item["id"],
        ),
    )
    counts: Dict[str, int] = {}
    for node in ordered_nodes:
        counts[node["kind"]] = counts.get(node["kind"], 0) + 1

    timeline = sorted(
        ordered_nodes,
        key=lambda item: (item.get("created") or "", _KIND_ORDER.get(item["kind"], 99), item["id"]),
    )

    return {
        "schema_version": 1,
        "project": {
            "name": name,
            "root": str(root),
            "version": __version__,
        },
        "ok": not any(item.severity == "error" for item in diagnostics),
        "counts": counts,
        "nodes": ordered_nodes,
        "edges": edges,
        "timeline": [node["id"] for node in timeline],
        "figures": figures,
        "state": _state_summary(root, config),
        "diagnostics": [item.to_dict() for item in diagnostics],
    }


class WebHandler(BaseHTTPRequestHandler):
    """Serve the embedded UI and a read-only graph API."""

    project_root: Path
    index_html: str
    server_version = "sciharness/{}".format(__version__)

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        self._send(
            status,
            "application/json; charset=utf-8",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", self.index_html.encode("utf-8"))
            return
        if path == "/api/graph":
            try:
                payload = build_graph(self.project_root)
            except ProjectError as exc:
                self._json(500, {"error": str(exc)})
            else:
                self._json(200, payload)
            return
        if path == "/health":
            self._json(200, {"ok": True, "version": __version__})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args: Any) -> None:
        # A viewer should be quiet; request logging would interleave with the
        # printed URL and serve no purpose for a local read-only tool.
        return


class WebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(
    root: Path, host: str = "127.0.0.1", port: int = 8765
) -> WebServer:
    if not INDEX_HTML.is_file():
        raise ProjectError("bundled web UI is missing: {}".format(INDEX_HTML))
    html = INDEX_HTML.read_text(encoding="utf-8")
    handler = type(
        "SciHarnessWebHandler",
        (WebHandler,),
        {"project_root": Path(root), "index_html": html},
    )
    try:
        return WebServer((host, port), handler)
    except OSError as exc:
        raise ProjectError(
            "cannot start web viewer on {}:{}: {}".format(host, port, exc)
        ) from exc


def server_url(server: WebServer) -> str:
    host, port = server.server_address[:2]
    display = str(host)
    if display in ("0.0.0.0", "::"):
        display = "127.0.0.1"
    if ":" in display and not display.startswith("["):
        display = "[{}]".format(display)
    return "http://{}:{}/".format(display, port)
