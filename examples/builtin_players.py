"""
examples/builtin_players.py
===========================

Demonstrates using the built-in LegalPlayer and RandomPlayer with a
stub StateMachine, without starting a real HTTP server.

This is useful for offline testing and algorithm development.
"""

# -- path bootstrap: works whether or not the package is pip-installed -------
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# ---------------------------------------------------------------------------

from ggp import GGPServer, LegalPlayer, RandomPlayer
from ggp.player.base import Clock
from ggp.protocol.messages import PlayMessage, StartMessage, StopMessage


# ---------------------------------------------------------------------------
# Stub StateMachine: simplified Tic-Tac-Toe (no GDL engine needed)
# ---------------------------------------------------------------------------

class TicTacToeStub:
    """
    A minimal Tic-Tac-Toe state machine.

    State: (board_tuple, whose_turn)
    board is a 9-tuple of 'x', 'o', or 'b' (blank).
    Positions:  0 1 2
                3 4 5
                6 7 8
    """

    ROLES = ["white", "black"]

    def get_roles(self):
        return self.ROLES

    def get_initial_state(self):
        return (tuple(["b"] * 9), "white")

    def get_legal_moves(self, state, role):
        board, turn = state
        if self._winner(board) or "b" not in board:
            return []                        # terminal — no moves
        if role != turn:
            return ["noop"]                 # not your turn
        return [
            f"mark({i // 3 + 1},{i % 3 + 1})"
            for i, cell in enumerate(board)
            if cell == "b"
        ]

    def get_next_state(self, state, joint_move):
        board, turn = state
        board = list(board)
        action = joint_move.get(turn, "noop")
        if action != "noop" and action.startswith("mark("):
            inner = action[5:-1]            # "r,c"
            r, c = inner.split(",")
            idx = (int(r) - 1) * 3 + (int(c) - 1)
            if 0 <= idx < 9 and board[idx] == "b":
                board[idx] = "x" if turn == "white" else "o"
        next_turn = "black" if turn == "white" else "white"
        return (tuple(board), next_turn)

    def is_terminal(self, state):
        board, _ = state
        return bool(self._winner(board)) or "b" not in board

    def get_goal(self, state, role):
        board, _ = state
        winner = self._winner(board)
        if winner == "x":
            return 100 if role == "white" else 0
        if winner == "o":
            return 0 if role == "white" else 100
        return 50   # draw or non-terminal

    def _winner(self, board):
        lines = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
            (0, 3, 6), (1, 4, 7), (2, 5, 8),   # cols
            (0, 4, 8), (2, 4, 6),               # diagonals
        ]
        for a, b, c in lines:
            if board[a] == board[b] == board[c] != "b":
                return board[a]
        return None


def ttt_factory(_rules):
    return TicTacToeStub()


# ---------------------------------------------------------------------------
# Pretty-print the board
# ---------------------------------------------------------------------------

def print_board(board):
    symbols = {"x": " X ", "o": " O ", "b": " . "}
    print("  ┌───┬───┬───┐")
    for row in range(3):
        cells = "│".join(symbols[board[row * 3 + col]] for col in range(3))
        print(f"  │{cells}│")
        if row < 2:
            print("  ├───┼───┼───┤")
    print("  └───┴───┴───┘")
    print("    1   2   3  ")


# ---------------------------------------------------------------------------
# Offline simulation
# ---------------------------------------------------------------------------

def simulate_match(white_player, black_player, match_id="game"):
    """Run a full match between two players offline."""
    sm = TicTacToeStub()
    state = sm.get_initial_state()

    print(f"\n{'='*44}")
    print(f"  Match: {match_id}")
    print(f"  White: {white_player.__class__.__name__}")
    print(f"  Black: {black_player.__class__.__name__}")
    print(f"{'='*44}")

    # Start both players
    for player, role in [(white_player, "white"), (black_player, "black")]:
        player.on_start(
            StartMessage(match_id, role, "(role white)(role black)", 10, 5),
            Clock(10),
        )

    last_moves = None
    step = 0

    while not sm.is_terminal(state):
        step += 1
        board, turn = state

        # Ask both players for their moves
        white_action = white_player.on_play(
            PlayMessage(match_id, last_moves), Clock(5)
        )
        black_action = black_player.on_play(
            PlayMessage(match_id, last_moves), Clock(5)
        )

        # The player in control's move counts; the other plays noop
        if turn == "white":
            chosen = white_action
        else:
            chosen = black_action

        print(f"\n  Step {step}  ({turn.upper()}'s turn) → {chosen}")
        joint = {"white": white_action, "black": black_action}
        state = sm.get_next_state(state, joint)
        last_moves = [white_action, black_action]

        print_board(state[0])

    # Final result
    white_goal = sm.get_goal(state, "white")
    black_goal = sm.get_goal(state, "black")
    winner = (
        "WHITE wins! 🎉" if white_goal == 100 else
        "BLACK wins! 🎉" if black_goal == 100 else
        "Draw 🤝"
    )
    print(f"\n  Result: {winner}  (white={white_goal}, black={black_goal})")

    # Stop both players
    for player in (white_player, black_player):
        player.on_stop(StopMessage(match_id, last_moves))

    return white_goal, black_goal


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("\n" + "─" * 44)
    print("  GAME 1 — LegalPlayer (white) vs LegalPlayer (black)")
    print("─" * 44)
    simulate_match(
        white_player=LegalPlayer(state_machine_factory=ttt_factory),
        black_player=LegalPlayer(state_machine_factory=ttt_factory),
        match_id="legal_vs_legal",
    )

    print("\n" + "─" * 44)
    print("  GAME 2 — RandomPlayer (white) vs RandomPlayer (black)")
    print("─" * 44)
    simulate_match(
        white_player=RandomPlayer(state_machine_factory=ttt_factory, seed=42),
        black_player=RandomPlayer(state_machine_factory=ttt_factory, seed=7),
        match_id="random_vs_random",
    )

    print("\n" + "─" * 44)
    print("  GAME 3 — RandomPlayer (white) vs LegalPlayer (black)")
    print("─" * 44)
    simulate_match(
        white_player=RandomPlayer(state_machine_factory=ttt_factory, seed=99),
        black_player=LegalPlayer(state_machine_factory=ttt_factory),
        match_id="random_vs_legal",
    )

    print("\n[done]")
