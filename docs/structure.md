# Project Structure

```
pyggp/
├── ggp/
│   ├── __init__.py              Public API re-exports
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── messages.py          GCLMessage dataclasses
│   │   └── parser.py            S-expression tokeniser + GCL dispatcher
│   ├── player/
│   │   ├── __init__.py
│   │   ├── statemachine.py      StateMachineProtocol (typing.Protocol)
│   │   ├── base.py              GGPPlayer ABC + Clock + MatchContext
│   │   ├── legal.py             LegalPlayer
│   │   └── random.py            RandomPlayer
│   └── server/
│       ├── __init__.py
│       └── http_server.py       GGPServer + _GGPRequestHandler
├── tests/
│   ├── test_protocol.py         Parser + message tests
│   └── test_player_server.py    Player + HTTP integration tests
├── examples/
│   ├── custom_player.py         Write your own player from scratch
│   └── builtin_players.py       LegalPlayer + RandomPlayer offline demo
├── pyproject.toml
└── README.md
```