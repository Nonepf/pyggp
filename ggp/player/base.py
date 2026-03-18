"""
GGPPlayer — abstract base class for all GGP HTTP players.

Architecture
------------

                    GGPServer (HTTP layer)
                          │
                          │  calls handler methods
                          ▼
                    GGPPlayer  (this module)
                    ┌─────────────────────────────────────┐
                    │  on_info()                          │
                    │  on_start(msg, clock) → "ready"     │
                    │  on_play(msg, clock)  → action_str  │
                    │  on_stop(msg)         → "done"      │
                    │  on_abort(msg)        → "done"      │
                    └──────────────┬──────────────────────┘
                                   │ uses
                             StateMachine
                           (user-supplied)

Timeout safety
--------------
The server calls on_start / on_play inside a worker thread and enforces
the clock via threading.Thread.join(timeout=...). If the player thread
does not finish in time, the server falls back to the player's
_fallback_move attribute (set by LegalPlayer / RandomPlayer subclasses).

Players should poll clock.is_expired() or check clock.remaining() in
their inner search loops to self-terminate before the deadline.

Match lifecycle
---------------
    on_start  → initialise state machine, set self.state = initial state
    on_play   → update self.state with previous joint move, choose action
    on_stop   → optional cleanup
    on_abort  → optional cleanup
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from ggp.protocol.messages import (
    AbortMessage,
    PlayMessage,
    StartMessage,
    StopMessage,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------

class Clock:
    """
    A countdown timer for a single start or play turn.

    The server creates one Clock per message and passes it to the player
    handler. Players (especially search-based ones) should consult the
    clock to avoid overrunning the time limit.

    Args:
        seconds:  Total allotted time in seconds.
        buffer:   Safety margin subtracted from the deadline (default 0.2 s).
                  Accounts for network latency and Python call-stack overhead.

    Usage:
        while not clock.is_expired():
            # ... search deeper ...
            pass
        return best_action_found_so_far
    """

    def __init__(self, seconds: float, buffer: float = 0.2) -> None:
        if seconds <= 0:
            raise ValueError(f"Clock seconds must be positive, got {seconds}.")
        self._total = seconds
        self._buffer = buffer
        self._deadline = time.monotonic() + seconds - buffer
        self._start = time.monotonic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def remaining(self) -> float:
        """Seconds left before the deadline (never negative)."""
        return max(0.0, self._deadline - time.monotonic())

    def elapsed(self) -> float:
        """Seconds elapsed since the clock was created."""
        return time.monotonic() - self._start

    def is_expired(self) -> bool:
        """True once the deadline has passed."""
        return time.monotonic() >= self._deadline

    @property
    def total(self) -> float:
        """Total allotted seconds (before buffer subtraction)."""
        return self._total

    def __repr__(self) -> str:
        return (
            f"Clock(total={self._total}s, buffer={self._buffer}s, "
            f"remaining={self.remaining():.3f}s)"
        )


# ---------------------------------------------------------------------------
# Match context
# ---------------------------------------------------------------------------

@dataclass
class MatchContext:
    """
    Holds all per-match state that the framework tracks automatically.

    Attributes:
        match_id:    Identifier assigned by the Game Manager.
        role:        This player's role in the current match.
        rules:       Raw GDL rules string as received in the start message.
        startclock:  Allotted seconds for the start phase.
        playclock:   Allotted seconds per play turn.
        state:       Current game state (opaque; set by player subclasses).
        step:        Number of play messages received (0 = before first play).
    """

    match_id: str
    role: str
    rules: str
    startclock: int
    playclock: int
    state: Any = field(default=None, repr=False)
    step: int = 0

    def __repr__(self) -> str:
        return (
            f"MatchContext(match_id={self.match_id!r}, role={self.role!r}, "
            f"step={self.step})"
        )


# ---------------------------------------------------------------------------
# StateMachineFactory type alias
# ---------------------------------------------------------------------------

# A callable that takes the raw GDL rules string and returns a StateMachine.
StateMachineFactory = Callable[[str], Any]


# ---------------------------------------------------------------------------
# GGPPlayer base class
# ---------------------------------------------------------------------------

class GGPPlayer(ABC):
    """
    Abstract base class for GGP HTTP players.

    Subclass this and implement at minimum:
        select_move(context, clock) → str

    Optionally override:
        setup(context, clock)    — called after state machine is ready
        teardown(context, moves) — called on stop or abort

    The framework handles:
        • Protocol message parsing
        • Match context bookkeeping
        • Clock creation and injection
        • Fallback move on timeout (requires _fallback_move to be set)

    Example::

        class MyPlayer(GGPPlayer):
            def select_move(self, context, clock):
                moves = self.sm.get_legal_moves(context.state, context.role)
                return moves[0]   # just pick the first legal move
    """

    def __init__(
        self,
        state_machine_factory: StateMachineFactory | None = None,
        clock_buffer: float = 0.2,
    ) -> None:
        """
        Args:
            state_machine_factory:
                Callable ``(rules: str) -> StateMachine``.
                If None, ``self.sm`` will not be set automatically; the
                subclass is responsible for building the state machine in
                ``setup()``.
            clock_buffer:
                Safety buffer subtracted from every clock (seconds).
        """
        self._sm_factory = state_machine_factory
        self._clock_buffer = clock_buffer
        self._context: MatchContext | None = None
        self._fallback_move: str | None = None  # set by subclasses
        self.sm: Any = None  # StateMachine instance (set in on_start)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def context(self) -> MatchContext | None:
        """The current MatchContext, or None if no match is active."""
        return self._context

    # ------------------------------------------------------------------
    # Framework entry points (called by GGPServer)
    # ------------------------------------------------------------------

    def on_info(self) -> str:
        """
        Respond to a Game Manager ping.

        Returns "available" normally, or "busy" if the player is mid-match
        and cannot accept a new one. Override to customise.
        """
        return "available"

    def on_start(self, msg: StartMessage, clock: Clock) -> str:
        """
        Handle a start message.

        1. Builds the state machine via the factory (if provided).
        2. Initialises the match context.
        3. Sets ``self.sm`` and ``context.state`` to the initial state.
        4. Calls ``self.setup(context, clock)`` for subclass-level init.

        Returns "ready".
        """
        logger.info(
            "Starting match %s as role %s (startclock=%ds, playclock=%ds).",
            msg.match_id, msg.role, msg.startclock, msg.playclock,
        )

        self._context = MatchContext(
            match_id=msg.match_id,
            role=msg.role,
            rules=msg.rules,
            startclock=msg.startclock,
            playclock=msg.playclock,
        )

        if self._sm_factory is not None:
            self.sm = self._sm_factory(msg.rules)
            self._context.state = self.sm.get_initial_state()
            logger.debug("State machine initialised; initial state ready.")

        self.setup(self._context, clock)
        return "ready"

    def on_play(self, msg: PlayMessage, clock: Clock) -> str:
        """
        Handle a play message.

        1. Advances the game state using the previous joint move.
        2. Delegates to ``self.select_move(context, clock)``.

        Returns the chosen action string.
        """
        ctx = self._require_context()
        ctx.step += 1

        # --- advance state -------------------------------------------
        if msg.moves is not None and self.sm is not None:
            roles = self.sm.get_roles()
            if len(msg.moves) == len(roles):
                joint_move = dict(zip(roles, msg.moves))
                ctx.state = self.sm.get_next_state(ctx.state, joint_move)
                logger.debug("Advanced to step %d via joint move %s.", ctx.step, joint_move)
            else:
                logger.warning(
                    "Joint move length mismatch: expected %d roles, got %d moves.",
                    len(roles), len(msg.moves),
                )

        # --- choose action -------------------------------------------
        action = self.select_move(ctx, clock)
        logger.info("Step %d: selected action %r.", ctx.step, action)
        return action

    def on_stop(self, msg: StopMessage) -> str:
        """Handle a stop message. Calls ``teardown`` and returns "done"."""
        ctx = self._context
        logger.info("Match %s stopped.", msg.match_id)
        if ctx is not None:
            self.teardown(ctx, msg.moves)
        self._context = None
        self.sm = None
        return "done"

    def on_abort(self, msg: AbortMessage) -> str:
        """Handle an abort message. Calls ``teardown`` and returns "done"."""
        ctx = self._context
        logger.info("Match %s aborted.", msg.match_id)
        if ctx is not None:
            self.teardown(ctx, None)
        self._context = None
        self.sm = None
        return "done"

    # ------------------------------------------------------------------
    # Abstract / overridable hooks
    # ------------------------------------------------------------------

    @abstractmethod
    def select_move(self, context: MatchContext, clock: Clock) -> str:
        """
        Choose and return an action string for the current game state.

        This is the core method to implement. It will be called once per
        play message, with ``context.state`` already advanced to the
        current game state.

        Args:
            context:  Current match context (role, state, step, …).
            clock:    Countdown timer; poll ``clock.is_expired()`` to
                      avoid exceeding the time limit.

        Returns:
            A legal action string, e.g. ``"mark(1,1)"`` or ``"noop"``.
        """
        ...

    def setup(self, context: MatchContext, clock: Clock) -> None:
        """
        Called at the end of ``on_start``, after the state machine is ready.

        Override to perform additional initialisation (e.g. pre-computation,
        opening book lookup, etc.) within the start clock budget.

        The default implementation does nothing.
        """

    def teardown(self, context: MatchContext, last_moves: list[str] | None) -> None:
        """
        Called at the end of ``on_stop`` or ``on_abort``.

        Override to release resources, save learned data, log results, etc.

        Args:
            context:    The match context at termination time.
            last_moves: The final joint move (None on abort).

        The default implementation does nothing.
        """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_context(self) -> MatchContext:
        if self._context is None:
            raise RuntimeError(
                "on_play called before on_start. No active match context."
            )
        return self._context

    def _make_clock(self, seconds: float) -> Clock:
        return Clock(seconds, buffer=self._clock_buffer)
