# GGP HTTP Protocol Reference

The Game Manager communicates with players via HTTP POST requests. All message bodies use the S-expression wire format with `Content-Type: text/acl`.

## Messages (Game Manager → Player)

### `(info)`
Check if the player is alive.

**Response:** `available` (or `busy` if in a match and unavailable)

---

### `(start <matchId> <role> <rules> <startclock> <playclock>)`

Begin a new match.

| Field | Type | Description |
|---|---|---|
| `matchId` | string | Unique match identifier |
| `role` | atom | The role this player will assume |
| `rules` | list | Complete GDL game description (S-expression list) |
| `startclock` | integer | Seconds to prepare (build SM, do metagaming) |
| `playclock` | integer | Seconds per move once play begins |

**Response:** `ready`  
Must reply within `startclock` seconds.

---

### `(play <matchId> <moves>)`

Request the player's next action.

| Field | Type | Description |
|---|---|---|
| `matchId` | string | Identifies the ongoing match |
| `moves` | list or `nil` | Joint move from the *previous* step, in role-declaration order. `nil` on the first step. |

**Response:** an action string, e.g. `mark(1,1)` or `noop`  
Must reply within `playclock` seconds. If the player does not reply in time, the Game Manager substitutes a random legal move.

---

### `(stop <matchId> <moves>)`

The match has reached a terminal state.

**Response:** `done`

---

### `(abort <matchId>)`

The match is terminated abnormally (not necessarily at a terminal state).

**Response:** `done`

## Example Session

```
GM → Player:  (start m23 white ((role white)(role black)...) 30 10)
Player → GM:  ready

GM → Player:  (play m23 nil)
Player → GM:  mark(1,1)

GM → Player:  (play m23 ((mark 1 1) noop))
Player → GM:  noop

GM → Player:  (play m23 (noop (mark 2 2)))
Player → GM:  mark(3,3)

GM → Player:  (stop m23 ((mark 3 3) noop))
Player → GM:  done
```