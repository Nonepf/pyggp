"""
RandomPlayer — selects a uniformly random legal move each turn.

Slightly more interesting than LegalPlayer because it is non-deterministic
and avoids systematic traps that a fixed-order legal player might fall into.

Useful as:
    • a stochastic baseline
    • an opponent simulator in offline self-play
    • verifying that the framework handles the full playclock correctly

Example::

    import random
    from ggp import RandomPlayer, GGPServer

    player = RandomPlayer(
        state_machine_factory=my_sm_factory,
        seed=42,        # reproducible play (optional)
    )
    server = GGPServer(player, port=9147)
    server.start()
"""

from __future__ import annotations

import logging
import random as _random_module
from typing import Optional

from ggp.player.base import Clock, GGPPlayer, MatchContext, StateMachineFactory

logger = logging.getLogger(__name__)


class RandomPlayer(GGPPlayer):
    """
    A player that selects uniformly at random from all legal moves.

    Args:
        state_machine_factory:
            Callable ``(rules: str) -> StateMachine``.
        seed:
            Optional integer seed for the random number generator.
            Useful for reproducible experiments.
        clock_buffer:
            Safety margin passed to Clock (default 0.2 s).
    """

    def __init__(
        self,
        state_machine_factory: StateMachineFactory,
        seed: Optional[int] = None,
        clock_buffer: float = 0.2,
    ) -> None:
        super().__init__(
            state_machine_factory=state_machine_factory,
            clock_buffer=clock_buffer,
        )
        self._rng = _random_module.Random(seed)

    def setup(self, context: MatchContext, clock: Clock) -> None:
        """Pre-compute a random legal move as the initial fallback."""
        self._update_fallback(context)

    def select_move(self, context: MatchContext, clock: Clock) -> str:
        """Return a uniformly random legal move."""
        moves = self.sm.get_legal_moves(context.state, context.role)
        if not moves:
            raise RuntimeError(
                f"No legal moves for role {context.role!r} at step {context.step}."
            )
        chosen = self._rng.choice(moves)
        self._fallback_move = chosen
        logger.debug(
            "Random choice: %r from %d legal moves.", chosen, len(moves)
        )
        return chosen

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_fallback(self, context: MatchContext) -> None:
        try:
            moves = self.sm.get_legal_moves(context.state, context.role)
            if moves:
                self._fallback_move = self._rng.choice(moves)
        except Exception as exc:
            logger.warning("Could not compute fallback move: %s", exc)
