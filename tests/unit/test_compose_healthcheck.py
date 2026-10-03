"""Run the exact Compose Python probe against an owned temporary HTTP server."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from typing import Any

import pytest
import yaml


COMPOSE_PATH = Path(__file__).resolve().parents[2] / "compose.yaml"
HEALTH = {
    "status": "degraded",
    "db": "error",
    "discogsography_api_check": "failed",
    "mqtt": "degraded",
    "version": "synthetic",
    "started_at": "2026-01-01T00:00:00+00:00",
    "sync_age_seconds": None,
}


def run_compose_probe(
    status: int, content_type: str, body: bytes
) -> subprocess.CompletedProcess[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        config = yaml.safe_load(COMPOSE_PATH.read_text())
        command = config["services"]["api"]["healthcheck"]["test"]
        assert command[:3] == ["CMD", "python", "-c"]
        script = command[3].replace(
            "http://127.0.0.1:8000/api/health",
            f"http://127.0.0.1:{server.server_port}/api/health",
        )
        # The command is checked-in Compose code, never an HTTP response or user input.
        return subprocess.run(  # noqa: S603
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=6
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize("status", ["ok", "degraded"])
def test_probe_accepts_existing_health_contract(status: str) -> None:
    health = {**HEALTH, "status": status}
    result = run_compose_probe(200, "application/json; charset=utf-8", json.dumps(health).encode())
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("http_status", "content_type", "body"),
    [
        (200, "text/html", b"<!doctype html><title>SPA fallback</title>"),
        (200, "text/plain", json.dumps(HEALTH).encode()),
        (200, "application/json", b"broken json"),
        (200, "application/json", b'{"status":"ok"}'),
        (200, "application/json", b"[]"),
        (200, "application/json", json.dumps({**HEALTH, "db": "unexpected"}).encode()),
        (404, "application/json", b'{"detail":"Not Found"}'),
    ],
)
def test_probe_rejects_html_missing_route_and_wrong_health_shape(
    http_status: int,
    content_type: str,
    body: bytes,
) -> None:
    result = run_compose_probe(http_status, content_type, body)
    assert result.returncode != 0
