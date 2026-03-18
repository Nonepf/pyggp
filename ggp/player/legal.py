"""
LegalPlayer — always selects the first legal move.

This is the simplest possible GGP player. It is useful as:
    • a sanity-check baseline that always plays legally
    • a fallback when no better strategy is available
    • a starting point for testing the server/framework setup

It requires a StateMachine to be injected via ``state_machine_factory``.

Example::

    from ggp import LegalPlayer, GGPServer

    def my_sm_factory(rules: str):
        return MyStateMachine(rules)

    player = LegalPlayer(state_machine_factory=my_sm_factory)
    server = GGPServer(player, port=9147)
    server.start()
"""

from __future__ import annotations

import logging

from ggp.player.base import Clock, GGPPlayer, MatchContext, StateMachineFactory

logger = logging.getLogger(__name__)


class LegalPlayer(GGPPlayer):
    """
    A player that always selects the first legal move in the current state.

    Move selection is deterministic and instantaneous: the player calls
    ``state_machine.get_legal_moves(state, role)`` and returns index 0.

    This player uses zero of its allotted play clock. It is therefore
    immune to timeout issues, which makes it ideal for integration tests.

    Args:
        state_machine_factory:
            Callable ``(rules: str) -> StateMachine`` used to build the
            game engine when a start message is received.
        clock_buffer:
            Safety margin passed to Clock (default 0.2 s). Not relevant
            for LegalPlayer itself, but required by the base class.
    """

    def __init__(
        self,
        state_machine_factory: StateMachineFactory,
        clock_buffer: float = 0.2,
    ) -> None:
        super().__init__(
            state_machine_factory=state_machine_factory,
            clock_buffer=clock_buffer,
        )

    def setup(self, context: MatchContext, clock: Clock) -> None:
        """Pre-compute the first legal move as the initial fallback."""
        self._update_fallback(context)

    def select_move(self, context: MatchContext, clock: Clock) -> str:
        """Return the first legal move for the current state."""
        move = self._first_legal(context)
        self._fallback_move = move  # keep fallback fresh
        return move

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _first_legal(self, context: MatchContext) -> str:
        moves = self.sm.get_legal_moves(context.state, context.role)
        if not moves:
            raise RuntimeError(
                f"No legal moves available for role {context.role!r} "
                f"at step {context.step}. "
                "The game description may not be well-formed."
            )
        return moves[0]

    def _update_fallback(self, context: MatchContext) -> None:
        try:
            self._fallback_move = self._first_legal(context)
        except Exception as exc:
            logger.warning("Could not compute fallback move: %s", exc)
