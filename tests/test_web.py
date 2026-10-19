"""Read-only web viewer: graph payload and local HTTP endpoints."""
import json
import threading
from urllib.request import urlopen

import yaml

from sciharness.cli import main
from sciharness.web import build_graph, create_server, server_url


def _seed(project):
    assert main(["new", "question", "Q", "--path", str(project)]) == 0
    assert main(
        ["new", "exploration", "X", "--question", "Q001", "--path", str(project)]
    ) == 0
    assert main(
        [
            "new",
            "experiment",
            "E",
            "--question",
            "Q001",
            "--exploration",
            "X001",
            "--path",
            str(project),
        ]
    ) == 0
    assert main(
        [
            "new",
            "decision",
            "D",
            "--question",
            "Q001",
            "--evidence",
            "X001",
            "--evidence",
            "EXP001",
            "--path",
            str(project),
        ]
    ) == 0


def test_graph_payload_contains_nodes_edges_and_diagnostics(project):
    _seed(project)
    graph = build_graph(project)

    assert graph["schema_version"] == 1
    assert graph["project"]["name"] == "Test Project"
    assert graph["ok"] is True
    assert graph["diagnostics"] == []

    ids = {node["id"] for node in graph["nodes"]}
    assert {"Q001", "X001", "EXP001", "D001"} <= ids
    assert graph["counts"]["decision"] == 1

    edge_set = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in graph["edges"]
    }
    assert ("D001", "X001", "evidence") in edge_set
    assert ("D001", "EXP001", "evidence") in edge_set
    assert ("D001", "Q001", "question") in edge_set
    assert ("EXP001", "X001", "exploration") in edge_set
    assert ("EXP001", "Q001", "question") in edge_set
    assert graph["timeline"]


def test_graph_includes_datasets(project):
    (project / "data" / "raw").mkdir(parents=True)
    (project / "data" / "raw" / "run.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (project / "data" / "registry.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "datasets": [
                    {"id": "DS001", "name": "Run", "path": "data/raw/run.csv"}
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "new",
                "experiment",
                "E",
                "--dataset",
                "DS001",
                "--path",
                str(project),
            ]
        )
        == 0
    )
    graph = build_graph(project)
    assert any(node["id"] == "DS001" for node in graph["nodes"])
    assert any(
        edge["source"] == "EXP001"
        and edge["target"] == "DS001"
        and edge["relation"] == "datasets"
        for edge in graph["edges"]
    )


def test_web_server_serves_ui_and_graph(project):
    _seed(project)
    server = create_server(project, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = server_url(server)
    try:
        with urlopen(base + "api/graph", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["project"]["name"] == "Test Project"
        assert any(node["id"] == "D001" for node in payload["nodes"])

        with urlopen(base, timeout=10) as response:
            html = response.read().decode("utf-8")
        assert "SciHarness" in html
        assert "Decision chain" in html

        with urlopen(base + "health", timeout=10) as response:
            assert json.loads(response.read().decode("utf-8"))["ok"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
