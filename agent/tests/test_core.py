"""Offline tests: no network, no openai package, stdlib unittest only."""
import json
import unittest
from types import SimpleNamespace as NS

from agent.agent import AgentResult, execute, run
from agent.backends import get_backend
from agent.compiler import to_assembly, to_words
from agent.config import Config
from agent.llm import extract_json
from agent.simulate import led_on, probabilities
from agent.tools import ToolBox
from agent.validator import validate

BELL = {"n_qubits": 2,
        "gates": [{"op": "H", "target": 0}, {"op": "X", "target": 1, "control": 0}],
        "expected": {"led_on": [0, 3], "note": "Bell"}}


def load(name):
    with open(f"agent/examples/{name}.json") as f:
        return json.load(f)


class ValidatorTests(unittest.TestCase):
    def test_accepts_bell(self):
        self.assertTrue(validate(BELL).ok)

    def test_rejections(self):
        def bad(**patch):
            c = json.loads(json.dumps(BELL)); c.update(patch); return validate(c)
        self.assertFalse(bad(n_qubits=5).ok)                                   # too many qubits
        self.assertFalse(bad(n_qubits=True).ok)                                # bool is not an int
        self.assertFalse(bad(gates=[{"op": "MEASURE", "target": 0}]).ok)       # not implemented
        self.assertFalse(bad(gates=[{"op": "SWAP", "target": 0}]).ok)          # unsupported
        self.assertFalse(bad(gates=[{"op": "RY", "target": 0, "param": 16}]).ok)
        self.assertFalse(bad(gates=[{"op": "RY", "target": 0}]).ok)            # missing param
        self.assertFalse(bad(gates=[{"op": "H", "target": 0, "param": 1}]).ok)
        self.assertFalse(bad(gates=[{"op": "H", "target": 2}]).ok)             # out of range
        self.assertFalse(bad(gates=[{"op": "X", "target": 1, "control": 1}]).ok)
        self.assertFalse(bad(gates=[]).ok)
        self.assertFalse(bad(expected={"led_on": [4]}).ok)                     # index >= 2**n
        self.assertFalse(validate("not a dict").ok)

    def test_normalizes_case(self):
        c = json.loads(json.dumps(BELL)); c["gates"][0]["op"] = " h "
        v = validate(c); self.assertTrue(v.ok); self.assertEqual(v.circuit["gates"][0]["op"], "H")


class CompileSimTests(unittest.TestCase):
    def test_assembly_and_words(self):
        c = validate(BELL).circuit
        self.assertEqual(to_assembly(c), "RESET\nH 0\nCNOT 0 1\n")
        self.assertEqual(to_words(c)[0], 0xF000)            # RESET, as assembled by qsim.py
        self.assertEqual(to_words(c)[1], 0x10F0)            # H, target 0, no control
        self.assertEqual(to_words(c)[2], 0x2100)            # X, target 1, control 0

    def test_controlled_rotation_assembly(self):
        c = validate({"n_qubits": 2, "gates": [{"op": "RY", "target": 1, "control": 0, "param": 8}],
                      "expected": {"led_on": [0]}}).circuit
        self.assertIn("CRY 0 1 8", to_assembly(c))

    def test_bell_probabilities(self):
        p = probabilities(validate(BELL).circuit)
        self.assertAlmostEqual(p[0], 0.5); self.assertAlmostEqual(p[3], 0.5)
        self.assertAlmostEqual(sum(p), 1.0)

    def test_examples(self):
        for name in ("bell", "grover2", "rabi_08"):
            c = validate(load(name)); self.assertTrue(c.ok, c.errors)
            self.assertEqual(led_on(probabilities(c.circuit)), c.circuit["expected"]["led_on"], name)

    def test_rabi_oscillation(self):
        import math
        for k in range(16):
            c = validate({"n_qubits": 1, "gates": [{"op": "RY", "target": 0, "param": k}],
                          "expected": {"led_on": []}}).circuit
            self.assertAlmostEqual(probabilities(c)[1], math.sin(k * math.pi / 16) ** 2, places=9)


class ToolBoxTests(unittest.TestCase):
    def test_flow_and_circuit_id_gate(self):
        tb = ToolBox(get_backend("sim-float"))
        self.assertFalse(tb.run_on_fpga("deadbeef")["ok"])          # raw/unknown ids rejected
        chk = tb.compile_and_simulate(BELL)
        self.assertTrue(chk["ok"] and chk["expected_matches"])
        self.assertTrue(tb.run_on_fpga(chk["circuit_id"])["ok"])
        self.assertTrue(tb.compare(chk["circuit_id"])["passed"])

    def test_unavailable_backend_reported(self):
        tb = ToolBox(get_backend("board"))
        cid = tb.compile_and_simulate(BELL)["circuit_id"]
        out = tb.run_on_fpga(cid); self.assertFalse(out["ok"]); self.assertIn("uart_tx", out["error"])

    def test_cli_mode_execute(self):
        res = execute(ToolBox(get_backend("sim-float")), load("grover2"), AgentResult(request="x"))
        self.assertTrue(res.ok and res.passed)


# ---- agent loop with a scripted fake client (no network) ---------------------------------
def reply(content=None, tool_calls=None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=tool_calls))])


def call(name, args, cid="c1"):
    return NS(id=cid, function=NS(name=name, arguments=json.dumps(args)))


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.chat = NS(completions=NS(create=self._create))
        self.calls = 0

    def _create(self, **kw):
        self.calls += 1
        return self.script.pop(0)


CFG = Config(api_key="k", base_url="u", planner_model="p", fast_model="f")


class AgentLoopTests(unittest.TestCase):
    def test_tool_call_then_final_json(self):
        fc = FakeClient([reply(tool_calls=[call("compile_and_simulate", {"circuit": BELL})]),
                         reply(content="```json\n" + json.dumps(BELL) + "\n```"),
                         reply(content="Bell state explained.")])
        res = run("bell please", CFG, fc, ToolBox(get_backend("sim-float")))
        self.assertTrue(res.ok and res.passed); self.assertEqual(res.repairs, 0)
        self.assertEqual(res.explanation, "Bell state explained.")

    def test_repairs_wrong_expected_then_succeeds(self):
        wrong = json.loads(json.dumps(BELL)); wrong["expected"]["led_on"] = [0, 1]
        fc = FakeClient([reply(content=json.dumps(wrong)), reply(content=json.dumps(BELL)), reply(content="ok")])
        res = run("bell", CFG, fc, ToolBox(get_backend("sim-float")))
        self.assertTrue(res.ok); self.assertEqual(res.repairs, 1)

    def test_gives_up_after_max_repairs(self):
        wrong = json.loads(json.dumps(BELL)); wrong["expected"]["led_on"] = [1]
        fc = FakeClient([reply(content=json.dumps(wrong)) for _ in range(10)])
        res = run("bell", CFG, fc, ToolBox(get_backend("sim-float")))
        self.assertFalse(res.ok); self.assertEqual(res.repairs, CFG.max_repairs + 1)
        self.assertIn("repair", res.refusal)

    def test_model_refusal_passthrough(self):
        fc = FakeClient([reply(content='{"error": "needs 6 qubits"}')])
        res = run("6 qubit qft", CFG, fc, ToolBox(get_backend("sim-float")))
        self.assertFalse(res.ok); self.assertEqual(res.refusal, "needs 6 qubits")

    def test_invalid_circuit_never_reaches_backend(self):
        class Spy(get_backend("sim-float").__class__):
            ran = False
            def run(self, *a): Spy.ran = True; return super().run(*a)
        bad = {"n_qubits": 6, "gates": [{"op": "H", "target": 0}], "expected": {"led_on": [0]}}
        fc = FakeClient([reply(content=json.dumps(bad)) for _ in range(10)])
        res = run("x", CFG, fc, ToolBox(Spy()))
        self.assertFalse(res.ok); self.assertFalse(Spy.ran)

    def test_extract_json_handles_think_blocks(self):
        self.assertEqual(extract_json('<think>hmm {x}</think> {"a": 1}'), {"a": 1})


# ---- cross-checks against the project's golden model (skipped if ref/qsim.py is absent) ----
import os
from agent.backends import load_qsim
HAVE_QSIM = os.path.exists(os.path.join(os.path.dirname(__file__), "..", "..", "ref", "qsim.py"))


def instrs_to_circuit(prog):
    gates = []
    for i in prog:
        if i.op == "RESET":
            gates.append({"op": "RESET"})
        else:
            g = {"op": i.op, "target": i.tgt}
            if i.ctl != 0xF:
                g["control"] = i.ctl
            if i.op in ("RY", "RZ"):
                g["param"] = i.par
            gates.append(g)
    return {"n_qubits": 4, "gates": gates, "expected": {"led_on": []}}


@unittest.skipUnless(HAVE_QSIM, "ref/qsim.py not found")
class QsimCrossCheck(unittest.TestCase):
    def setUp(self):
        self.q = load_qsim()

    def test_encoding_matches_qsim_for_every_demo(self):
        for name, src in self.q.PROGRAMS.items():
            prog = [i for i in self.q.assemble(src) if i.op != "MEASURE"]
            v = validate(instrs_to_circuit(prog)); self.assertTrue(v.ok, (name, v.errors))
            asm = to_assembly(v.circuit)
            ours = [self.q.encode(i) for i in self.q.assemble(asm)]
            self.assertEqual(to_words(v.circuit), ours, name)

    def test_float_model_matches_qsim_for_every_demo(self):
        import numpy as np
        for name, src in self.q.PROGRAMS.items():
            prog = self.q.assemble(src)
            ref = np.abs(self.q.run_float(4, prog)) ** 2
            v = validate(instrs_to_circuit(prog))
            self.assertTrue(np.allclose(probabilities(v.circuit), ref, atol=1e-9), name)

    def test_ref_fixed_backend_close_to_float(self):
        tb = ToolBox(get_backend("ref-fixed"))
        for name in ("bell", "grover2", "rabi_08"):
            res = execute(tb, load(name), AgentResult(request=name))
            self.assertTrue(res.ok and res.passed, (name, res.refusal, res.max_abs_diff))

    def test_agent_loop_on_ref_fixed(self):
        fc = FakeClient([reply(content=json.dumps(BELL)), reply(content="ok")])
        res = run("bell", CFG, fc, ToolBox(get_backend("ref-fixed")))
        self.assertTrue(res.ok and res.passed)


class DotenvTests(unittest.TestCase):
    def test_loader_parses_and_never_overrides(self):
        import tempfile
        from pathlib import Path
        from agent.config import load_dotenv
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / ".env"
            f.write_text("# comment\nT_A=plain\nT_B = \"quoted value\"\nexport T_C='single'\nT_D=keep_me_not\n\nbadline\n",
                         encoding="utf-8")
            os.environ["T_D"] = "already-set"
            for k in ("T_A", "T_B", "T_C"):
                os.environ.pop(k, None)
            names = load_dotenv([f])
            self.assertEqual(sorted(names), ["T_A", "T_B", "T_C"])        # names only, never values
            self.assertEqual((os.environ["T_A"], os.environ["T_B"], os.environ["T_C"]), ("plain", "quoted value", "single"))
            self.assertEqual(os.environ["T_D"], "already-set")            # real env wins
            for k in ("T_A", "T_B", "T_C", "T_D"):
                os.environ.pop(k, None)

    def test_missing_file_is_fine(self):
        from agent.config import load_dotenv
        self.assertEqual(load_dotenv(["/nonexistent/.env"]), [])


if __name__ == "__main__":
    unittest.main()
