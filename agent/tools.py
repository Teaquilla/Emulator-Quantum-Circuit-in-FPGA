"""The five agent tools + their OpenAI-style function schemas.

Safety property: run_on_fpga / compare take a circuit_id that the validator issued.
The model can never hand raw program bytes to a backend.
"""
from __future__ import annotations

import hashlib
import json

from . import gates
from .backends import Backend, BackendUnavailable
from .compiler import to_assembly, to_words
from .simulate import led_on, probabilities
from .validator import validate


def circuit_id(circuit: dict) -> str:
    blob = json.dumps(circuit, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha1(blob).hexdigest()[:8]


class ToolBox:
    def __init__(self, backend: Backend, tolerance: float = 0.02):
        self.backend = backend
        self.tol = tolerance
        self.circuits: dict[str, dict] = {}
        self.measured: dict[str, list[float]] = {}
        self.last_id: str | None = None

    # -- tools ---------------------------------------------------------------
    def list_gates(self) -> dict:
        return gates.describe()

    def compile_and_simulate(self, circuit: dict) -> dict:
        v = validate(circuit)
        if not v.ok:
            return {"ok": False, "stage": "validation", "errors": v.errors}
        c = v.circuit
        cid = circuit_id(c)
        self.circuits[cid] = c
        probs = probabilities(c)
        sim_on, exp_on = led_on(probs), c["expected"]["led_on"]
        return {"ok": True, "circuit_id": cid, "assembly": to_assembly(c),
                "words_hex": [f"{w:04X}" for w in to_words(c)],
                "probabilities": [round(p, 4) for p in probs],
                "simulated_led_on": sim_on, "expected_led_on": exp_on,
                "expected_matches": sim_on == exp_on}

    def run_on_fpga(self, circuit_id: str) -> dict:
        c = self.circuits.get(circuit_id)
        if c is None:
            return {"ok": False, "error": "unknown circuit_id; call compile_and_simulate first"}
        try:
            probs = self.backend.run(c, to_assembly(c), to_words(c))
        except BackendUnavailable as e:
            return {"ok": False, "backend": self.backend.name, "error": str(e)}
        self.measured[circuit_id] = probs
        self.last_id = circuit_id
        return {"ok": True, "backend": self.backend.name}

    def read_state(self) -> dict:
        if self.last_id is None:
            return {"ok": False, "error": "nothing has been run yet"}
        return {"ok": True, "circuit_id": self.last_id, "backend": self.backend.name,
                "probabilities": [round(p, 4) for p in self.measured[self.last_id]]}

    def compare(self, circuit_id: str) -> dict:
        c, m = self.circuits.get(circuit_id), self.measured.get(circuit_id)
        if c is None or m is None:
            return {"ok": False, "error": "run_on_fpga must succeed for this circuit_id first"}
        ref = probabilities(c)
        diff = max(abs(a - b) for a, b in zip(ref, m))
        return {"ok": True, "passed": diff <= self.tol and led_on(m) == led_on(ref),
                "max_abs_diff": round(diff, 5), "tolerance": self.tol,
                "measured_led_on": led_on(m), "expected_led_on": led_on(ref)}

    # -- dispatch ------------------------------------------------------------
    def dispatch(self, name: str, arguments) -> dict:
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
            fn = {"list_gates": self.list_gates, "compile_and_simulate": self.compile_and_simulate,
                  "run_on_fpga": self.run_on_fpga, "read_state": self.read_state,
                  "compare": self.compare}.get(name)
            if fn is None:
                return {"ok": False, "error": f"unknown tool {name!r}"}
            return fn(**args)
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"bad arguments: {e}"}


def _fn(name, description, properties=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": list(required)}}}


TOOL_SCHEMAS = [
    _fn("list_gates", "List supported gates, parameter ranges and hardware limits."),
    _fn("compile_and_simulate",
        "Validate a circuit, compile it to assembly and simulate it. Returns circuit_id, "
        "probabilities and whether your 'expected' matches. Errors say exactly what to fix.",
        {"circuit": {"type": "object", "description": "{n_qubits, gates:[{op,target,control?,param?}], expected:{led_on,note}}"}},
        ["circuit"]),
    _fn("run_on_fpga", "Run a validated circuit (by circuit_id) on the configured execution backend.",
        {"circuit_id": {"type": "string"}}, ["circuit_id"]),
    _fn("read_state", "Read back the 16 state probabilities from the last run."),
    _fn("compare", "Compare the measured result of a circuit_id with the reference simulation.",
        {"circuit_id": {"type": "string"}}, ["circuit_id"]),
]
