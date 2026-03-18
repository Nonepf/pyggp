"""
examples/custom_player.py
=========================

A self-contained example showing how to:

1. Implement a minimal StateMachine stub (no real GDL engine).
2. Write a custom GGPPlayer subclass.
3. Spin up the HTTP server.

Run this script, then point a GGP Game Manager at http://localhost:9147/.

For quick local testing without a real Game Manager, you can send raw
HTTP requests with curl:

    curl -X POST http://localhost:9147/ \\
         -H "Content-Type: text/acl" \\
         -d "(info)"

    curl -X POST http://localhost:9147/ \\
         -H "Content-Type: text/acl" \\
         -d "(start match1 white ((role white)(role black)) 30 10)"

    curl -X POST http://localhost:9147/ \\
         -H "Content-Type: text/acl" \\
         -d "(play match1 nil)"

    curl -X POST http://localhost:9147/ \\
         -H "Content-Type: text/acl" \\
         -d "(stop match1 (noop noop))"
"""

import logging
import random

from ggp import GGPPlayer, GGPServer
from ggp.player.base import Clock, MatchContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Stub StateMachine (replace with your real GDL engine)
# ---------------------------------------------------------------------------

class SimpleState:
    def __init__(self, step: int = 0):
        self.step = step

    def __repr__(self):
        return f"SimpleState(step={self.step})"


class SimpleStateMachine:
    """
    A 5-step single-player game.
    Legal actions: left, right, up, down.
    Terminal at step 5; goal = 100.
    """

    def get_roles(self):
        return ["player"]

    def get_initial_state(self):
        return SimpleState(0)

    def get_legal_moves(self, state, role):
        if state.step >= 5:
            return []
        return ["left", "right", "up", "down"]

    def get_next_state(self, state, joint_move):
        return SimpleState(state.step + 1)

    def is_terminal(self, state):
        return state.step >= 5

    def get_goal(self, state, role):
        return 100 if self.is_terminal(state) else 0


def simple_sm_factory(rules: str) -> SimpleStateMachine:
    # In a real implementation, parse `rules` (a GDL string) here.
    print(f"[factory] Building StateMachine from {len(rules)} chars of GDL.")
    return SimpleStateMachine()


# ---------------------------------------------------------------------------
# Custom player
# ---------------------------------------------------------------------------

class MyPlayer(GGPPlayer):
    """
    A custom player that:
    - Logs the start and stop of each match.
    - Picks a random legal move (demonstrating how to use the StateMachine).
    """

    def setup(self, context: MatchContext, clock: Clock) -> None:
        """Called once after the StateMachine is initialised."""
        roles = self.sm.get_roles()
        print(
            f"[MyPlayer] Match {context.match_id!r} started. "
            f"I am role {context.role!r}. "
            f"Roles in game: {roles}. "
            f"Clock remaining: {clock.remaining():.1f}s."
        )

    def select_move(self, context: MatchContext, clock: Clock) -> str:
        """Choose a random legal move."""
        moves = self.sm.get_legal_moves(context.state, context.role)
        chosen = random.choice(moves) if moves else "noop"
        print(
            f"[MyPlayer] Step {context.step}: "
            f"choosing {chosen!r} from {moves}. "
            f"State: {context.state}."
        )
        return chosen

    def teardown(self, context: MatchContext, last_moves) -> None:
        """Called when the match ends (stop or abort)."""
        if self.sm and self.sm.is_terminal(context.state):
            goal = self.sm.get_goal(context.state, context.role)
            print(f"[MyPlayer] Match over. Final goal: {goal}.")
        else:
            print("[MyPlayer] Match aborted or state unknown.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    player = MyPlayer(state_machine_factory=simple_sm_factory)
    server = GGPServer(player, host="0.0.0.0", port=9147)
    server.start()
