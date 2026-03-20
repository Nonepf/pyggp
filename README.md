# pyggp

A lightweight, zero-dependency Python framework for building **General Game Playing (GGP)** players that communicate via the Stanford HTTP competition protocol.

> **What is GGP?** General Game Players are programs that accept a formal game description at runtime and play effectively without prior knowledge of the rules.

---

## Key Features

| What `pyggp` handles | What you implement |
| :--- | :--- |
| **Infrastructure**: HTTP server & request routing | **Rules**: `StateMachine` (GDL reasoner) |
| **Parsing**: GCL message to S-expressions | **Intelligence**: `select_move()` (search/heuristics) |
| **Safety**: Clock enforcement & timeout fallback | **Lifecycle**: Setup and teardown logic |

  * **Zero Runtime Dependencies**: Built entirely on the Python Standard Library.
  * **Modern Python**: Leverages Python 3.10+ features like `dataclasses` and structural subtyping.

---

## Quick Start

### 1\. Installation

```bash
git clone https://github.com/Nonepf/pyggp.git
cd pyggp
pip install -e .
```

### 2\. Create a Random Player

```python
import random
from ggp import GGPPlayer, GGPServer

class MyPlayer(GGPPlayer):
    def select_move(self, context, clock) -> str:
        # 'sm' is your StateMachine instance automatically managed by the framework
        moves = self.sm.get_legal_moves(context.state, context.role)
        return random.choice(moves)

# Start the server on the default GGP port
player = MyPlayer(state_machine_factory=my_sm_factory)
GGPServer(player, port=9147).start()
```

---

## Architecture & Core Concepts

`pyggp` bridges the gap between the low-level HTTP protocol and your high-level search logic.

```text
┌──────────────────────────┐      (start/play/stop)      ┌──────────────────────────┐
│     GGP Game Manager     │ ──────────────────────────▶ │   ggp.server.GGPServer   │
└──────────────────────────┘         HTTP POST           └────────────┬─────────────┘
                                                                      │
┌──────────────────────────┐           calls             ┌────────────▼─────────────┐
│   Your Search Logic      │ ◀────────────────────────── │   ggp.player.GGPPlayer   │
│  (e.g., MCTS, AlphaBeta) │     select_move(ctx, clk)   └────────────┬─────────────┘
└──────────────────────────┘                                          │ uses
                                                         ┌────────────▼─────────────┐
                                                         │   StateMachineProtocol   │
                                                         └──────────────────────────┘
```

### The State Machine (The Rules)

Your game engine must implement the `StateMachineProtocol`. No inheritance is required—just define these core methods:

  * `get_initial_state()` / `get_next_state(state, joint_move)`
  * `get_legal_moves(state, role)`
  * `is_terminal(state)` / `get_goal(state, role)`

### The Player (The Brain)

Subclass `GGPPlayer` to define your agent's behavior. The framework manages the match lifecycle:

  * `setup(context, clock)`: Called during the `start` phase for pre-computation.
  * `select_move(context, clock)`: **Required.** Return your move string before the clock expires.
  * `teardown(context, last_moves)`: Called when the match ends or aborts.

---

## Advanced Usage

### Precision Timing

`GGPServer` includes a `clock_buffer` (default: **0.2s**) to account for network latency and Python overhead. In your search loop, use the `clock` object for safe iterative deepening:

```python
def select_move(self, context, clock):
    best_move = self.sm.get_legal_moves(context.state, context.role)[0]
    for depth in range(1, 100):
        if clock.is_expired(): # Returns True if time (minus buffer) is up
            break
        best_move = self.heavy_search(context.state, depth)
    return best_move
```

### Testing with Built-in Baselines

Use included players to verify your state machine or test your search performance:

  * **`LegalPlayer`**: Always picks the first legal move. Great for smoke testing.
  * **`RandomPlayer`**: Picks moves uniformly at random.

### Manual Verification

You can simulate a Game Manager using `curl`:

```bash
# Check if player is available
curl -X POST http://localhost:9147/ -H "Content-Type: text/acl" -d "(info)"
```

---

## References

  * [Game Description Language (GDL) Guide](docs/gdl_ref.md)
  * [HTTP Protocol Specification](docs/http_ref.md)
  * [roject Structure](docs/structure.md)

-----

## License

MIT