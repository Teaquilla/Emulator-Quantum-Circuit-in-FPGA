"""Usage:
  python -m agent.cli "make a Bell state"                 # needs NEBIUS_* env vars
  python -m agent.cli --circuit agent/examples/bell.json  # offline: no LLM, no network
"""
from __future__ import annotations

import argparse
import json
import sys

from .agent import AgentResult, execute, run
from .backends import get_backend
from .config import Config
from .tools import ToolBox


def _print(res: AgentResult, backend: str) -> int:
    if res.refusal:
        print(f"REFUSED / FAILED: {res.refusal}")
        return 1
    print(f"circuit {res.circuit_id} on backend '{backend}' (repairs: {res.repairs})")
    print(res.assembly)
    led = [i for i, p in enumerate(res.measured) if p >= 0.249]
    print("LEDs on (p >= 0.25):", led)
    print("probabilities:", res.measured)
    print(f"compare: {'PASS' if res.passed else 'FAIL'} (max |diff| = {res.max_abs_diff})")
    if res.explanation:
        print("\n" + res.explanation)
    return 0 if res.passed else 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent.cli")
    ap.add_argument("request", nargs="?", help="natural-language request")
    ap.add_argument("--circuit", help="run a circuit JSON file through validator + backend (no LLM)")
    ap.add_argument("--backend", default=None, help="sim-float | ref-fixed | ghdl | board")
    ap.add_argument("--no-explain", action="store_true")
    a = ap.parse_args(argv)

    if a.circuit:
        backend = a.backend or "sim-float"
        tb = ToolBox(get_backend(backend))
        with open(a.circuit) as f:
            res = execute(tb, json.load(f), AgentResult(request=a.circuit))
        return _print(res, backend)

    if not a.request:
        ap.error("give a request or --circuit FILE")
    from .llm import make_client
    cfg = Config.from_env()
    backend = a.backend or cfg.backend
    tb = ToolBox(get_backend(backend), cfg.tolerance)
    res = run(a.request, cfg, make_client(cfg), tb, explain=not a.no_explain)
    return _print(res, backend)


if __name__ == "__main__":
    sys.exit(main())
