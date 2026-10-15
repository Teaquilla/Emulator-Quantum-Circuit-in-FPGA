"""Validated circuit JSON -> assembly text (+ 16-bit words for display/tests).

Assembly is the format accepted by ref/qsim.py and `host/send_program.py --asm`.
`words` are informational: byte order on the wire is handled by send_program.py.
"""
from __future__ import annotations

from .gates import NO_CONTROL, OPCODES, PARAM_GATES


def _mnemonic(op: str, controlled: bool) -> str:
    if not controlled:
        return op
    return "CNOT" if op == "X" else "C" + op


def to_assembly(circuit: dict) -> str:
    lines = ["RESET"]                       # always start from |0...0>
    for g in circuit["gates"]:
        if g["op"] == "RESET":
            lines.append("RESET")
            continue
        c = g.get("control")
        parts = [_mnemonic(g["op"], c is not None)]
        if c is not None:
            parts.append(str(c))
        parts.append(str(g["target"]))
        if g["op"] in PARAM_GATES:
            parts.append(str(g["param"]))
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"


def encode_word(op: str, target: int = 0, control: int | None = None, param: int = 0) -> int:
    """[opcode:4][target:4][control:4][param:4]; control 0xF = none."""
    ctl = NO_CONTROL if control is None else control
    return (OPCODES[op] << 12) | (target << 8) | (ctl << 4) | param


def to_words(circuit: dict) -> list[int]:
    words = [encode_word("RESET")]
    for g in circuit["gates"]:
        if g["op"] == "RESET":
            words.append(encode_word("RESET"))
        else:
            words.append(encode_word(g["op"], g["target"], g.get("control"), g.get("param", 0)))
    return words
