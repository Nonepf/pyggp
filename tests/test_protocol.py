"""
Tests for ggp.protocol.parser and ggp.protocol.messages.

Run with:  python3 -m unittest discover -s tests -v
"""

import unittest

from ggp.protocol.messages import (
    AbortMessage,
    InfoMessage,
    PlayMessage,
    StartMessage,
    StopMessage,
)
from ggp.protocol.parser import (
    _sexpr_to_action,
    parse_gcl_message,
    parse_sexpr,
    unparse_sexpr,
)


class TestParseSexpr(unittest.TestCase):

    def test_atom(self):
        self.assertEqual(parse_sexpr("hello"), "hello")

    def test_simple_list(self):
        self.assertEqual(parse_sexpr("(info)"), ["info"])

    def test_nested(self):
        self.assertEqual(parse_sexpr("(play m1 nil)"), ["play", "m1", "nil"])

    def test_deeply_nested(self):
        result = parse_sexpr("(play m1 ((mark 1 1) noop))")
        self.assertEqual(result, ["play", "m1", [["mark", "1", "1"], "noop"]])

    def test_whitespace_tolerance(self):
        self.assertEqual(parse_sexpr("  ( info )  "), ["info"])

    def test_unparse_roundtrip_simple(self):
        original = "(play m1 nil)"
        self.assertEqual(unparse_sexpr(parse_sexpr(original)), original)

    def test_unparse_roundtrip_nested(self):
        original = "(play m1 ((mark 1 1) noop))"
        self.assertEqual(unparse_sexpr(parse_sexpr(original)), original)

    def test_missing_close_paren(self):
        with self.assertRaises(ValueError):
            parse_sexpr("(play m1 nil")

    def test_unexpected_close_paren(self):
        # A lone ')' with no matching '(' is an unexpected close paren.
        with self.assertRaises(ValueError):
            parse_sexpr(")")

    def test_empty_string(self):
        with self.assertRaises((ValueError, IndexError)):
            parse_sexpr("")


class TestSexprToAction(unittest.TestCase):

    def test_atom(self):
        self.assertEqual(_sexpr_to_action("noop"), "noop")

    def test_list_single(self):
        self.assertEqual(_sexpr_to_action(["noop"]), "noop")

    def test_compound(self):
        self.assertEqual(_sexpr_to_action(["mark", "1", "1"]), "mark(1, 1)")

    def test_nested_compound(self):
        self.assertEqual(_sexpr_to_action(["f", ["g", "x"], "y"]), "f(g(x), y)")


TICTACTOE_RULES = (
    "((role white)(role black)"
    "(init (cell 1 1 b))(init (cell 1 2 b))(init (control white)))"
)


class TestInfoMessage(unittest.TestCase):

    def test_basic(self):
        msg = parse_gcl_message("(info)")
        self.assertIsInstance(msg, InfoMessage)
        self.assertEqual(msg.type, "info")

    def test_case_insensitive(self):
        msg = parse_gcl_message("(INFO)")
        self.assertIsInstance(msg, InfoMessage)

    def test_too_many_args(self):
        with self.assertRaises(ValueError):
            parse_gcl_message("(info extra)")


class TestStartMessage(unittest.TestCase):

    def _make(self, match_id="match1", role="white", sc=60, pc=10):
        return parse_gcl_message(
            f"(start {match_id} {role} {TICTACTOE_RULES} {sc} {pc})"
        )

    def test_basic_fields(self):
        msg = self._make()
        self.assertIsInstance(msg, StartMessage)
        self.assertEqual(msg.match_id, "match1")
        self.assertEqual(msg.role, "white")
        self.assertEqual(msg.startclock, 60)
        self.assertEqual(msg.playclock, 10)

    def test_rules_preserved(self):
        msg = self._make()
        self.assertIn("role", msg.rules)

    def test_type_property(self):
        self.assertEqual(self._make().type, "start")

    def test_missing_arg(self):
        with self.assertRaises(ValueError):
            parse_gcl_message("(start match1 white)")

    def test_repr_does_not_crash(self):
        self.assertIn("StartMessage", repr(self._make()))


class TestPlayMessage(unittest.TestCase):

    def test_nil_first_move(self):
        msg = parse_gcl_message("(play match1 nil)")
        self.assertIsInstance(msg, PlayMessage)
        self.assertIsNone(msg.moves)
        self.assertTrue(msg.is_first_move)

    def test_joint_move_two_players(self):
        msg = parse_gcl_message("(play match1 ((mark 1 1) noop))")
        self.assertIsNotNone(msg.moves)
        self.assertEqual(len(msg.moves), 2)
        self.assertEqual(msg.moves[0], "mark(1, 1)")
        self.assertEqual(msg.moves[1], "noop")

    def test_joint_move_single_player(self):
        msg = parse_gcl_message("(play match1 (right))")
        self.assertEqual(msg.moves, ["right"])

    def test_is_first_move_false(self):
        msg = parse_gcl_message("(play match1 ((mark 1 1) noop))")
        self.assertFalse(msg.is_first_move)

    def test_type_property(self):
        self.assertEqual(parse_gcl_message("(play m1 nil)").type, "play")

    def test_nil_case_insensitive(self):
        msg = parse_gcl_message("(play match1 NIL)")
        self.assertIsNone(msg.moves)


class TestStopMessage(unittest.TestCase):

    def test_basic(self):
        msg = parse_gcl_message("(stop match1 ((mark 3 3) noop))")
        self.assertIsInstance(msg, StopMessage)
        self.assertEqual(msg.match_id, "match1")
        self.assertEqual(msg.moves, ["mark(3, 3)", "noop"])

    def test_type_property(self):
        self.assertEqual(parse_gcl_message("(stop m1 nil)").type, "stop")


class TestAbortMessage(unittest.TestCase):

    def test_basic(self):
        msg = parse_gcl_message("(abort match1)")
        self.assertIsInstance(msg, AbortMessage)
        self.assertEqual(msg.match_id, "match1")
        self.assertEqual(msg.type, "abort")

    def test_too_many_args(self):
        with self.assertRaises(ValueError):
            parse_gcl_message("(abort match1 extra)")


class TestParseGCLEdgeCases(unittest.TestCase):

    def test_empty_string(self):
        with self.assertRaises(ValueError):
            parse_gcl_message("")

    def test_unknown_keyword(self):
        with self.assertRaises(ValueError):
            parse_gcl_message("(frobnicate foo bar)")

    def test_not_a_list(self):
        with self.assertRaises(ValueError):
            parse_gcl_message("info")


if __name__ == "__main__":
    unittest.main()
