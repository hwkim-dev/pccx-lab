# pccx-lab CLI/core boundary

This document defines the controlled boundary through which external
consumers — editors, launchers, CI pipelines, and future integration
layers — interact with pccx-lab.

## Principle

**CLI/core first. GUI second.**

The Tauri shell and any future editor extensions are built on top of
the CLI/core boundary, not alongside it. There is no private back
channel from any integration layer into pccx-lab internals.

This means:

- The same `analyze`, `status`, and `traces` paths that the GUI uses
  are exactly the paths that `systemverilog-ide` and `pccx-llm-launcher`
  will consume.
- AI workers can interact with pccx-lab through a controlled MCP
  interface (planned). They do not get a separate internal surface.
- The GUI may expose richer visualisation, but any state it reads must
  be reachable through the documented CLI boundary.

## Consumers

| Consumer | Integration path | Status |
|---|---|---|
| `systemverilog-ide` | `pccx-lab analyze <file>` → diagnostics envelope | active (early-scaffold) |
| `pccx-llm-launcher` | `pccx-lab status` → run-status envelope | early-scaffold |
| VS Code extension | same CLI boundary; no separate IPC | planned |
| JetBrains / other IDE bridge | same CLI boundary | planned |
| MCP interface | controlled MCP tool server wrapping CLI boundary | planned |
| Plugin workflows | extension registry via `pccx-ai-copilot` | planned |
| CI / headless verification | `pccx-lab` subcommands, non-interactive | planned |

## In-tree boundary artifacts

Three in-tree artifacts anchor the boundary shape:

- **`crates/core/src/bin/pccx_lab.rs`** — `pccx-lab analyze` command
  (early scaffold). File-shape checks only. Emits a diagnostics
  envelope to stdout. No full semantic parser. No stable ABI.
  Binary lives in `crates/core` as a low-churn scaffold; will be
  promoted to a dedicated `crates/cli/` crate when the boundary
  matures. See [analyze command](#analyze-command-early-scaffold) below.

- **`crates/lsp/src/sv_diagnostics.rs`** — internal SV diagnostics
  provider used by the LSP layer. Its richer convention-aware checks
  (port prefix, stub detection) are intentionally not exposed through
  the `analyze` command yet; that wiring is planned for a future
  milestone when the CLI/core boundary stabilises.

- **`crates/remote/openapi.yaml`** — Phase 3 daemon scaffold. The
  `/v1/traces`, `/v1/sessions`, and `/v1/reports/{id}` paths sketch
  the run-status and trace-discovery contracts. No endpoint is wired
  yet; the file documents the intended surface.

[sv-schema]: https://github.com/pccxai/systemverilog-ide/blob/main/schema/diagnostics-v0.json

## analyze command (early scaffold)

```
pccx-lab analyze <path> [--format json]
```

**Status:** early scaffold — pre-stable output. Intended for
`systemverilog-ide` integration testing. Real analysis will grow
iteratively behind this CLI/core boundary.

**What it does (file-shape checks only):**

| Check | Code | Severity |
|---|---|---|
| File missing or unreadable | `PCCX-IO-001` | error |
| File content is empty | `PCCX-SHAPE-001` | error |
| No `module` declaration found | `PCCX-SHAPE-002` | error |
| `module` present but `endmodule` missing | `PCCX-SCAFFOLD-003` | error |

**What it does NOT do:**

- No full SystemVerilog semantic parsing.
- No port-prefix convention checks (those live in `crates/lsp`).
- No GUI dependency.
- No Vivado, xsim, or hardware requirement.

**Output shape** matches the envelope in
[`docs/examples/diagnostics-envelope.example.json`](examples/diagnostics-envelope.example.json)
and is close to `pccxai/systemverilog-ide schema/diagnostics-v0.json`.
Divergence from that schema will be resolved once cross-repo
coordination is complete; the `_note` field signals pre-stability.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | No error-severity diagnostics |
| 1 | At least one error-severity diagnostic |
| 2 | I/O failure (file missing/unreadable); envelope still emitted |

**systemverilog-ide handoff path:**

`systemverilog-ide` will discover the binary via:
1. `PCCX_LAB_BIN` environment variable (absolute path).
2. `pccx-lab` on `$PATH`.
3. Hard error — no silent fallback.

Once the binary is installed and `PCCX_LAB_BIN` or `PATH` is set,
`systemverilog-ide` can call `pccx-lab analyze <file>` and parse the
JSON envelope directly. The boundary contract (stdout JSON, exit codes,
envelope fields) is the controlled surface; internal implementation
is not exposed.

**Fixtures for integration testing:**

- `fixtures/ok_module.sv` — valid module, exit 0
- `fixtures/missing_endmodule.sv` — triggers `PCCX-SCAFFOLD-003`, exit 1
- `fixtures/empty.sv` — triggers `PCCX-SHAPE-001`, exit 1

## status command (early scaffold)

```
pccx-lab status [--format json]
```

**Status:** early scaffold — host-only, dry-run. No real KV260 probing.
No real inference. Intended for `pccx-llm-launcher` integration testing.

**What it emits:**

A JSON run-status envelope with the following top-level fields:

| Field | Value | Notes |
|---|---|---|
| `envelope` | `"0"` | envelope format version |
| `tool` | `"pccx-lab"` | always |
| `version` | from `CARGO_PKG_VERSION` | e.g. `"0.1.0"` |
| `mode` | `"host-dry-run"` | no real hardware |
| `device.kv260` | `"not-probed"` | KV260 path pending bring-up |
| `inference.status` | `"unavailable"` | deferred until timing-closed bitstream |
| `diagnostics_integration.status` | `"active"` | `analyze` boundary wired |
| `launcher_handoff.status` | `"early-scaffold"` | `status` boundary wired |
| `evidence_required` | array of strings | what must land before status changes |
| `pccx_lab_bin` | `"pccx-lab"` | binary name |
| `_note` | string | pre-stability marker; stripped by consumers |

**What it does NOT do:**

- No KV260 device probing.
- No real inference status.
- No xsim run status (xsim handoff is planned).
- No GUI dependency.

**Exit code:** always 0. Envelope is a static host-dry-run report.

**Example output:** [`docs/examples/run-status.example.json`](examples/run-status.example.json)

## Near-term contracts (planned)

The following contracts are expected to solidify before `v0.2.0`:

### Diagnostics envelope (systemverilog-ide integration target)

Path: `pccx-lab analyze <file.sv>` → stdout JSON  
Shape: `pccxai/systemverilog-ide schema/diagnostics-v0.json`  
See: [`docs/examples/diagnostics-envelope.example.json`](examples/diagnostics-envelope.example.json)

Resolution precedence (mirrors systemverilog-ide's `PCCX_LAB_BIN`
convention):

1. `PCCX_LAB_BIN` environment variable (absolute path).
2. `pccx-lab` on `$PATH`.
3. Hard error — no silent fallback to a stub when the binary is expected.

### Run-status envelope (pccx-llm-launcher integration target)

Path: `pccx-lab status` → stdout JSON  
Shape: matches `pccx-schema::HealthStatus` plus launcher state fields  
See: [`docs/examples/run-status.example.json`](examples/run-status.example.json)

### Trace-report discovery (CI / headless path)

Path: `pccx-lab traces [--format json]` → trace list  
Consumed by CI to surface `.pccx` artefacts after xsim runs.

### xsim log handoff (pccx-FPGA verification loop)

Path: `pccx-from-xsim-log --log <xsim.log> --output <out.pccx>`  
Already wired. Converts xsim stdout to a `.pccx` trace the lab can load.  
Next: surface the resulting diagnostics through `pccx-lab analyze`.

## Deferred contracts

The following are intentionally out of scope until core contracts mature:

| Contract | Notes |
|---|---|
| Stable plugin ABI | No stable plugin ABI is claimed today. Extensions use `pccx-ai-copilot` which is explicitly pre-v0.3 unstable. |
| MCP tool server | Planned. AI-assisted SystemVerilog development workflow gated on CLI boundary stability. |
| GUI visualisation layer | Tauri shell consumes the same CLI boundary. No separate internal surface. |
| AI-assisted generate / simulate / evaluate / refine loop | Planned evolutionary loop. Gated on xsim + timing evidence from `pccx-FPGA-NPU-LLM-kv260`. |

## Non-goals

- No stable plugin ABI claim today.
- No production-ready tooling claim.
- No autonomous hardware design claim.
- No vendor-specific AI worker control wording.

Public wording to use:

> "AI workers can interact with pccx-lab through a controlled MCP interface."

> "AI-assisted SystemVerilog development workflow."

> "Evolutionary generate / simulate / evaluate / refine loop."

Avoid these phrases — they are not accurate for this project at this stage:

- "Claude can directly control pccx-lab" — not accurate; AI workers interact through a controlled interface.
- "production-ready" is not accurate; use "pre-alpha" or "development preview" instead.
- "stable plugin ABI" is not stable today; use "unstable, pre-v0.3" instead.
- "timing-closed" is not yet achieved; use "timing closure pending verified bring-up".
- "KV260 inference works" is not yet verified; use "KV260 path pending verified bring-up".
