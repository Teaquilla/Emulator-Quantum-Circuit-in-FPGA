"""Float64 state-vector reference used by the agent to sanity-check circuits.

This is an *independent* quick model (NumPy). The project's golden model remains
ref/qsim.py (bit-accurate fixed-point); see backends.QsimFixedBackend.
"""
from __future__ import annotations

import numpy as np

from .gates import HW_QUBITS, LED_THRESHOLD


def gate_matrix(op: str, param: int | None = None) -> np.ndarray:
    s = 1 / np.sqrt(2)
    if op == "H":
        return np.array([[s, s], [s, -s]], dtype=complex)
    if op == "X":
        return np.array([[0, 1], [1, 0]], dtype=complex)
    if op == "Y":
        return np.array([[0, -1j], [1j, 0]], dtype=complex)
    if op == "Z":
        return np.array([[1, 0], [0, -1]], dtype=complex)
    if op == "S":
        return np.array([[1, 0], [0, 1j]], dtype=complex)
    if op == "T":
        return np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=complex)
    theta = param * np.pi / 8
    c, sn = np.cos(theta / 2), np.sin(theta / 2)
    if op == "RY":
        return np.array([[c, -sn], [sn, c]], dtype=complex)
    if op == "RZ":
        # Same convention as ref/qsim.py (checked by tests): diag(cos-i*sin, cos+i*sin) of theta/2.
        return np.array([[np.exp(-1j * theta / 2), 0], [0, np.exp(1j * theta / 2)]], dtype=complex)
    raise ValueError(f"unsupported op {op}")


def simulate_state(circuit: dict) -> np.ndarray:
    dim = 2 ** HW_QUBITS
    state = np.zeros(dim, dtype=complex)
    state[0] = 1.0
    for g in circuit["gates"]:
        if g["op"] == "RESET":
            state[:] = 0
            state[0] = 1.0
            continue
        m = gate_matrix(g["op"], g.get("param"))
        t, c = g["target"], g.get("control")
        for i0 in range(dim):
            if (i0 >> t) & 1:
                continue
            if c is not None and not (i0 >> c) & 1:
                continue
            i1 = i0 | (1 << t)
            a, b = state[i0], state[i1]
            state[i0] = m[0, 0] * a + m[0, 1] * b
            state[i1] = m[1, 0] * a + m[1, 1] * b
    return state


def probabilities(circuit: dict) -> list[float]:
    """16 probabilities, index = basis state (qubit 0 = LSB), like the LEDs."""
    return [float(p) for p in np.abs(simulate_state(circuit)) ** 2]


def led_on(probs: list[float], thr: float = LED_THRESHOLD, eps: float = 1e-3) -> list[int]:
    return [i for i, p in enumerate(probs) if p >= thr - eps]
