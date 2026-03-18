"""
StateMachine protocol (structural interface).

This module defines the contract that any game state machine must fulfil
in order to be used with GGPPlayer subclasses like LegalPlayer and
RandomPlayer.

By using typing.Protocol (PEP 544), we achieve structural subtyping:
any class that implements these methods is automatically compatible —
no explicit inheritance required. This keeps the player framework
fully decoupled from any particular GDL reasoner or game engine.

Implementing a StateMachine
---------------------------
Create a class with the following methods:

    class MyStateMachine:
        def __init__(self, gdl_rules: str): ...

        def get_roles(self) -> list[str]: ...
        def get_initial_state(self) -> object: ...
        def get_legal_moves(self, state, role: str) -> list[str]: ...
        def get_next_state(self, state, joint_move: dict[str, str]) -> object: ...
        def is_terminal(self, state) -> bool: ...
        def get_goal(self, state, role: str) -> int: ...

Then pass an instance to your player:

    sm = MyStateMachine(rules)
    player = MyPlayer(state_machine_factory=lambda rules: MyStateMachine(rules))

State representation
--------------------
States are opaque objects from the framework's perspective. Your
StateMachine implementation can use any representation internally
(frozenset of atoms, dict, custom object, etc.). The framework only
passes states back to the same StateMachine that produced them.

Joint moves
-----------
A joint move is a dict mapping each role to its chosen action:
    {"white": "mark(1,1)", "black": "noop"}
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StateMachineProtocol(Protocol):
    """
    Structural protocol for GGP state machines.

    Any object satisfying this interface can be used as the game engine
    inside a GGPPlayer. No inheritance from this class is needed.
    """

    def get_roles(self) -> list[str]:
        """
        Return the list of role names in declaration order (as in the GDL).

        Example:
            ["white", "black"]
        """
        ...

    def get_initial_state(self) -> Any:
        """
        Return the initial game state.

        The returned object is opaque to the framework; it will be passed
        back to other methods of this same StateMachine.
        """
        ...

    def get_legal_moves(self, state: Any, role: str) -> list[str]:
        """
        Return all legal action strings for *role* in *state*.

        The returned strings should match the canonical GDL action
        representation, e.g. "mark(1,1)" or "noop".

        Guarantees (per GDL well-formedness):
            - At least one action is always returned for non-terminal states.
            - The list may be empty only if the state is terminal.
        """
        ...

    def get_next_state(self, state: Any, joint_move: dict[str, str]) -> Any:
        """
        Apply *joint_move* to *state* and return the resulting state.

        Args:
            state:       Current game state.
            joint_move:  Mapping of role → chosen action string.
                         Must contain an entry for every role.

        Returns:
            The next game state (a new object; states are immutable).
        """
        ...

    def is_terminal(self, state: Any) -> bool:
        """Return True if *state* is a terminal (game-over) state."""
        ...

    def get_goal(self, state: Any, role: str) -> int:
        """
        Return the goal value (0–100) for *role* in *state*.

        Meaningful values are typically only queried at terminal states,
        but the GDL spec allows goal to be defined for any state.
        """
        ...
