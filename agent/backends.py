"""Execution backends. All return 16 probabilities (index = basis state).

Implemented now : sim-float  (NumPy; lets the whole agent loop run today)
Stubs to fill   : ref-fixed  (bit-accurate ref/qsim.py model)
                  ghdl       (real VHDL via a program-driven testbench)
                  board      (Basys 3 over UART; needs uart_tx.vhd for read-back)
"""
from __future__ import annotations

from .simulate import probabilities


class BackendUnavailable(RuntimeError):
    pass


class Backend:
    name = "base"

    def run(self, circuit: dict, assembly: str, words: list[int]) -> list[float]:
        raise NotImplementedError


class FloatBackend(Backend):
    name = "sim-float"

    def run(self, circuit, assembly, words):
        return probabilities(circuit)


class QsimFixedBackend(Backend):
    """TODO: call the fixed-point model in ref/qsim.py and return its 16 probabilities
    (re^2 + im^2 of the final state, Q1.15 -> float). Map the function names once
    you have checked qsim.py."""
    name = "ref-fixed"

    def run(self, circuit, assembly, words):
        raise BackendUnavailable("ref-fixed backend not wired to ref/qsim.py yet")


class GhdlBackend(Backend):
    """TODO: write the assembly to a .mem program, run a testbench that loads it, executes it
    on qcore and dumps the final state vector, then parse the dump. The existing testbenches
    use fixed programs, so this needs a small new testbench (e.g. sim/tb_run_prog.vhd)."""
    name = "ghdl"

    def run(self, circuit, assembly, words):
        raise BackendUnavailable("ghdl backend needs a program-driven testbench")


class BoardBackend(Backend):
    """TODO: send via host/send_program.py; reading results back needs uart_tx.vhd."""
    name = "board"

    def run(self, circuit, assembly, words):
        raise BackendUnavailable("board read-back needs uart_tx.vhd (roadmap step 5)")


_REGISTRY = {b.name: b for b in (FloatBackend, QsimFixedBackend, GhdlBackend, BoardBackend)}


def get_backend(name: str) -> Backend:
    if name not in _REGISTRY:
        raise ValueError(f"unknown backend {name!r}; choose from {sorted(_REGISTRY)}")
    return _REGISTRY[name]()
