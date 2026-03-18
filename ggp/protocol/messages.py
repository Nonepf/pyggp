"""
GGP Communication Language (GCL) message definitions.

The HTTP-based GGP protocol defines five message types exchanged between
the Game Manager and players:

    (info)
    (start <matchId> <role> <rules> <startclock> <playclock>)
    (play  <matchId> <moves>)
    (stop  <matchId> <moves>)
    (abort <matchId>)

References:
    - Stanford GGP Book, Chapter 3: Game Management
    - http://ggp.stanford.edu
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


# ---------------------------------------------------------------------------
# Base type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GCLMessage:
    """Abstract base for all GCL messages."""

    @property
    def type(self) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete message types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InfoMessage(GCLMessage):
    """
    Sent by the Game Manager to check if the player is alive.

    Expected player response: "available" or "busy"
    (Some implementations also accept the older "ready".)

    Wire format: (info)
    """

    @property
    def type(self) -> str:
        return "info"

    def __repr__(self) -> str:
        return "InfoMessage()"


@dataclass(frozen=True)
class StartMessage(GCLMessage):
    """
    Sent by the Game Manager to initialise a new match.

    Attributes:
        match_id:    Unique identifier for this match (alphanumeric string).
        role:        The role this player will assume in the game.
        rules:       Complete GDL description of the game, as a raw string
                     (the original S-expression list of sentences).
        startclock:  Seconds the player has to prepare before play begins.
        playclock:   Seconds allowed per move once play begins.

    Expected player response: "ready"

    Wire format:
        (start <matchId> <role> <rules> <startclock> <playclock>)
    """

    match_id: str
    role: str
    rules: str          # Raw GDL text; pass to your StateMachine.
    startclock: int
    playclock: int

    @property
    def type(self) -> str:
        return "start"

    def __repr__(self) -> str:
        rule_preview = self.rules[:60].replace("\n", " ")
        if len(self.rules) > 60:
            rule_preview += "..."
        return (
            f"StartMessage(match_id={self.match_id!r}, role={self.role!r}, "
            f"rules='{rule_preview}', startclock={self.startclock}, "
            f"playclock={self.playclock})"
        )


@dataclass(frozen=True)
class PlayMessage(GCLMessage):
    """
    Sent by the Game Manager to request the player's next move.

    Attributes:
        match_id:  Identifies the ongoing match.
        moves:     The joint move from the *previous* step, as a list of
                   action strings ordered by role declaration order.
                   On the very first step this is None (wire value: nil).

    Expected player response: the player's chosen action string.

    Wire format:
        (play <matchId> <moves>)
        (play <matchId> nil)          ; first step

    Note on joint moves:
        moves is a list aligned with the role order declared in the GDL.
        For a two-player game with roles [white, black]:
            moves == ["mark(1,1)", "noop"]
        means white played mark(1,1) and black played noop.
    """

    match_id: str
    moves: list[str] | None = field(default=None)

    @property
    def type(self) -> str:
        return "play"

    @property
    def is_first_move(self) -> bool:
        """True when this is the very first play request (no prior moves)."""
        return self.moves is None

    def __repr__(self) -> str:
        return f"PlayMessage(match_id={self.match_id!r}, moves={self.moves!r})"


@dataclass(frozen=True)
class StopMessage(GCLMessage):
    """
    Sent by the Game Manager when the match has reached a terminal state.

    Attributes:
        match_id:  Identifies the match that has ended.
        moves:     The final joint move that caused termination.

    Expected player response: "done"

    Wire format:
        (stop <matchId> <moves>)
    """

    match_id: str
    moves: list[str] | None = field(default=None)

    @property
    def type(self) -> str:
        return "stop"

    def __repr__(self) -> str:
        return f"StopMessage(match_id={self.match_id!r}, moves={self.moves!r})"


@dataclass(frozen=True)
class AbortMessage(GCLMessage):
    """
    Sent by the Game Manager to terminate a match abnormally.

    The match may not be in a terminal state. Players should clean up
    any match-specific resources.

    Attributes:
        match_id:  Identifies the match being aborted.

    Expected player response: "done"

    Wire format:
        (abort <matchId>)
    """

    match_id: str

    @property
    def type(self) -> str:
        return "abort"

    def __repr__(self) -> str:
        return f"AbortMessage(match_id={self.match_id!r})"


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

AnyGCLMessage = Union[InfoMessage, StartMessage, PlayMessage, StopMessage, AbortMessage]
