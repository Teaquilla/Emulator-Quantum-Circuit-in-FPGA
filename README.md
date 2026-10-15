# Quantum Circuit Emulator on an FPGA

[![FPGA VHDL CI Pipeline](https://github.com/Teaquilla/Quantum-Circuit-Emulator-on-an-FPGA/actions/workflows/vhdl_ci.yml/badge.svg)](https://github.com/Teaquilla/Quantum-Circuit-Emulator-on-an-FPGA/actions/workflows/vhdl_ci.yml)
[![License](https://img.shields.io/github/license/Teaquilla/Quantum-Circuit-Emulator-on-an-FPGA)](LICENSE)

A hardware accelerator that emulates **small state-vector quantum circuits** on an Artix-7 FPGA (**Basys 3**, `xc7a35tcpg236-1`). Written in **VHDL** for **Vivado**, and verified bit-for-bit against a Python reference model.
The default size is **4 qubits**; the qubit count is set by the `N_QUBITS` generic.

> **Scope note:** this is a state-vector *emulator* running in hardware, **not** a physical quantum computer.
> The contribution is the fixed-point datapath, the control FSM, bit-accurate verification, and an analysis of numerical error and resource use.

**Built for the Nebius x NVIDIA Global AI Hackathon.** On top of the emulator, we are adding an LLM agent layer
(NVIDIA Nemotron served on Nebius Token Factory) that turns natural-language requests into circuits, checks them with a
deterministic validator, runs them on the emulator, and compares the hardware result against the reference model.
See [AI agent layer](#ai-agent-layer-hackathon-work) and the [update log](#hackathon-update-log).

---

## Table of contents

1. [How it works](#1-how-it-works)
2. [AI agent layer (hackathon work)](#ai-agent-layer-hackathon-work)
3. [Repository layout](#2-repository-layout)
4. [Number formats and instruction set](#3-number-formats-and-instruction-set)
5. [Quick start](#4-quick-start)
6. [Reading results on the LEDs](#5-reading-results-on-the-leds)
7. [CI](#6-ci-github-actions)
8. [Synthesis and implementation results](#synthesis-and-implementation-results)
9. [Board test checklist](#7-board-test-checklist)
10. [Troubleshooting](#8-troubleshooting)
11. [Limitations and roadmap](#9-limitations-and-roadmap)
12. [Hackathon update log](#hackathon-update-log)
13. [License](#license)

## Status

| Stage                                                      | Status                                                                                                              |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Python reference model (float + bit-accurate fixed-point)  | Done: fidelity > 0.999 for all demos                                                                                |
| Behavioral simulation in xsim (Vivado 2026.1)              | Done: `tb_gate_engine` (494 vectors), `tb_qcore` (10/10 programs), `tb_qemu_top` (4 cases)                          |
| 4-qubit synthesis                                          | Done: 100 MHz timing met, RAM inferred as BRAM (see [results](#synthesis-and-implementation-results))               |
| Implementation + bitstream                                 | Done: bitstream generated; post-route numbers not yet recorded                                                      |
| Board test (UART to LEDs)                                  | Pending: waiting to borrow a board                                                                                  |
| GitHub Actions CI                                          | Done: Python model + all three testbenches under GHDL, first run green                                              |
| LLM agent layer (Nemotron on Token Factory)                | In progress (hackathon work)                                                                                        |

---

## 1. How it works

n qubits = 2^n complex amplitudes. A single-qubit gate on target qubit `t` is a 2x2 matrix multiplication applied to every pair
of amplitudes `(i0, i1)` whose indices differ only in bit `t`:

```
[a']   [g00 g01] [a]        a = state[i0]   (bit t = 0)
[b'] = [g10 g11] [b]        b = state[i1]   (bit t = 1)
```

- **Controlled gates** (CNOT, CZ, CS, CRY, ...) = a normal gate plus a *control* field; the pair is skipped when the control bit of `i0` is 0.
  There is no dedicated CNOT datapath.
- One butterfly unit is reused for all pairs (2^(n-1) pairs per gate).
- Qubit 0 = least significant bit of the state index.

```
PC ──UART 115200 8N1──► uart_rx ──► 2-byte assembler ──► ┌───────────────────────────── qcore ─────────────────────────────┐
(host/send_program.py)              (qemu_top)           │  qstate_ctrl ──addr/WE──► qstate_ram (2^N x 32 bit)             │
                                                         │      │  ▲                        │ dout A/B                    │
                                                         │      ▼  │ valid_out/result       ▼                             │
                                                         │   gate_engine (2x2 complex butterfly, 4 stages) ◄───────────┘ │
                                                         └───────────────────────────────┬──────────────────────────────────┘
                                        state scan (re²+im²) ◄───── rd_addr/rd_data ─────┘ ──► LED[15:0]
```

Cycles per pair ≈ 7 clocks (`ISSUE` → `CAPTURE` → 4 clocks `WAIT_ENG` → `NEXT`):
4 qubits ≈ 60 clocks (~0.6 µs @ 100 MHz) per gate, 10 qubits ≈ 3,600 clocks (~36 µs).

## AI agent layer (hackathon work)

> **Status: in development.** This section describes the design; the [update log](#hackathon-update-log) tracks what is actually implemented.

The agent "drives" the emulator. An LLM proposes circuits, but **deterministic code decides what is allowed to reach the hardware**.

```
Natural language ─► [Planner: Nemotron] ─► circuit JSON
                 ─► [Deterministic validator / compiler] ─► assembly ─► 16-bit instructions
                 ─► [Reference model ref/qsim.py] ─► expected probabilities
                 ─► [Executor: board over UART  |  GHDL simulation of the real VHDL] ─► measured result
                 ─► [Explainer: Nemotron] ─► explanation + hardware-vs-model comparison
                        ↑_______________ repair loop (max 3 retries) if results do not match _______________|
```

**Model roles** (exact endpoint IDs are taken from the Token Factory catalog):

- A larger Nemotron model is the **planner** (reasoning: e.g. "Grover on 2 qubits, target |11>" into a gate sequence).
- A smaller Nemotron model produces **explanations and quick calls** to save credits.

**Tools exposed to the agent (function calling):**

1. `list_gates()` returns supported gates and limits (4 qubits, params 0..15).
2. `compile_and_simulate(circuit)` returns assembly, float and fixed-point probabilities, and fidelity.
3. `run_on_fpga(program)` sends the program over UART or to the simulation backend.
4. `read_state()` reads the result back.
5. `compare(expected, measured)` returns pass/fail plus the difference.

**Safety by construction:** the validator rejects more than 4 qubits, unsupported gates, `RY`/`RZ` parameters outside 0..15,
invalid qubit indices, and `MEASURE` (not implemented). The LLM can only propose; it cannot bypass these checks.

**Planner output schema:**

```json
{
  "n_qubits": 2,
  "gates": [
    {"op": "H", "target": 0},
    {"op": "CNOT", "control": 0, "target": 1}
  ],
  "expected": {"led_on": [0, 3], "note": "Bell state, p=0.5 each"}
}
```

**Backends.** The executor has two interchangeable backends: the physical Basys 3 board (UART), and a GHDL simulation of the
actual VHDL (`tb_qemu_top`). The second keeps the demo running on the real RTL when a board is not available.

*Running the agent: instructions will be added here when `agent/` lands (see the update log).*

## 2. Repository layout

```
src/      gate_engine.vhd  qstate_ram.vhd  qstate_ctrl.vhd  qcore.vhd  uart_rx.vhd  qemu_top.vhd
sim/      tb_gate_engine.vhd  tb_qcore.vhd  tb_qemu_top.vhd  + prog_*.mem / golden_*.mem / gate_vectors.mem
ref/      qsim.py           float + bit-accurate fixed-point reference model, assembler, .mem generator
host/     send_program.py   send a program to the board over UART
constr/   basys3.xdc
scripts/  create_project.tcl  sim_ghdl.sh
agent/    (hackathon) LLM planner, validator, tools, executor backends
```

| File                   | Role                                                                                                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gate_engine.vhd`      | 2x2 complex butterfly, 4-stage pipeline (operands → 16 multiplies/DSP → 34-bit sum → round + saturate), gate coefficient table.                                           |
| `qstate_ram.vhd`       | State-vector memory 2^N x 32 bit `{re, im}`, true dual-port read-first (Xilinx shared-variable pattern + `ram_style = block`). **Must be file type VHDL (not 2008) in Vivado.** |
| `qstate_ctrl.vhd`      | FSM: instruction decode, pair index iteration, controlled gates, `RESET`; invalid operands become NOP.                                                                    |
| `qcore.vhd`            | RAM + engine + controller, with no pins or UART (used by testbenches).                                                                                                    |
| `uart_rx.vhd`          | 8N1 UART receiver (generics `CLK_HZ`, `BAUD`).                                                                                                                            |
| `qemu_top.vhd`         | Basys 3 top level: UART → 16-bit instruction → `qcore` → state scan → LEDs. Automatic RESET at power-up and on `btnC`.                                                    |
| `tb_gate_engine.vhd`   | Engine vs `gate_vectors.mem` (494 vectors, all gates, RY/RZ params 0..15, saturation).                                                                                    |
| `tb_qcore.vhd`         | 10 programs vs `golden_*.mem`, the full state vector compared bit for bit.                                                                                                |
| `tb_qemu_top.vhd`      | End-to-end test: UART bytes → LEDs (boot, Bell, X, 4-qubit superposition). No `.mem` files needed.                                                                       |
| `ref/qsim.py`          | Float model (NumPy), hardware-identical fixed-point model, assembler, `.mem` generator.                                                                                   |
| `host/send_program.py` | Send a program (`--demo`, `--asm`, `--mem`) to the board.                                                                                                                 |

## 3. Number formats and instruction set

| Quantity           | Format              | Notes                                                                       |
| ------------------ | ------------------- | --------------------------------------------------------------------------- |
| Amplitude (re, im) | **Q1.15**, int16    | 1.0 ≈ `0x7FFF`                                                              |
| Gate coefficient   | **Q2.14**, int16    | 1.0 = `0x4000` (Q1.15 cannot represent 1.0)                                 |
| Accumulator        | 34 bit              | 4 terms x (16x16 bit), fully summed before truncation                       |
| Rounding           | `(x + 8192) >>> 14` | round-half-up, not truncation (truncation makes the state norm shrink)      |
| Saturation         | to int16            |                                                                             |
| RAM entry          | 32 bit              | `{re, im}`                                                                  |

16-bit instruction: `[opcode:4][target:4][control:4][param:4]`, where `control = F` means no control.

| Opcode   | 0   | 1 | 2 | 3 | 4 | 5 | 6 | 7  | 8  | 9          | F     |
| -------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---------- | ----- |
| Mnemonic | NOP | H | X | Y | Z | S | T | RY | RZ | MEASURE\*  | RESET |

\* `MEASURE` is reserved (currently identical to NOP). `RY`/`RZ`: theta = `param` x π/8, `param` 0..15.

Assembly syntax (comments start with `#`):

```
RESET             # state back to |0...0>
H 0               # Hadamard on qubit 0
CNOT 0 1          # control=0, target=1   (alias: CX)
CZ 0 1            # controlled gates: C + {H X Y Z S T}
CS 1 2            # controlled-S
RY 0 4            # rotation, param 0..15
CRY 0 1 8         # controlled-RY: control target param
```

## 4. Quick start

```
git clone https://github.com/Teaquilla/Quantum-Circuit-Emulator-on-an-FPGA.git
cd Quantum-Circuit-Emulator-on-an-FPGA
pip install numpy pyserial
```

**a. Model and simulation files** (outputs live in `sim/` and are committed)

```
python ref/qsim.py gen      # generate sim/*.mem
python ref/qsim.py check    # float vs fixed-point + check the trig table in gate_engine.vhd
python ref/qsim.py list     # list demo programs
```

**b. Simulate in Vivado**

```
vivado -mode batch -source scripts/create_project.tcl
```

Then change the simulation top and *Run Behavioral Simulation*; the Tcl console must show `PASS` / `ALL TESTS PASSED`:

```
set_property top tb_gate_engine [get_filesets sim_1]
set_property top tb_qcore       [get_filesets sim_1]
set_property top tb_qemu_top    [get_filesets sim_1]
```

**c. Simulate with GHDL (no Vivado needed)**

```
cd scripts && ./sim_ghdl.sh tb_qcore      # or tb_gate_engine / tb_qemu_top
```

The `-frelaxed` flag is used because `qstate_ram` uses a plain-typed shared variable.

**d. Bitstream and board.** *Run Synthesis → Run Implementation → Generate Bitstream → Open Hardware Manager → Program Device.*
The bitstream is not stored in the repo; download `qemu_top.bit` from **Releases** when available.

**e. Send a program**

```
python host/send_program.py --list                     # demos + serial ports
python host/send_program.py COM5 --demo bell           # Linux: /dev/ttyUSB1
python host/send_program.py COM5 --asm mycircuit.asm
python host/send_program.py --demo grover2 --dry-run   # no board, just print hex
```

## 5. Reading results on the LEDs

After every instruction, `qemu_top` reads all amplitudes, computes p = re² + im², and **LED[i] lights up when p(state i) ≥ threshold**.
The threshold is set by **`sw[2:0]` = k**: 0.25 / 2^k (k=0: 0.25 · k=1: 0.125 · k=2: 0.0625 · … · k=7: 1/512).
Only the first 16 states are displayed. `btnC` = reset (only LED0 lit). LED index = binary state value, with qubit 0 as the lowest bit.

| Demo           | Circuit                      | LEDs lit (sw = 000)                                           |
| -------------- | ---------------------------- | ------------------------------------------------------------- |
| `bell`         | H, CNOT                      | 0 and 3 (p = 0.5)                                             |
| `ghz4`         | H + CNOT chain               | 0 and 15                                                      |
| `grover2`      | 2-qubit Grover, target \|11> | 3 (p = 1)                                                     |
| `dj3_balanced` | Deutsch-Jozsa, f(x)=x0       | 1 and 5 (input ≠ 00 → balanced)                               |
| `dj3_constant` | Deutsch-Jozsa, f(x)=0        | 0 and 4 (input = 00 → constant)                               |
| `qft3`         | 3-qubit QFT on \|001>        | p = 0.125 for each of states 0..7 → raise to `sw = 001` or `010` |
| `rabi_04`      | RY(π/2)                      | 0 and 1 (p = 0.5)                                             |
| `rabi_08`      | RY(π)                        | 1 (p = 1)                                                     |
| `rz_04`        | H, RZ(π/2), H                | 0 and 1 (p = 0.5)                                             |
| `cry`          | X 0, CRY(π) 0→1              | 3 (p = 1)                                                     |

Rabi oscillation: send `RESET` then `RY 0 k`, k = 0..15; probability of |1> = sin²(kπ/16).

## 6. CI (GitHub Actions)

The **FPGA VHDL CI Pipeline** workflow (`.github/workflows/vhdl_ci.yml`) runs on every push and pull request to `main`, or manually via *Run workflow*. It has two jobs:

| Job                                | What it does                                                                                                                                                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Python Reference Model**         | `python ref/qsim.py check` (float vs fixed-point, cos/sin table in `gate_engine.vhd`); `qsim.py gen` followed by `git diff` to confirm the committed `sim/*.mem` match the model; `host/send_program.py --dry-run`. |
| **VHDL Analyze & Simulate (GHDL)** | Analyzes all VHDL files (`--std=08 -frelaxed`), then runs `tb_gate_engine`, `tb_qcore`, and `tb_qemu_top`. The job fails on any `FAIL`/error, or if `PASS` / `ALL TESTS PASSED` does not appear.                |

If `.mem` files go out of sync, run `python ref/qsim.py gen` and commit the result.

## Synthesis and implementation results

Target: Basys 3, 100 MHz, `N_QUBITS = 4`.

| Stage                                           | LUT   | FF    | BRAM   | DSP   | WNS (ns) | Notes                                                    |
| ----------------------------------------------- | ----- | ----- | ------ | ----- | -------- | -------------------------------------------------------- |
| Synthesis #1 (RAM inferred as flip-flops)       | 1,210 | 730   | 0      | 20    | +4.159   | `qstate_ram` = 512 FF; ctrl 740 LUT                      |
| Synthesis #2 (Xilinx TDP RAM pattern)           | 397   | 218   | 1 tile | 20    | +4.159   | `qstate_ram` became BRAM; `u_ctrl` 187 LUT; WHS +0.134 ns |
| Implementation (post-route)                     | TBD   | TBD   | TBD    | TBD   | TBD      | final WNS                                                |

The RAM fix cut LUTs by about 67% (1,210 → 397) and FFs by about 70% (730 → 218): memory that was 512 flip-flops is now one Block RAM tile,
and `u_ctrl` dropped from 740 to 187 LUTs. Synthesis #2 per module: `u_ctrl` 187 LUT / 23 FF, `u_eng` 117 LUT / 65 FF / 18 DSP.
Synthesis rows come from the *Synthesized Design* report (no routing delay); final WNS is in the *Implemented Design* report.

DSP: 18 in `gate_engine` + 2 in `qemu_top` (amplitude squaring for the LED scan).
For a scalability study, re-run synthesis with `N_QUBITS` = 6, 8, 10 and record LUT/FF/BRAM/DSP and WNS.

## 7. Board test checklist

1. Program `qemu_top.bit` → only **LED0** lights (the core runs `RESET` on its own).
2. `--demo bell` → LED0 + LED3. Press `btnC` to reset.
3. `ghz4` (LED0, LED15) → `grover2` (LED3) → `rabi_08` (LED1) → `cry` (LED3).
4. Photo/video of each demo's LEDs. Vary `sw[2:0]`.

## 8. Troubleshooting

| Symptom                                                         | Cause / fix                                                                                       |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Synthesis: `array index -1 out of range` in `qstate_ctrl.vhd`   | Fixed (`j > 0` guard in `insert_zero`). Make sure you are on the latest version.                  |
| `u_ram` becomes 512 FFs, no BRAM                                | Use the shared-variable `qstate_ram.vhd` and set its file type to **VHDL** (not 2008).            |
| xsim/GHDL: shared variable must be protected                    | xsim: file type VHDL; GHDL: add `-frelaxed`.                                                      |
| Testbench: `.mem` file not found                                | Set the `SIM_DIR` generic to the absolute path of `sim/` (see comments in `create_project.tcl`). |
| LEDs do not change when sending a program                       | Check the COM port, that no other program holds it, `RsRx` pin = B18; press `btnC` and resend.    |
| `python`: no module named `serial`                              | `pip install pyserial`.                                                                           |

## 9. Limitations and roadmap

- Not yet implemented: `MEASURE` (LFSR sampling + histogram), UART TX (send state back to the PC), CORDIC (rotations currently use a 16-angle table).
- Results are shown on LEDs only; 16-bit precision means accumulated error grows with gate count.
- Pins in `basys3.xdc` come from the Digilent master XDC; verify against the official file.
- `tb_qemu_top` uses an accelerated baud (10 clocks/bit); the 868 clocks/bit divider for 115200 baud is only tested on the board.

Roadmap: (1) `MEASURE` with a 32-bit LFSR + histogram, (2) `uart_tx` for plotting and comparison against NumPy,
(3) finer angle table or CORDIC, (4) full pipelining across pairs (≈ 1 pair/clock),
(5) Bloch/Rabi model with T1/T2 as a quantum-control extension.

## Hackathon update log

This project was started in early October 2026 and first pushed to GitHub on 6 October 2026, inside the hackathon
submission period (26 Aug - 30 Oct 2026). All of it is hackathon-period work. For clarity, the git tag **`emulator-core`**
marks the finished hardware emulator before the AI agent layer was added:

```
git log emulator-core..HEAD --oneline      # agent layer and everything after it
git diff emulator-core..HEAD --stat
```

**Emulator core (early October, tag `emulator-core`):** the VHDL emulator (`src/`), testbenches (`sim/`), Python reference model (`ref/`),
host sender (`host/`), CI pipeline, and synthesis results for 4 qubits.

**AI agent layer and follow-up work:**

| Date (2026) | Change                                                                                  | Status      |
| ----------- | --------------------------------------------------------------------------------------- | ----------- |
| 15 Oct      | Open-source `LICENSE`; repository name fixed in README badge and clone URLs             | Done        |
| 16 Oct      | English README, repo description and topics                                             | In progress |
| 17-19 Oct   | `agent/`: Nemotron planner → JSON → validator → assembly → `qsim.py` expected result    | Planned     |
| 19-22 Oct   | Tool-calling loop with self-repair; executor backends (board UART, GHDL simulation)     | Planned     |
| 21-24 Oct   | `uart_tx.vhd`: send the 16 state probabilities back to the PC; board readout            | Planned     |
| 24-26 Oct   | Demo interface (CLI or small web page)                                                  | Planned     |
| 26-28 Oct   | Demo video, final README, feedback for Nebius/NVIDIA                                    | Planned     |

*(Update this table as work lands; keep commit messages prefixed with `[hackathon]`.)*

## License

See [LICENSE](LICENSE).
