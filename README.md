# pccx-lab

CLI-first verification lab for pccx NPU trace profiling, workflow
descriptors, proposal previews, disabled runner pilots, and bounded GUI
inspection.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Status](https://img.shields.io/badge/Status-Work_in_Progress-yellow.svg)]()
[![Rust](https://img.shields.io/badge/Rust-Language-orange.svg)]()
[![Tauri](https://img.shields.io/badge/Tauri-Framework-teal.svg)]()

## Project status

**Public alpha** — `v0.1.0-alpha` is published as a prerelease. Core
crates and the Tauri shell are in active development; APIs and `.pccx`
schema may shift before `v0.2.0`. Feedback and issues are welcome.

| Entry point | Link |
| --- | --- |
| Documentation | <https://pccxai.github.io/pccx/en/lab/> |
| Releases | <https://github.com/pccxai/pccx-lab/releases> |
| `v0.1.0-alpha` notes | [docs/releases/v0.1.0-alpha.md](docs/releases/v0.1.0-alpha.md) |
| Roadmap (project board) | <https://github.com/orgs/pccxai/projects/1> |
| Contributing | <https://github.com/pccxai/.github/blob/main/CONTRIBUTING.md> |
| How to cite | [CITATION.cff](CITATION.cff) |
| Tooling status | `rust-check` + `frontend-check` required on `main`; `cargo fmt --check` enforced |
| Discussions | <https://github.com/pccxai/pccx-lab/discussions> |
| Good first issues | <https://github.com/pccxai/pccx-lab/labels/good%20first%20issue> |

## Full documentation
Documentation is available in both English and Korean:
- **English:** [https://pccxai.github.io/pccx/en/lab/](https://pccxai.github.io/pccx/en/lab/)
- **Korean:** [https://pccxai.github.io/pccx/ko/lab/](https://pccxai.github.io/pccx/ko/lab/)

## Why one repo, not five?
Read our [design rationale](https://pccxai.github.io/pccx/en/lab/design/rationale.html) on why we use a single monorepo to maintain strong module boundaries.

## Module layout
Phase 1 split the original monolithic `core` into nine focused crates under `crates/` plus a top-level `ui/`.  `pccx-core` is the single sink of the dependency graph; no crate depends on `pccx-ide` or `pccx-remote` (both are terminal binaries).

- `crates/core/` (`pccx-core`) — pure Rust core: `.pccx` format, trace parsing, hardware model, roofline, bottleneck, VCD / chrome-trace, Vivado timing.
- `crates/reports/` — Markdown / HTML / PDF rendering.
- `crates/verification/` — golden-diff + robust-reader gates for CI.
- `crates/authoring/` — ISA / API TOML compilers.
- `crates/evolve/` — EAGLE-family speculative-decoding primitives; future home of the Phase 5 DSE loop.
- `crates/lsp/` — Phase 2 IntelliSense façade (sync + async provider traits, multiplexers, subprocess spawner).
- `crates/remote/` — Phase 3 backend-daemon scaffold.
- `crates/uvm_bridge/` — SystemVerilog/UVM DPI-C boundary.
- `crates/ai_copilot/` — assistant-facing helper scaffolds; provider runtime integration is outside the CLI/core boundary.
- `ui/src-tauri/` (`pccx-ide`) — Tauri shell consuming the core / reports crates through IPC.
- `ui/` — React + Vite frontend; talks to `pccx-ide` via Tauri IPC.

See [docs/design/phase1_crate_split.md](docs/design/phase1_crate_split.md) for the full dependency graph and per-crate rationale.

## .pccx file format
Read the open specification for our [`.pccx` binary session format](https://pccxai.github.io/pccx/en/lab/pccx-format.html).

## How others consume pccx-lab

pccx-lab is CLI-first. GUI, editor-adjacent, launcher-adjacent, and
future plugin-facing workflows sit on top of the same controlled
boundary. There is no private back channel into lab internals. See
[docs/CLI_CORE_BOUNDARY.md](docs/CLI_CORE_BOUNDARY.md).

- `pccx-lab status --format json` returns deterministic lab status for
  headless tools and the GUI status panel.
- `pccx-lab theme --format json` returns the early theme-token contract
  for a theme-neutral presentation layer.
- `pccx-lab workflows --format json` returns descriptor-only workflow
  metadata for GUI, CI/headless, and future tool consumers.
- `pccx-lab workflow-proposals --format json` returns proposal-only
  previews for future approved workflow runs.
- `pccx-lab workflow-results --format json` returns summary-only
  workflow result metadata without full logs.
- `docs/examples/mcp-read-only-tool-plan.example.json` maps a future
  MCP/tool adapter to read-only CLI/core commands; it is a checked plan,
  not a runtime implementation.
- `docs/examples/mcp-read-only-analysis-flow.example.json` records a
  checked dry-run flow contract for composing existing CLI/core summaries
  into a future read-only report path; it is not a command executor or
  report writer.
- `docs/examples/mcp-read-only-report-contract.example.json` records the
  summary-only report output shape for a future read-only tool adapter;
  it is not an MCP runtime, command executor, artifact writer, or report
  writer.
- `docs/examples/mcp-permission-model.example.json` records the
  descriptor-only permission profiles and approval gates for a future
  MCP/tool adapter; it is not a permission runtime or command executor.
- `docs/examples/mcp-approval-request.example.json` records the
  approval-request and repository-mutation gate for a future MCP/tool
  adapter; it is not an MCP runtime, permission executor, command
  executor, audit logger, or write path.
- `docs/examples/mcp-approval-decision.example.json` records a denied
  approval-decision gate for a future MCP/tool adapter; it is not an MCP
  runtime, approval executor, permission executor, command executor,
  audit logger, tool invocation path, or write path.
- `docs/examples/mcp-audit-event.example.json` records the redacted
  audit-event shape for a future read-only MCP/tool adapter; it is not
  an audit logger or runtime implementation.
- `docs/examples/plugin-boundary-plan.example.json` records the plugin
  manifest and host API planning boundary; it is not a plugin loader or
  package distribution flow.
- `docs/examples/plugin-dry-run-flow.example.json` records a checked
  dry-run flow contract for future approved plugin manifest, capability,
  diagnostics, and report-panel summaries; it is not a plugin loader,
  runtime, sandbox, command executor, or report writer.
- `docs/examples/plugin-input-contract.example.json` records the
  summary-only input shape for future approved plugin diagnostics and
  report previews; it is not a plugin loader, runtime, input reader,
  command executor, artifact reader, or stable ABI.
- `docs/examples/plugin-output-contract.example.json` records the
  summary-only output shape for future plugin diagnostic, report-panel,
  and report item previews; it is not a plugin loader, runtime, command
  executor, artifact writer, or stable ABI.
- `docs/examples/plugin-permission-model.example.json` records the
  descriptor-only permission profiles, sandbox requirements, and approval
  gates for future plugin capabilities; it is not a plugin runtime,
  sandbox, or permission executor.
- `docs/examples/plugin-audit-event.example.json` records the redacted
  audit-event shape for future approved plugin metadata review; it is
  not an audit logger, plugin loader, runtime, sandbox, or command
  executor.
- `pccx-lab run-approved-workflow <proposal-id> --format json` returns
  a blocked result by default; the pilot only runs fixed allowlisted
  pccx-lab commands when explicitly enabled for local validation.
- `pccx-lab analyze <file> --format json` returns file-shape diagnostics
  through the reusable CLI/core boundary.
- `pccx-lab diagnostics-handoff validate --file <path> --format json`
  validates a launcher diagnostics handoff JSON file as a read-only
  future-consumer boundary.

The GUI is a CLI-backed GUI surface, not a separate logic island. Theme
work is experimental. Workflow descriptors, proposals, and result
summaries do not execute anything, and the runner pilot is disabled by
default. No stable plugin ABI is promised. No MCP runtime, provider
runtime, launcher runtime, or editor runtime integration is implemented
by this foundation.

The diagnostics handoff validator does not execute pccx-llm-launcher,
load plugins, call providers, touch hardware, upload telemetry, write
files, or start GUI workflows. It reads a local JSON document and emits a
deterministic summary. See
[docs/DIAGNOSTICS_HANDOFF_CONSUMER.md](docs/DIAGNOSTICS_HANDOFF_CONSUMER.md).

## Part of the pccx ecosystem
- [pccx (docs)](https://github.com/pccxai/pccx) — NPU architecture reference
- [pccx-FPGA-NPU-LLM-kv260 (RTL)](https://github.com/pccxai/pccx-FPGA-NPU-LLM-kv260) — external RTL repository
- [pccx-lab (this)](https://github.com/pccxai/pccx-lab) — CLI-first verification lab and GUI inspector

## License
Apache 2.0 License.
