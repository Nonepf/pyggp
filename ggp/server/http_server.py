"""
GGPServer — HTTP server implementing the GGP competition protocol.

The Game Manager communicates with players over HTTP. Each request is
a POST with Content-Type: text/acl containing a single GCL message in
S-expression format. The player responds with a plain-text reply.

Wire format reference (Chapter 3, Stanford GGP Book)
-----------------------------------------------------

    Request body:  (start match1 white (...rules...) 10 10)
    Response body: ready

    Request body:  (play match1 ((mark 1 1) noop))
    Response body: mark(2,2)

    Request body:  (stop match1 ((mark 3 3) noop))
    Response body: done

Timeout enforcement
-------------------
The server enforces the start clock and play clock by running the player
handler in a daemon thread. If the player does not respond before the
deadline, the server falls back to ``player._fallback_move`` (set by
LegalPlayer / RandomPlayer) or the literal string "noop".

              GGP Server thread           Player worker thread
              ─────────────────           ────────────────────
              receive HTTP request
              parse GCL message
              create Clock
              start worker thread ──────► on_start / on_play
              join(timeout=clock) ◄────── returns action
              if timed out:
                  use fallback move
              send HTTP response

Usage::

    server = GGPServer(player, host="0.0.0.0", port=9147)
    server.start()          # blocks; Ctrl-C to stop
    # or
    server.start_background()  # non-blocking; call server.stop() later
"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from ggp.player.base import Clock, GGPPlayer
from ggp.protocol.messages import (
    AbortMessage,
    InfoMessage,
    PlayMessage,
    StartMessage,
    StopMessage,
)
from ggp.protocol.parser import parse_gcl_message

logger = logging.getLogger(__name__)

# Default HTTP content type for GCL responses (per the GGP spec).
_GCL_CONTENT_TYPE = "text/acl"

# Fallback action used when the player times out and has no fallback set.
_EMERGENCY_FALLBACK = "noop"


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _GGPRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for GGP messages.

    The ``player`` attribute is injected by GGPServer before the handler
    class is passed to HTTPServer.
    """

    # Will be set by GGPServer before instantiation.
    player: GGPPlayer
    clock_buffer: float

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_body()
        if body is None:
            return

        logger.debug("← Received: %s", body[:200])

        try:
            msg = parse_gcl_message(body)
        except ValueError as exc:
            logger.error("Failed to parse GCL message: %s\n  Body: %r", exc, body)
            self._send_response("error", status=400)
            return

        response = self._dispatch(msg)
        logger.debug("→ Sending: %s", response)
        self._send_response(response)

    def do_GET(self) -> None:  # noqa: N802
        """Respond to GET requests with a simple status page."""
        self._send_response("GGP Player running.", content_type="text/plain")

    # Suppress default HTTP request logging to stdout.
    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug("HTTP: " + fmt, *args)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, msg) -> str:
        """Route a parsed GCL message to the appropriate player handler."""

        if isinstance(msg, InfoMessage):
            return self.player.on_info()

        if isinstance(msg, StartMessage):
            clock = Clock(msg.startclock, buffer=self.clock_buffer)
            return self._run_with_timeout(
                target=lambda: self.player.on_start(msg, clock),
                clock=clock,
                fallback="ready",
                phase="start",
                match_id=msg.match_id,
            )

        if isinstance(msg, PlayMessage):
            # Retrieve the playclock from the active match context.
            ctx = self.player.context
            if ctx is None:
                logger.error("Received play message but no active match context.")
                return _EMERGENCY_FALLBACK
            clock = Clock(ctx.playclock, buffer=self.clock_buffer)
            return self._run_with_timeout(
                target=lambda: self.player.on_play(msg, clock),
                clock=clock,
                fallback=self._get_fallback(),
                phase="play",
                match_id=msg.match_id,
            )

        if isinstance(msg, StopMessage):
            # Stop does not have a hard clock; run directly.
            return self.player.on_stop(msg)

        if isinstance(msg, AbortMessage):
            return self.player.on_abort(msg)

        logger.error("Unknown message type: %r", msg)
        return "error"

    # ------------------------------------------------------------------
    # Timeout enforcement
    # ------------------------------------------------------------------

    def _run_with_timeout(
        self,
        target,
        clock: Clock,
        fallback: str,
        phase: str,
        match_id: str,
    ) -> str:
        """
        Run *target* in a worker thread, returning its result or *fallback*
        if the clock expires first.
        """
        result_holder: list[str] = []
        exc_holder: list[BaseException] = []

        def worker() -> None:
            try:
                result_holder.append(target())
            except Exception as exc:  # noqa: BLE001
                exc_holder.append(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=clock.remaining())

        if exc_holder:
            logger.exception(
                "Player raised an exception during %s phase of match %s:",
                phase, match_id, exc_info=exc_holder[0],
            )
            return fallback

        if thread.is_alive():
            logger.warning(
                "Player exceeded %s clock for match %s (%.1fs allotted). "
                "Using fallback: %r.",
                phase, match_id, clock.total, fallback,
            )
            return fallback

        return result_holder[0] if result_holder else fallback

    def _get_fallback(self) -> str:
        fb = getattr(self.player, "_fallback_move", None)
        return fb if fb is not None else _EMERGENCY_FALLBACK

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _read_body(self) -> Optional[str]:
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            return raw.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            logger.error("Failed to read request body: %s", exc)
            self._send_response("error", status=400)
            return None

    def _send_response(
        self,
        body: str,
        status: int = 200,
        content_type: str = _GCL_CONTENT_TYPE,
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)


# ---------------------------------------------------------------------------
# GGPServer
# ---------------------------------------------------------------------------

class GGPServer:
    """
    HTTP server that bridges the GGP wire protocol to a GGPPlayer instance.

    Args:
        player:        The player instance to serve.
        host:          Bind address (default "0.0.0.0" — all interfaces).
        port:          Listen port (default 9147 — GGP competition default).
        clock_buffer:  Safety margin (seconds) subtracted from each clock
                       before passing it to the player. Accounts for network
                       round-trip time and Python overhead (default 0.2 s).

    Example::

        server = GGPServer(player, port=9147)
        server.start()  # blocks until Ctrl-C

    Running in the background::

        server = GGPServer(player, port=9147)
        server.start_background()
        # ... do other things ...
        server.stop()
    """

    def __init__(
        self,
        player: GGPPlayer,
        host: str = "0.0.0.0",
        port: int = 9147,
        clock_buffer: float = 0.2,
    ) -> None:
        self.player = player
        self.host = host
        self.port = port
        self.clock_buffer = clock_buffer
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the server and block until interrupted (Ctrl-C / SIGINT).

        Logs startup information including the listening address.
        """
        self._httpd = self._make_server()
        logger.info(
            "GGP player server listening on http://%s:%d/",
            self.host, self.port,
        )
        print(
            f"[ggp] Player server running at http://{self.host}:{self.port}/ "
            "(Press Ctrl-C to stop)"
        )
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[ggp] Shutting down.")
        finally:
            self._httpd.server_close()

    def start_background(self) -> None:
        """
        Start the server in a background daemon thread (non-blocking).

        Use ``stop()`` to shut it down.
        """
        self._httpd = self._make_server()
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name=f"GGPServer:{self.port}",
        )
        self._thread.start()
        logger.info(
            "GGP player server started in background on http://%s:%d/",
            self.host, self.port,
        )

    def stop(self) -> None:
        """Shut down a background server started with ``start_background()``."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            logger.info("GGP server stopped.")

    @property
    def address(self) -> tuple[str, int]:
        """The (host, port) tuple this server is bound to."""
        return (self.host, self.port)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_server(self) -> HTTPServer:
        """Build the HTTPServer, injecting the player into the handler class."""
        # Create a fresh handler subclass so multiple servers can coexist.
        handler_cls = type(
            "_GGPHandler",
            (_GGPRequestHandler,),
            {
                "player": self.player,
                "clock_buffer": self.clock_buffer,
            },
        )
        server = HTTPServer((self.host, self.port), handler_cls)
        return server
