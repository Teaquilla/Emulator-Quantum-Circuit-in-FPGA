"""Single source of truth for what the hardware supports (see README, section 3)."""
from __future__ import annotations

HW_QUBITS = 4          # N_QUBITS generic of the VHDL core; LEDs show 16 states
MAX_GATES = 64         # sanity limit per request
PARAM_MAX = 15         # RY/RZ: theta = param * pi / 8
NO_CONTROL = 0xF       # control field value meaning "no control"
LED_THRESHOLD = 0.25   # "expected" lists states with p >= this

OPCODES = {"NOP": 0x0, "H": 0x1, "X": 0x2, "Y": 0x3, "Z": 0x4, "S": 0x5,
           "T": 0x6, "RY": 0x7, "RZ": 0x8, "MEASURE": 0x9, "RESET": 0xF}
FIXED_GATES = ("H", "X", "Y", "Z", "S", "T")
PARAM_GATES = ("RY", "RZ")
GATES = FIXED_GATES + PARAM_GATES


def describe() -> dict:
    """What the list_gates tool returns to the model."""
    return {
        "max_qubits": HW_QUBITS,
        "qubit_order": "qubit 0 is the least significant bit of the state index",
        "gates": {
            "H,X,Y,Z,S,T": "single-qubit gates, fields: op, target",
            "RY,RZ": f"rotations, fields: op, target, param (int 0..{PARAM_MAX}); theta = param*pi/8",
            "RESET": "returns the whole state to |0...0>, no other fields",
        },
        "controlled": "any gate except RESET may take an optional 'control' qubit (applied when control bit = 1); "
                      "control must differ from target. CNOT = op X with a control.",
        "unsupported": ["MEASURE", "more than 4 qubits", "any gate not listed above"],
        "max_gates": MAX_GATES,
        "expected_field": f"expected.led_on = sorted basis-state indices with probability >= {LED_THRESHOLD}",
    }
