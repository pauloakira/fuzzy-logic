"""Fixtures for browser end-to-end tests.

A real uvicorn process serving the real app, driven by a real headless browser.
`TestClient` cannot cover this layer: it never runs the JavaScript, so it cannot
tell whether the page actually talks to the API it was written against.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest

pytest.importorskip("playwright", reason="pip install -e '.[dev]' for browser tests")

import uvicorn  # noqa: E402

from editor.api import app  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def server() -> Iterator[str]:
    """Run the app in a background thread and yield its base URL."""
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30.0
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("uvicorn did not start within 30 s")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10.0)


@pytest.fixture
def page_errors(page):
    """Fail a test if the page logged a console error or threw.

    A UI that renders but throws underneath is not passing, and without this the
    browser swallows it silently.
    """
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

    def on_console(msg):
        if msg.type != "error":
            return
        # The browser logs every non-2xx response as a console error, but this
        # app handles 4xx deliberately — a 409 asking to confirm an overwrite, a
        # 422 refusing an unloadable spec. Those are features under test, not
        # faults. Uncaught exceptions still fail, which is the point.
        if "Failed to load resource" in msg.text:
            return
        errors.append(f"console.{msg.type}: {msg.text}")

    page.on("console", on_console)
    yield errors
