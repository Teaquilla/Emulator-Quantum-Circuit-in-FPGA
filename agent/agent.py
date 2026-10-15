"""Planner loop: Nemotron proposes, deterministic code verifies, backend executes."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .config import Config
from .llm import extract_json
from .prompts import EXPLAIN_PROMPT, SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, ToolBox


@dataclass
class AgentResult:
    request: str
    ok: bool = False
    circuit: dict | None = None
    circuit_id: str | None = None
    assembly: str | None = None
    simulated: list | None = None
    measured: list | None = None
    passed: bool | None = None
    max_abs_diff: float | None = None
    refusal: str | None = None
    explanation: str | None = None
    repairs: int = 0
    trace: list = field(default_factory=list)


def _assistant_msg(m) -> dict:
    msg = {"role": "assistant", "content": m.content or ""}
    if getattr(m, "tool_calls", None):
        msg["tool_calls"] = [{"id": tc.id, "type": "function",
                              "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                             for tc in m.tool_calls]
    return msg


def _feedback(chk: dict) -> str:
    if not chk["ok"]:
        return "Validation failed: " + "; ".join(chk["errors"]) + ". Fix these and reply with the corrected JSON only."
    return (f"Simulation disagrees with your expected.led_on {chk['expected_led_on']}: "
            f"the circuit actually lights {chk['simulated_led_on']} (probabilities {chk['probabilities']}). "
            "Fix the circuit or the expected list and reply with the corrected JSON only.")


def execute(toolbox: ToolBox, circuit: dict, res: AgentResult) -> AgentResult:
    """Validate -> run on backend -> compare. Used by the LLM loop and by --circuit mode."""
    chk = toolbox.compile_and_simulate(circuit)
    if not chk["ok"]:
        res.refusal = "validation failed: " + "; ".join(chk["errors"])
        return res
    cid = chk["circuit_id"]
    res.circuit, res.circuit_id = toolbox.circuits[cid], cid
    res.assembly, res.simulated = chk["assembly"], chk["probabilities"]
    run = toolbox.run_on_fpga(cid)
    res.trace.append({"tool": "run_on_fpga", "result": run})
    if not run["ok"]:
        res.refusal = f"backend error: {run['error']}"
        return res
    cmp_ = toolbox.compare(cid)
    res.trace.append({"tool": "compare", "result": cmp_})
    res.measured = toolbox.read_state()["probabilities"]
    res.passed, res.max_abs_diff = cmp_["passed"], cmp_["max_abs_diff"]
    res.ok = True
    return res


def run(request: str, cfg: Config, client, toolbox: ToolBox, explain: bool = True) -> AgentResult:
    res = AgentResult(request=request)
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": request}]
    verified = None

    for _ in range(cfg.max_rounds):
        resp = client.chat.completions.create(model=cfg.planner_model, messages=msgs,
                                              tools=TOOL_SCHEMAS, tool_choice="auto", temperature=0.2)
        m = resp.choices[0].message
        msgs.append(_assistant_msg(m))

        if getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                out = toolbox.dispatch(tc.function.name, tc.function.arguments)
                res.trace.append({"tool": tc.function.name, "result": out})
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})
            continue

        try:
            data = extract_json(m.content)
        except ValueError as e:
            msgs.append({"role": "user", "content": f"Could not parse your reply ({e}). Reply with ONLY the JSON object."})
            continue
        if "error" in data and "gates" not in data:
            res.refusal = str(data["error"])
            return res

        chk = toolbox.compile_and_simulate(data)      # never trust the model's own check
        if chk["ok"] and chk["expected_matches"]:
            verified = data
            break
        res.repairs += 1
        if res.repairs > cfg.max_repairs:
            res.refusal = f"no verified circuit after {cfg.max_repairs} repair attempts"
            return res
        msgs.append({"role": "user", "content": _feedback(chk)})

    if verified is None:
        res.refusal = res.refusal or "round limit reached without a verified circuit"
        return res

    execute(toolbox, verified, res)
    if res.ok and explain:
        try:
            summary = {"request": request, "circuit": res.circuit, "backend": toolbox.backend.name,
                       "expected_led_on": res.circuit["expected"]["led_on"],
                       "measured_probabilities": res.measured, "passed": res.passed}
            r = client.chat.completions.create(
                model=cfg.fast_model, temperature=0.3,
                messages=[{"role": "system", "content": EXPLAIN_PROMPT},
                          {"role": "user", "content": json.dumps(summary)}])
            res.explanation = (r.choices[0].message.content or "").strip()
        except Exception as e:                        # explanation is optional; never fail the run
            res.explanation = f"(explanation unavailable: {e})"
    return res
