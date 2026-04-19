# pccx-lab

Pre-RTL bottleneck detection, UVM co-simulation, and LLM-driven testbench generation — purpose-built for the pccx NPU architecture.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Status](https://img.shields.io/badge/Status-Work_in_Progress-yellow.svg)]()
[![Rust](https://img.shields.io/badge/Rust-Language-orange.svg)]()
[![Tauri](https://img.shields.io/badge/Tauri-Framework-teal.svg)]()

## Full documentation
Documentation is available in both English and Korean:
- **English:** [https://hwkim-dev.github.io/pccx/en/lab/](https://hwkim-dev.github.io/pccx/en/lab/)
- **Korean:** [https://hwkim-dev.github.io/pccx/ko/lab/](https://hwkim-dev.github.io/pccx/ko/lab/)

## Why one repo, not five?
Read our [design rationale](https://hwkim-dev.github.io/pccx/en/lab/design/rationale.html) on why we use a single monorepo to maintain strong module boundaries.

## Module layout
- `core/`: Pure Rust simulation and cycle estimation engine.
- `ui/`: Tauri and React-based frontend shell.
- `uvm_bridge/`: SystemVerilog/UVM boundary via DPI-C.
- `ai_copilot/`: LLM integration wrapper.

## .pccx file format
Read the open specification for our [`.pccx` binary session format](https://hwkim-dev.github.io/pccx/en/lab/pccx-format.html).

## Part of the pccx ecosystem
- [pccx (docs)](https://github.com/hwkim-dev/pccx) — NPU architecture reference
- [pccx-FPGA-NPU-LLM-kv260 (RTL)](https://github.com/hwkim-dev/pccx-FPGA-NPU-LLM-kv260) — RTL implementation
- [pccx-lab (this)](https://github.com/hwkim-dev/pccx-lab) — Performance profiler & simulator

## License
Apache 2.0 License.
