"""A controlled HTTP server for the fetcher's integration tests, and the policy to reach it.

Both pieces are **test infrastructure and only test infrastructure**. The loopback-permitting
policy is defined here rather than in ``src/`` on purpose: the shipped
``PublicTargetPolicy`` takes no argument that could widen its address rule, so the only way to
reach a server on 127.0.0.1 is to subclass it in test code. Nothing that can be configured in
production is involved, and ``test_target_policy`` asserts the shipped policy still refuses
every loopback address.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

from pxapi.adapters.web.target_policy import PublicTargetPolicy

LOOPBACK = {"127.0.0.1", "::1"}


class LoopbackTargetPolicy(PublicTargetPolicy):
    """Permits loopback in addition to public addresses. Test-only."""

    def _permits(self, address: str) -> bool:
        return address in LOOPBACK or super()._permits(address)


def loopback_policy() -> LoopbackTargetPolicy:
    """A loopback policy that resolves every name to 127.0.0.1 without touching DNS."""
    return LoopbackTargetPolicy(resolve=lambda host, port: ["127.0.0.1"])


@dataclass
class Route:
    """One canned response."""

    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    #: Seconds to stall before responding, for exercising the read timeout.
    delay: float = 0.0


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    routes: ClassVar[dict[str, Route]] = {}

    def do_GET(self) -> None:  # stdlib requires this exact spelling
        route = self.routes.get(self.path)
        if route is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route.delay:
            time.sleep(route.delay)
        self.send_response(route.status)
        for name, value in route.headers.items():
            self.send_header(name, value)
        if "Content-Length" not in route.headers:
            self.send_header("Content-Length", str(len(route.body)))
        self.end_headers()
        if route.body:
            self.wfile.write(route.body)

    def log_message(self, *args: Any) -> None:
        """Silence: the server's stderr chatter is not part of any assertion."""


class ControlledHttpServer:
    """A real HTTP server on loopback, serving exactly the routes it was given."""

    def __init__(self, routes: dict[str, Route]) -> None:
        handler = type("BoundHandler", (_Handler,), {"routes": routes})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def __enter__(self) -> ControlledHttpServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
