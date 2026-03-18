"""
Tests for GGPPlayer, LegalPlayer, RandomPlayer, and GGPServer (HTTP round-trip).

Uses a stub StateMachine — no GDL engine required.

Run with:  python3 -m unittest discover -s tests -v
"""

import time
import unittest
import urllib.request
from typing import Any

from ggp.player.base import Clock, GGPPlayer, MatchContext
from ggp.player.legal import LegalPlayer
from ggp.player.random import RandomPlayer
from ggp.protocol.messages import (
    AbortMessage,
    PlayMessage,
    StartMessage,
    StopMessage,
)
from ggp.server.http_server import GGPServer


# ---------------------------------------------------------------------------
# Stub StateMachine
# ---------------------------------------------------------------------------

class StubState:
    def __init__(self, step=0, terminal=False):
        self.step = step
        self.terminal = terminal
    def __repr__(self):
        return f"StubState(step={self.step}, terminal={self.terminal})"


class StubStateMachine:
    ROLES = ["white", "black"]
    LEGAL_MOVES = ["move_a", "move_b"]
    MAX_STEPS = 3

    def get_roles(self):
        return self.ROLES

    def get_initial_state(self):
        return StubState(0, False)

    def get_legal_moves(self, state, role):
        return [] if state.terminal else self.LEGAL_MOVES

    def get_next_state(self, state, joint_move):
        s = state.step + 1
        return StubState(s, s >= self.MAX_STEPS)

    def is_terminal(self, state):
        return state.terminal

    def get_goal(self, state, role):
        if not state.terminal:
            return 50
        return 100 if role == "white" else 0


def stub_factory(_rules):
    return StubStateMachine()


RULES = "((role white)(role black))"


# ---------------------------------------------------------------------------
# Clock tests
# ---------------------------------------------------------------------------

class TestClock(unittest.TestCase):

    def test_remaining_decreases(self):
        c = Clock(5.0, buffer=0.0)
        r1 = c.remaining()
        time.sleep(0.05)
        r2 = c.remaining()
        self.assertLess(r2, r1)

    def test_elapsed_increases(self):
        c = Clock(5.0, buffer=0.0)
        time.sleep(0.05)
        self.assertGreaterEqual(c.elapsed(), 0.04)

    def test_is_expired_false_initially(self):
        self.assertFalse(Clock(5.0, buffer=0.0).is_expired())

    def test_is_expired_true_after_deadline(self):
        c = Clock(0.1, buffer=0.0)
        time.sleep(0.15)
        self.assertTrue(c.is_expired())

    def test_remaining_never_negative(self):
        c = Clock(0.01, buffer=0.0)
        time.sleep(0.05)
        self.assertEqual(c.remaining(), 0.0)

    def test_invalid_seconds(self):
        with self.assertRaises(ValueError):
            Clock(-1.0)

    def test_repr(self):
        r = repr(Clock(10.0))
        self.assertIn("Clock", r)
        self.assertIn("10.0", r)


# ---------------------------------------------------------------------------
# GGPPlayer base class
# ---------------------------------------------------------------------------

class ConcretePlayer(GGPPlayer):
    def select_move(self, context, clock):
        return "move_a"


def _start_msg(match_id="m1", role="white"):
    return StartMessage(match_id, role, RULES, 10, 5)


class TestGGPPlayerBase(unittest.TestCase):

    def setUp(self):
        self.player = ConcretePlayer(state_machine_factory=stub_factory)

    def test_on_info_returns_available(self):
        self.assertEqual(self.player.on_info(), "available")

    def test_on_start_sets_context(self):
        self.player.on_start(_start_msg(), Clock(10))
        ctx = self.player.context
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.role, "white")
        self.assertEqual(ctx.match_id, "m1")

    def test_on_start_initialises_state(self):
        self.player.on_start(_start_msg(), Clock(10))
        self.assertIsInstance(self.player.context.state, StubState)
        self.assertEqual(self.player.context.state.step, 0)

    def test_on_start_returns_ready(self):
        result = self.player.on_start(_start_msg(), Clock(10))
        self.assertEqual(result, "ready")

    def test_on_play_advances_step(self):
        self.player.on_start(_start_msg(), Clock(10))
        self.player.on_play(PlayMessage("m1", None), Clock(5))
        self.assertEqual(self.player.context.step, 1)

    def test_on_play_advances_state_with_joint_move(self):
        self.player.on_start(_start_msg(), Clock(10))
        self.player.on_play(PlayMessage("m1", ["move_a", "move_b"]), Clock(5))
        self.assertEqual(self.player.context.state.step, 1)

    def test_on_play_nil_does_not_advance_state(self):
        self.player.on_start(_start_msg(), Clock(10))
        self.player.on_play(PlayMessage("m1", None), Clock(5))
        # moves=None → state not advanced
        self.assertEqual(self.player.context.state.step, 0)

    def test_on_stop_clears_context(self):
        self.player.on_start(_start_msg(), Clock(10))
        self.player.on_stop(StopMessage("m1", None))
        self.assertIsNone(self.player.context)

    def test_on_stop_returns_done(self):
        self.player.on_start(_start_msg(), Clock(10))
        self.assertEqual(self.player.on_stop(StopMessage("m1", None)), "done")

    def test_on_abort_clears_context(self):
        self.player.on_start(_start_msg(), Clock(10))
        self.player.on_abort(AbortMessage("m1"))
        self.assertIsNone(self.player.context)

    def test_on_play_without_start_raises(self):
        p = ConcretePlayer(state_machine_factory=stub_factory)
        with self.assertRaises(RuntimeError):
            p.on_play(PlayMessage("m1", None), Clock(5))

    def test_teardown_called_on_stop(self):
        calls = []

        class TrackingPlayer(GGPPlayer):
            def select_move(self, ctx, clock):
                return "move_a"
            def teardown(self, ctx, moves):
                calls.append((ctx.match_id, moves))

        p = TrackingPlayer(state_machine_factory=stub_factory)
        p.on_start(_start_msg(), Clock(10))
        p.on_stop(StopMessage("m1", ["move_a", "move_b"]))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ("m1", ["move_a", "move_b"]))


# ---------------------------------------------------------------------------
# LegalPlayer
# ---------------------------------------------------------------------------

class TestLegalPlayer(unittest.TestCase):

    def _started(self):
        p = LegalPlayer(state_machine_factory=stub_factory)
        p.on_start(_start_msg(), Clock(10))
        return p

    def test_returns_first_legal_move(self):
        p = self._started()
        self.assertEqual(p.select_move(p.context, Clock(5)), "move_a")

    def test_deterministic(self):
        p = self._started()
        a1 = p.select_move(p.context, Clock(5))
        a2 = p.select_move(p.context, Clock(5))
        self.assertEqual(a1, a2)

    def test_fallback_set_after_setup(self):
        p = self._started()
        self.assertEqual(p._fallback_move, "move_a")

    def test_full_game_sequence(self):
        p = LegalPlayer(state_machine_factory=stub_factory)
        p.on_start(_start_msg(), Clock(10))
        a1 = p.on_play(PlayMessage("m1", None), Clock(5))
        self.assertIn(a1, StubStateMachine.LEGAL_MOVES)
        a2 = p.on_play(PlayMessage("m1", ["move_a", "move_b"]), Clock(5))
        self.assertIn(a2, StubStateMachine.LEGAL_MOVES)
        self.assertEqual(p.on_stop(StopMessage("m1", None)), "done")


# ---------------------------------------------------------------------------
# RandomPlayer
# ---------------------------------------------------------------------------

class TestRandomPlayer(unittest.TestCase):

    def _started(self, seed=42):
        p = RandomPlayer(state_machine_factory=stub_factory, seed=seed)
        p.on_start(_start_msg(), Clock(10))
        return p

    def test_returns_legal_move(self):
        p = self._started()
        self.assertIn(p.select_move(p.context, Clock(5)), StubStateMachine.LEGAL_MOVES)

    def test_seeded_reproducibility(self):
        moves1 = [self._started(seed=0).select_move(self._started(seed=0).context, Clock(5)) for _ in range(10)]
        p1 = RandomPlayer(state_machine_factory=stub_factory, seed=0)
        p2 = RandomPlayer(state_machine_factory=stub_factory, seed=0)
        p1.on_start(_start_msg(), Clock(10))
        p2.on_start(_start_msg(), Clock(10))
        seq1 = [p1.select_move(p1.context, Clock(5)) for _ in range(20)]
        seq2 = [p2.select_move(p2.context, Clock(5)) for _ in range(20)]
        self.assertEqual(seq1, seq2)

    def test_fallback_set_after_setup(self):
        p = self._started()
        self.assertIn(p._fallback_move, StubStateMachine.LEGAL_MOVES)


# ---------------------------------------------------------------------------
# GGPServer HTTP integration
# ---------------------------------------------------------------------------

def _post(port, body):
    url = f"http://127.0.0.1:{port}/"
    data = body.encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "text/acl", "Content-Length": str(len(data))},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8")


class TestGGPServerHTTP(unittest.TestCase):

    PORT = 19147

    @classmethod
    def setUpClass(cls):
        player = LegalPlayer(state_machine_factory=stub_factory)
        cls.server = GGPServer(player, host="127.0.0.1", port=cls.PORT, clock_buffer=0.05)
        cls.server.start_background()
        time.sleep(0.15)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def _post(self, body):
        return _post(self.PORT, body)

    def test_info(self):
        r = self._post("(info)")
        self.assertIn(r, ("available", "ready", "busy"))

    def test_start_returns_ready(self):
        r = self._post(f"(start m1 white {RULES} 10 5)")
        self.assertEqual(r, "ready")

    def test_play_after_start(self):
        self._post(f"(start m2 white {RULES} 10 5)")
        r = self._post("(play m2 nil)")
        self.assertIn(r, StubStateMachine.LEGAL_MOVES)

    def test_stop_returns_done(self):
        self._post(f"(start m3 white {RULES} 10 5)")
        self._post("(play m3 nil)")
        r = self._post("(stop m3 (move_a move_b))")
        self.assertEqual(r, "done")

    def test_abort_returns_done(self):
        self._post(f"(start m4 white {RULES} 10 5)")
        r = self._post("(abort m4)")
        self.assertEqual(r, "done")

    def test_full_match_sequence(self):
        self._post(f"(start m5 white {RULES} 10 5)")
        r1 = self._post("(play m5 nil)")
        self.assertIn(r1, StubStateMachine.LEGAL_MOVES)
        r2 = self._post("(play m5 ((move_a move_b)))")
        self.assertIn(r2, StubStateMachine.LEGAL_MOVES)
        done = self._post("(stop m5 ((move_a move_b)))")
        self.assertEqual(done, "done")


if __name__ == "__main__":
    unittest.main()
