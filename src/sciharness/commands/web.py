"""``sci web``: serve a read-only local decision-chain viewer."""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from typing import Any

from ..output import EXIT_OK, emit, envelope, project_info
from ..project import find_project_root
from ..web import create_server, server_url


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    server = create_server(root, host=args.host, port=args.port)
    url = server_url(server)

    if getattr(args, "json", False):
        emit(
            envelope(
                "web",
                project=project_info(root),
                data={
                    "url": url,
                    "host": args.host,
                    "port": server.server_address[1],
                    "read_only": True,
                },
            )
        )
        sys.stdout.flush()
    else:
        print("SciHarness web viewer: {}".format(url))
        print("  read-only; press Ctrl-C to stop")
        sys.stdout.flush()

    if getattr(args, "open", False):
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        server.server_close()
    return EXIT_OK
