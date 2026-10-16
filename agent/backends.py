"""Execution backends. All return 16 probabilities (index = basis state).

Implemented now : sim-float  (NumPy float model)
                  ref-fixed  (bit-accurate fixed-point model from ref/qsim.py; identical to the VHDL)
Stubs to fill   : ghdl       (real VHDL via a program-driven testbench)
                  board      (Basys 3 over UART; needs uart_tx.vhd for read-back)
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .gates import HW_QUBITS
from .simulate import probabilities

_QSIM = None


def load_qsim():
    """Load ref/qsim.py (sibling of agent/ in the repo root) without touching sys.path."""
    global _QSIM
    if _QSIM is None:
        path = Path(__file__).resolve().parents[1] / "ref" / "qsim.py"
        if not path.exists():
            raise BackendUnavailable(f"ref/qsim.py not found at {path}; keep agent/ and ref/ side by side")
        spec = importlib.util.spec_from_file_location("qsim", path)
        _QSIM = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_QSIM)
    return _QSIM


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
    """Runs the program through ref/qsim.py's bit-accurate fixed-point model (Q1.15 amplitudes,
    Q2.14 coefficients). CI checks this model against the VHDL testbenches, so it stands in
    for the hardware until the board / GHDL backends are wired."""
    name = "ref-fixed"

    def run(self, circuit, assembly, words):
        q = load_qsim()
        prog = q.assemble(assembly)
        re_, im_ = q.run_fx(HW_QUBITS, prog)
        amps = q.fx_to_complex(re_, im_)
        return [float(abs(a) ** 2) for a in amps]


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
