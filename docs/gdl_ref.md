# GDL Reference

Game Description Language (GDL) is the formal language GGP uses to describe games. It is a logic programming language (similar to Datalog/Prolog) with special reserved keywords for game-specific concepts.

This section is a practical guide. For the full formal specification see the [Stanford GDL spec](http://ggp.stanford.edu/readings/gdl_spec.pdf).

---

## Syntax Basics

GDL uses **prefix S-expression** (Lisp-style) syntax. All expressions are parenthesised lists:

```
(keyword arg1 arg2 ...)
```

**Atoms (constants)** begin with a lowercase letter or digit:

```
white   black   cell   1   2   3   noop   b   x   o
```

**Variables** begin with `?`:

```
?role   ?x   ?y   ?w   ?player
```

**Compound terms** (functors) are also S-expressions:

```
(cell 1 2 b)      ; cell(1, 2, b) in traditional notation
(mark 1 1)        ; mark(1, 1)
(control white)   ; control(white)
```

**Rules** use `<=` (read: "if"):

```
(<= head body1 body2 ...)
```

This means: `head` is true **if** `body1` and `body2` and … are all true.

**Negation** uses `not`:

```
(not (true (control black)))   ; "control(black) is not true"
```

**Comments** (in some implementations):

```
; This is a comment
```

---

## Reserved Keywords

| Keyword | Arity | Meaning |
|---|---|---|
| `role` | 1 | Declares a player role |
| `base` | 1 | Declares a base proposition (all possible state facts) |
| `input` | 2 | Declares a feasible action for a role |
| `init` | 1 | A proposition true in the initial state |
| `true` | 1 | A proposition true in the **current** state (input relation) |
| `does` | 2 | The action a role performs in the current step (input relation) |
| `next` | 1 | A proposition true in the **next** state (output relation) |
| `legal` | 2 | An action is legal for a role in the current state |
| `goal` | 2 | The goal value (0–100) for a role in the current state |
| `terminal` | 0 | The current state is terminal (game over) |
| `distinct` | 2 | Built-in: two terms are not equal |

**Input relations** (`true`, `does`) may only appear in rule bodies.  
**Output relations** (`next`, `legal`, `goal`, `terminal`) are defined by the rules.

---

## A Complete Example — Tic-Tac-Toe

Below is the full GDL description of Tic-Tac-Toe. Read it top-to-bottom.

```lisp
;;; ─── Roles ───────────────────────────────────────────────────────────────
;;; Two players: white (plays x) and black (plays o).

(role white)
(role black)

;;; ─── Base propositions ───────────────────────────────────────────────────
;;; Declares every proposition that can ever be true in any state.
;;; cell(row, col, mark): the cell at (row,col) contains mark (x, o, or b).
;;; control(role): it is role's turn to move.

(base (cell ?m ?n x))    ; for all rows ?m and columns ?n
(base (cell ?m ?n o))
(base (cell ?m ?n b))
(base (control white))
(base (control black))

;;; ─── Inputs (feasible actions) ───────────────────────────────────────────
;;; Every role can potentially mark any cell, or do nothing (noop).

(input ?r (mark ?m ?n))  ; for all roles ?r, rows ?m, columns ?n
(input ?r noop)

;;; ─── Helper facts ─────────────────────────────────────────────────────────

(index 1) (index 2) (index 3)

;;; ─── Initial state ────────────────────────────────────────────────────────
;;; All 9 cells are blank; white moves first.

(<= (init (cell ?m ?n b)) (index ?m) (index ?n))
(init (control white))

;;; ─── Legality ─────────────────────────────────────────────────────────────
;;; White may mark a blank cell when it has control.
;;; Otherwise it must play noop.

(<= (legal ?w (mark ?m ?n))
    (true (cell ?m ?n b))
    (true (control ?w)))

(<= (legal white noop)
    (true (control black)))

(<= (legal black noop)
    (true (control white)))

;;; ─── Next state (transition rules) ───────────────────────────────────────
;;; If white marks cell (m,n) and it was blank, it becomes x.

(<= (next (cell ?m ?n x))
    (does white (mark ?m ?n))
    (true (cell ?m ?n b)))

;;; If black marks cell (m,n) and it was blank, it becomes o.

(<= (next (cell ?m ?n o))
    (does black (mark ?m ?n))
    (true (cell ?m ?n b)))

;;; Any cell that already has a mark keeps it (frame axiom).

(<= (next (cell ?m ?n ?w))
    (true (cell ?m ?n ?w))
    (distinct ?w b))

;;; A blank cell stays blank if no one marks it (frame axiom).
;;; (A cell that is overwritten is handled by the rules above.)

(<= (next (cell ?m ?n b))
    (does ?w (mark ?j ?k))
    (true (cell ?m ?n b))
    (distinct ?m ?j))

(<= (next (cell ?m ?n b))
    (does ?w (mark ?j ?k))
    (true (cell ?m ?n b))
    (distinct ?n ?k))

;;; Control alternates each turn.

(<= (next (control white)) (true (control black)))
(<= (next (control black)) (true (control white)))

;;; ─── Goal values ──────────────────────────────────────────────────────────
;;; A player gets 100 if it has a line and the opponent does not.
;;; Draw (no lines): 50. Opponent wins: 0.

(<= (goal white 100) (line x) (not (line o)))
(<= (goal white  50) (not (line x)) (not (line o)))
(<= (goal white   0) (not (line x)) (line o))

(<= (goal black 100) (not (line x)) (line o))
(<= (goal black  50) (not (line x)) (not (line o)))
(<= (goal black   0) (line x) (not (line o)))

;;; ─── Terminal condition ───────────────────────────────────────────────────

(<= terminal (line x))
(<= terminal (line o))
(<= terminal (not open))

(<= open (true (cell ?m ?n b)))  ; game is open if any blank cell exists

;;; ─── Supporting relations ─────────────────────────────────────────────────
;;; A "line" means three of the same mark in a row, column, or diagonal.

(<= (line ?w) (row ?m ?w))
(<= (line ?w) (column ?n ?w))
(<= (line ?w) (diagonal ?w))

(<= (row ?m ?w)
    (true (cell ?m 1 ?w))
    (true (cell ?m 2 ?w))
    (true (cell ?m 3 ?w)))

(<= (column ?n ?w)
    (true (cell 1 ?n ?w))
    (true (cell 2 ?n ?w))
    (true (cell 3 ?n ?w)))

(<= (diagonal ?w)
    (true (cell 1 1 ?w))
    (true (cell 2 2 ?w))
    (true (cell 3 3 ?w)))

(<= (diagonal ?w)
    (true (cell 1 3 ?w))
    (true (cell 2 2 ?w))
    (true (cell 3 1 ?w)))
```

---

## Rules Deep-Dive

### How `true` and `does` work

The game engine evaluates each GDL rule against two **input datasets**:

- **`true(p)`** — the set of base propositions that hold in the *current* state.
- **`does(role, action)`** — the joint move selected by all players this step.

These are **inputs**: they may appear only in rule bodies, never in heads.

The engine derives all **output** relations by forward chaining over the rules:

```
Inputs (true, does)  +  Rules  →  legal, next, goal, terminal
```

### The frame problem

GDL has no "default persistence". You must explicitly state that facts carry over.
That is what the `(next (cell ?m ?n ?w)) :- (true (cell ?m ?n ?w)) & distinct(?w, b)` rules do — they say a marked cell stays marked. This is called a **frame axiom**.

### Stratified negation

Negation (`not`) is allowed, but **never in a recursive cycle**. This ensures reasoning is always decidable.

✅ OK — `not` on a base relation:
```lisp
(<= terminal (not open))
```

❌ Forbidden — `not` inside its own recursive definition:
```lisp
(<= (p ?x) (not (p ?x)))   ; illegal: p recursively negates itself
```

### `distinct` is built-in

`(distinct ?x ?y)` succeeds when `?x` and `?y` are not the same term. It cannot be defined with rules.

```lisp
(<= (next (cell ?m ?n b))
    (does ?w (mark ?j ?k))
    (true (cell ?m ?n b))
    (distinct ?m ?j))       ; only keep blank if row index differs
```

### Variables are universally quantified

A rule like:

```lisp
(<= (legal ?w (mark ?m ?n))
    (true (cell ?m ?n b))
    (true (control ?w)))
```

means: **for every** `?w`, `?m`, `?n` — if the cell is blank and `?w` has control, then `?w` may mark it.

---

## GDL Constraints

A valid GDL game description must be:

| Property | Meaning |
|---|---|
| **Safe** | Every variable in a rule head or negated body also appears in a positive body literal |
| **Stratified** | No negation appears in a recursive dependency cycle |
| **Terminating** | All legal-move sequences eventually reach a terminal state |
| **Playable** | Every role has at least one legal move in every non-terminal state |
| **Weakly winnable** | For every role, there exists *some* joint sequence of actions that gives it a maximal goal value |

Games used in GGP competitions are always **well-formed** (terminating + playable + weakly winnable).