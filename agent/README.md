# agent/ - Nemotron planner for the FPGA quantum emulator

Natural language -> circuit JSON -> **deterministic validator** -> assembly -> backend -> compare -> explanation.
The LLM only proposes; `validator.py` decides what may run; backends only accept validator-issued `circuit_id`s.

```
pip install -r agent/requirements.txt
export NEBIUS_API_KEY=...                       # Token Factory key
python -m agent.list_models                     # pick Nemotron IDs (check function-calling support in the docs)
export NEBIUS_PLANNER_MODEL=<reasoning model id>
export NEBIUS_FAST_MODEL=<small model id>

python -m agent.cli "make a Bell state"                    # LLM mode
python -m agent.cli --circuit agent/examples/grover2.json  # offline, no LLM
python -m unittest discover -s agent/tests -t .            # offline tests (no network)
```

| File | Role |
| --- | --- |
| `gates.py` | hardware limits and opcodes (single source of truth) |
| `validator.py` | deterministic checks, no LLM |
| `compiler.py` | circuit JSON -> assembly / 16-bit words |
| `simulate.py` | NumPy float reference for quick checks |
| `backends.py` | `sim-float` works; `ref-fixed`, `ghdl`, `board` are stubs (TODO) |
| `tools.py` | the 5 function-calling tools + schemas |
| `agent.py` | planner loop, max 3 repairs, execute + compare + explain |
| `cli.py` / `list_models.py` | entry points |
