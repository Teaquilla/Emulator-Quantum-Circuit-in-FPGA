# agent/ - Nemotron planner for the FPGA quantum emulator

Natural language -> circuit JSON -> **deterministic validator** -> assembly -> backend -> compare -> explanation.
The LLM only proposes; `validator.py` decides what may run; backends only accept validator-issued `circuit_id`s.

```
`agent/` must sit next to `ref/` (the `ref-fixed` backend loads `ref/qsim.py`).

```
pip install -r agent/requirements.txt

# Option A: .env file in the repo root (see agent/.env.example; .env MUST be in .gitignore)
#   NEBIUS_API_KEY=...   NEBIUS_PLANNER_MODEL=...   NEBIUS_FAST_MODEL=...

# Option B, Linux / macOS (bash)
export NEBIUS_API_KEY=...
export NEBIUS_PLANNER_MODEL=<reasoning model id>
export NEBIUS_FAST_MODEL=<small model id>

# Option B, Windows cmd (no quotes, no spaces around "="; lasts for this window only)
set NEBIUS_API_KEY=...
set NEBIUS_PLANNER_MODEL=<reasoning model id>
set NEBIUS_FAST_MODEL=<small model id>

# Option B, Windows PowerShell
$env:NEBIUS_API_KEY="..."

python -m agent.list_models     # pick Nemotron IDs (check function-calling support in the docs)

python -m agent.cli "make a Bell state"                    # LLM mode
python -m agent.cli --circuit agent/examples/grover2.json  # offline, no LLM, uses ref-fixed
python -m unittest discover -s agent/tests -t .            # offline tests (no network)
```

| File | Role |
| --- | --- |
| `gates.py` | hardware limits and opcodes (single source of truth) |
| `validator.py` | deterministic checks, no LLM |
| `compiler.py` | circuit JSON -> assembly / 16-bit words |
| `simulate.py` | NumPy float reference for quick checks |
| `backends.py` | `ref-fixed` (default, bit-accurate `ref/qsim.py`) and `sim-float` work; `ghdl`, `board` are stubs (TODO) |
| `tools.py` | the 5 function-calling tools + schemas |
| `agent.py` | planner loop, max 3 repairs, execute + compare + explain |
| `cli.py` / `list_models.py` | entry points |
