"""Deterministic validator. The LLM can only *propose*; nothing reaches a backend
unless this module accepts it. No LLM, no network, no randomness."""
from __future__ import annotations

from dataclasses import dataclass, field

from .gates import FIXED_GATES, GATES, HW_QUBITS, MAX_GATES, PARAM_GATES, PARAM_MAX

_GATE_KEYS = {"op", "target", "control", "param"}
_TOP_KEYS = {"n_qubits", "gates", "expected"}


@dataclass
class Validation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    circuit: dict | None = None     # normalized copy, only when ok


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def validate(circuit) -> Validation:
    errors: list[str] = []
    if not isinstance(circuit, dict):
        return Validation(False, ["circuit must be a JSON object"])

    extra = set(circuit) - _TOP_KEYS
    if extra:
        errors.append(f"unknown top-level keys: {sorted(extra)}")

    n = circuit.get("n_qubits")
    if not _is_int(n) or not 1 <= n <= HW_QUBITS:
        errors.append(f"n_qubits must be an integer 1..{HW_QUBITS} (hardware limit), got {n!r}")
        n = None

    gates = circuit.get("gates")
    norm_gates: list[dict] = []
    if not isinstance(gates, list) or not gates:
        errors.append("gates must be a non-empty list")
    elif len(gates) > MAX_GATES:
        errors.append(f"too many gates ({len(gates)} > {MAX_GATES})")
    else:
        for i, g in enumerate(gates):
            where = f"gates[{i}]"
            if not isinstance(g, dict):
                errors.append(f"{where}: must be an object")
                continue
            if set(g) - _GATE_KEYS:
                errors.append(f"{where}: unknown keys {sorted(set(g) - _GATE_KEYS)}")
            op = g.get("op")
            op = op.strip().upper() if isinstance(op, str) else op
            if op == "MEASURE":
                errors.append(f"{where}: MEASURE is not implemented in hardware")
                continue
            if op == "RESET":
                if set(g) - {"op"}:
                    errors.append(f"{where}: RESET takes no target/control/param")
                norm_gates.append({"op": "RESET"})
                continue
            if op not in GATES:
                errors.append(f"{where}: unsupported op {g.get('op')!r}")
                continue
            ng = {"op": op}
            t, c, p = g.get("target"), g.get("control"), g.get("param")
            if n is not None:
                if not _is_int(t) or not 0 <= t < n:
                    errors.append(f"{where}: target must be an integer in 0..{n - 1}")
                if c is not None and (not _is_int(c) or not 0 <= c < n):
                    errors.append(f"{where}: control must be an integer in 0..{n - 1}")
                if _is_int(t) and _is_int(c) and t == c:
                    errors.append(f"{where}: control and target must differ")
            if op in PARAM_GATES:
                if not _is_int(p) or not 0 <= p <= PARAM_MAX:
                    errors.append(f"{where}: {op} needs integer param 0..{PARAM_MAX}, got {p!r}")
            elif p is not None:
                errors.append(f"{where}: {op} takes no param")
            ng["target"] = t
            if c is not None:
                ng["control"] = c
            if op in PARAM_GATES:
                ng["param"] = p
            norm_gates.append(ng)

    expected = circuit.get("expected")
    norm_expected = None
    if not isinstance(expected, dict) or "led_on" not in expected:
        errors.append("expected.led_on is required")
    else:
        led = expected["led_on"]
        limit = 2 ** n if n else 2 ** HW_QUBITS
        if not isinstance(led, list) or not all(_is_int(x) and 0 <= x < limit for x in led):
            errors.append(f"expected.led_on must be a list of state indices in 0..{limit - 1}")
        else:
            note = expected.get("note", "")
            norm_expected = {"led_on": sorted(set(led)),
                             "note": note[:200] if isinstance(note, str) else ""}

    if errors:
        return Validation(False, errors)
    return Validation(True, [], {"n_qubits": n, "gates": norm_gates, "expected": norm_expected})
