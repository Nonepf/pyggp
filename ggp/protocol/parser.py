"""
GCL (GGP Communication Language) parser.

Parses the S-expression wire format used by the HTTP GGP protocol into
structured Python message objects.

GCL uses prefix (Lisp-style) S-expressions:

    (info)
    (start match1 white ((role white)(role black)...) 10 10)
    (play  match1 ((mark 1 1) noop))
    (play  match1 nil)
    (stop  match1 ((mark 3 3) noop))
    (abort match1)

This module handles two concerns:

1.  parse_sexpr / unparse_sexpr
    Low-level tokeniser and tree builder. Converts a raw string into a
    nested Python list structure (atoms become strings, lists become lists).

2.  parse_gcl_message
    High-level dispatcher. Takes a raw GCL string and returns the
    appropriate GCLMessage subclass.
"""

from __future__ import annotations

import re
from typing import Any

from ggp.protocol.messages import (
    AbortMessage,
    AnyGCLMessage,
    InfoMessage,
    PlayMessage,
    StartMessage,
    StopMessage,
)


# ---------------------------------------------------------------------------
# Low-level S-expression tokeniser
# ---------------------------------------------------------------------------

# Tokens: open paren, close paren, or a sequence of non-whitespace/paren chars.
_TOKEN_RE = re.compile(r'[()]|[^\s()]+')


def _tokenise(text: str) -> list[str]:
    """Split a GCL string into a flat list of tokens."""
    return _TOKEN_RE.findall(text)


def parse_sexpr(text: str) -> Any:
    """
    Parse a GCL S-expression string into a nested Python structure.

    Atoms  → str
    Lists  → list

    Examples:
        >>> parse_sexpr("(info)")
        ['info']
        >>> parse_sexpr("(play match1 nil)")
        ['play', 'match1', 'nil']
        >>> parse_sexpr("(play match1 ((mark 1 1) noop))")
        ['play', 'match1', [['mark', '1', '1'], 'noop']]
    """
    tokens = _tokenise(text.strip())
    result, pos = _parse_tokens(tokens, 0)
    return result


def _parse_tokens(tokens: list[str], pos: int) -> tuple[Any, int]:
    """Recursive descent parser over a flat token list."""
    if pos >= len(tokens):
        raise ValueError("Unexpected end of input while parsing S-expression.")

    token = tokens[pos]

    if token == "(":
        items: list[Any] = []
        pos += 1
        while pos < len(tokens) and tokens[pos] != ")":
            item, pos = _parse_tokens(tokens, pos)
            items.append(item)
        if pos >= len(tokens):
            raise ValueError("Missing closing parenthesis in S-expression.")
        return items, pos + 1  # consume ')'

    if token == ")":
        raise ValueError(f"Unexpected ')' at position {pos}.")

    # Plain atom
    return token, pos + 1


def unparse_sexpr(obj: Any) -> str:
    """
    Convert a nested Python list / string back into an S-expression string.

    Examples:
        >>> unparse_sexpr(['play', 'match1', 'nil'])
        '(play match1 nil)'
        >>> unparse_sexpr(['play', 'match1', [['mark', '1', '1'], 'noop']])
        '(play match1 ((mark 1 1) noop))'
    """
    if isinstance(obj, list):
        return "(" + " ".join(unparse_sexpr(item) for item in obj) + ")"
    return str(obj)


# ---------------------------------------------------------------------------
# Joint-move extraction helpers
# ---------------------------------------------------------------------------

def _extract_moves(raw: Any) -> list[str] | None:
    """
    Convert the moves argument of a play/stop message into a list of
    action strings, or None if the wire value was 'nil'.

    The moves argument is either:
        nil                   → None
        (<action1> <action2>) → ["action1_str", "action2_str"]

    Each action may itself be a compound S-expression, e.g. (mark 1 1).
    We unparse it back into a canonical string for downstream use.
    """
    if isinstance(raw, str) and raw.lower() == "nil":
        return None

    if isinstance(raw, list):
        result = []
        for item in raw:
            if isinstance(item, list):
                # Compound action like ['mark', '1', '1'] → "mark(1,1)"
                result.append(_sexpr_to_action(item))
            else:
                result.append(str(item))
        return result

    # Scalar non-nil (shouldn't appear in well-formed messages, but be lenient)
    return [str(raw)]


def _sexpr_to_action(expr: Any) -> str:
    """
    Convert a parsed action S-expression to a human-readable string.

    ['mark', '1', '1']  → 'mark(1,1)'
    'noop'              → 'noop'
    ['noop']            → 'noop'
    """
    if isinstance(expr, str):
        return expr
    if isinstance(expr, list):
        if len(expr) == 0:
            return ""
        if len(expr) == 1:
            return str(expr[0])
        head = expr[0]
        args = ", ".join(_sexpr_to_action(a) for a in expr[1:])
        return f"{head}({args})"
    return str(expr)


def _rules_to_str(raw: Any) -> str:
    """
    Re-serialise the rules argument of a start message as a string.

    The Game Manager sends the GDL ruleset as a list of S-expressions.
    We preserve the wire format (unparse back to a string) so that
    downstream StateMachine implementations can parse it themselves.
    """
    return unparse_sexpr(raw)


# ---------------------------------------------------------------------------
# High-level GCL message dispatcher
# ---------------------------------------------------------------------------

def parse_gcl_message(text: str) -> AnyGCLMessage:
    """
    Parse a raw GCL wire string into the appropriate GCLMessage subclass.

    Raises:
        ValueError: if the message is not a recognised GCL type or is
                    structurally malformed.

    Wire formats handled:
        (info)
        (start <matchId> <role> <rules> <startclock> <playclock>)
        (play  <matchId> <moves>)
        (stop  <matchId> <moves>)
        (abort <matchId>)
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty GCL message.")

    tree = parse_sexpr(text)

    if not isinstance(tree, list) or len(tree) == 0:
        raise ValueError(f"GCL message must be a non-empty list, got: {tree!r}")

    keyword = str(tree[0]).lower()

    # ------------------------------------------------------------------ info
    if keyword == "info":
        _expect_arity("info", tree, exact=1)
        return InfoMessage()

    # ----------------------------------------------------------------- start
    if keyword == "start":
        _expect_arity("start", tree, exact=6)
        _, match_id, role, rules_raw, startclock_raw, playclock_raw = tree
        return StartMessage(
            match_id=str(match_id),
            role=str(role),
            rules=_rules_to_str(rules_raw),
            startclock=int(startclock_raw),
            playclock=int(playclock_raw),
        )

    # ------------------------------------------------------------------ play
    if keyword == "play":
        _expect_arity("play", tree, exact=3)
        _, match_id, moves_raw = tree
        return PlayMessage(
            match_id=str(match_id),
            moves=_extract_moves(moves_raw),
        )

    # ------------------------------------------------------------------ stop
    if keyword == "stop":
        _expect_arity("stop", tree, exact=3)
        _, match_id, moves_raw = tree
        return StopMessage(
            match_id=str(match_id),
            moves=_extract_moves(moves_raw),
        )

    # ----------------------------------------------------------------- abort
    if keyword == "abort":
        _expect_arity("abort", tree, exact=2)
        _, match_id = tree
        return AbortMessage(match_id=str(match_id))

    raise ValueError(
        f"Unknown GCL message type: {keyword!r}. "
        "Expected one of: info, start, play, stop, abort."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expect_arity(name: str, tree: list, *, exact: int) -> None:
    if len(tree) != exact:
        raise ValueError(
            f"GCL '{name}' message expects {exact - 1} argument(s), "
            f"got {len(tree) - 1}: {tree!r}"
        )
