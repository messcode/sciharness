# Web viewer

`sci web` starts a small, dependency-free, read-only web viewer for one project.
It is intentionally local: the default bind address is `127.0.0.1`, and the
server exposes only the embedded UI plus a read-only graph API.

```bash
sci web
# SciHarness web viewer: http://127.0.0.1:8765/

sci web --port 0 --open
sci web --host 0.0.0.0 --port 8765   # exposes read-only project data on the network
```

Press `Ctrl-C` to stop. `sci web --json` prints the URL in the standard JSON
envelope before serving.

## Views

### Decision chain

The default view selects a Decision and lays out:

```text
Question  →  Evidence  →  Decision  →  Motivated work
```

- **Question** — the linked research question.
- **Evidence** — explorations/experiments cited by the Decision.
- **Decision** — the selected append-only decision.
- **Motivated work** — explorations/experiments that link back with
  `motivated_by`.
- **Supersedes** — older/newer decisions are shown as chips and remain
  clickable.

The left sidebar lists decisions with their evidence/downstream counts. The
right panel shows the selected record's path, status, outgoing references, and
incoming references.

### Graph

All questions, explorations, experiments, decisions, and datasets in one
provenance graph. Nodes are grouped by kind; edges follow provenance direction
(`evidence`, `motivated_by`, `supersedes`, `question`, `exploration`,
`datasets`). Clicking a node opens its detail; clicking a decision focuses its
chain.

### Timeline

Decisions in chronological order, with evidence and downstream-work chips. This
is the fastest way to answer “what changed, in what order?”.

## API

The viewer uses a single read-only endpoint:

```text
GET /api/graph
```

It returns one JSON object:

```json
{
  "schema_version": 1,
  "project": {"name": "...", "root": "...", "version": "0.6.0"},
  "ok": true,
  "counts": {"question": 1, "decision": 1},
  "nodes": [
    {"id": "D001", "kind": "decision", "title": "...", "status": "active",
     "created": "2026-10-19", "path": "docs/decisions/D001-....md"}
  ],
  "edges": [
    {"source": "D001", "target": "EXP001", "relation": "evidence", "inverse": "evidenced_by"}
  ],
  "timeline": ["Q001", "EXP001", "D001"],
  "figures": [{"id": "figure3", "status": "working", "approved": false}],
  "diagnostics": []
}
```

`GET /health` returns `{"ok": true, "version": "..."}`. Unknown paths return a
JSON 404.

## Security and scope

- Read-only: there are no POST/PUT/DELETE endpoints and no file download route.
- No project path is accepted from the browser; the server is bound to one root
  at startup.
- `--host 0.0.0.0` exposes project metadata to the network; use it only on a
  trusted network.
- The viewer does not run the CLI, execute experiments, render plots, or modify
  records. Use the CLI for all mutations.

The UI asset is packaged at `src/sciharness/resources/web/index.html`; it uses
vanilla HTML/CSS/JS and has no external CDN dependencies.
