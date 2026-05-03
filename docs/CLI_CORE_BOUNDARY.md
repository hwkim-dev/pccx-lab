# pccx-lab CLI/core boundary

This document defines the controlled boundary used by command-line,
desktop, editor-adjacent, CI, and future integration workflows.

## Principle

**CLI/core first. GUI second.**

The desktop shell is a thin surface over reusable core commands and
status contracts. GUI-visible workflow state should be reachable
through the same Rust core or CLI boundary that a headless consumer can
call. The GUI may render richer panels, but it must not become a
separate workflow logic island.

## Current boundary artifacts

| Artifact | Status | Notes |
|---|---|---|
| `pccx-lab status --format json` | available | Deterministic lab-status JSON from `pccx-core`. |
| `pccx-lab theme --format json` | experimental | Minimal semantic theme-token contract. |
| `pccx-lab workflows --format json` | available | Descriptor-only workflow catalog from `pccx-core`. |
| `pccx-lab workflow-proposals --format json` | available | Proposal-only workflow previews from `pccx-core`. |
| `pccx-lab workflow-results --format json` | available | Summary-only workflow result metadata from `pccx-core`. |
| `pccx-lab run-approved-workflow <proposal-id> --format json` | disabled-by-default pilot | Fixed allowlisted runner pilot; blocked unless explicitly enabled. |
| `pccx-lab analyze <file> --format json` | early scaffold | File-shape diagnostics only. |
| `pccx-lab diagnostics-handoff validate --file <path> --format json` | read-only validator | Launcher diagnostics handoff schema reader. |
| `pccx-lab device-session-status validate --file <path> --format json` | read-only validator | Launcher device/session status schema reader. |
| `docs/examples/mcp-read-only-tool-plan.example.json` | planned boundary map | Checked future MCP/tool adapter plan over fixed CLI/core commands; no runtime is implemented. |
| `docs/examples/mcp-permission-model.example.json` | planned permission map | Checked permission profiles and approval gates for a future MCP/tool adapter; no permission runtime or command executor is implemented. |
| `docs/examples/mcp-audit-event.example.json` | planned audit event shape | Checked redacted audit-event shape for a future read-only MCP/tool adapter; no logger or runtime is implemented. |
| `docs/examples/plugin-boundary-plan.example.json` | planned boundary map | Checked plugin manifest and host API plan; no plugin runtime is implemented. |
| `docs/examples/plugin-permission-model.example.json` | planned permission map | Checked plugin capability profiles, sandbox requirements, and approval gates; no plugin runtime, sandbox, or permission executor is implemented. |
| `lab_status` Tauri command | available | GUI reads the same core status struct. |
| `theme_contract` Tauri command | experimental | GUI reads the same core theme-token struct. |
| `workflow_descriptors` Tauri command | available | GUI reads descriptor-only workflow metadata. |
| `workflow_proposals` Tauri command | available | GUI reads proposal-only workflow previews. |
| `workflow_result_summaries` Tauri command | available | GUI reads summary-only workflow result metadata. |
| `workflow_runner_status` Tauri command | available | GUI reads disabled runner pilot status only. |

No stable plugin ABI is promised. No MCP runtime is implemented. No
IDE or launcher runtime integration is implemented by this foundation.
For command snippets and consumer handoff notes, see
[`docs/CLI_BOUNDARY_EXAMPLES.md`](CLI_BOUNDARY_EXAMPLES.md).

## JSON example inventory

The machine-readable inventory lives at
[`scripts/fixtures/json-boundary-inventory.json`](../scripts/fixtures/json-boundary-inventory.json).
It keeps the documented examples, shape checks, and Rust example tests
aligned.

| Boundary | Example | Producer/reader | Validation coverage |
|---|---|---|---|
| `diagnostics-envelope` | `docs/examples/diagnostics-envelope.example.json` | `pccx-lab analyze <path> --format json` | Shape validator, inventory test, Rust JSON-shape test |
| `lab-status` | `docs/examples/run-status.example.json` | `pccx-lab status --format json`; `pccx_core::status::lab_status` | Shape validator, inventory test, Rust deserialize test |
| `theme-tokens` | `docs/examples/theme-tokens.example.json` | `pccx-lab theme --format json`; `pccx_core::theme::theme_contract` | Shape validator, inventory test, Rust deserialize test |
| `workflow-descriptors` | `docs/examples/workflow-descriptors.example.json` | `pccx-lab workflows --format json`; `pccx_core::workflows::workflow_descriptors` | Shape validator, inventory test, Rust deserialize test |
| `workflow-proposals` | `docs/examples/workflow-proposals.example.json` | `pccx-lab workflow-proposals --format json`; `pccx_core::proposals::workflow_proposals` | Shape validator, inventory test, Rust deserialize test |
| `workflow-results` | `docs/examples/workflow-results.example.json` | `pccx-lab workflow-results --format json`; `pccx_core::results::workflow_result_summaries` | Shape validator, inventory test, Rust deserialize test |
| `workflow-runner-result` | `docs/examples/workflow-runner-blocked.example.json` | `pccx-lab run-approved-workflow <proposal-id> --format json`; `pccx_core::runner::blocked_workflow_result` | Shape validator, inventory test, Rust deserialize test |
| `launcher-diagnostics-handoff` | `docs/examples/launcher-diagnostics-handoff.example.json` | Reader only; `pccx_core::diagnostics_handoff::validate_diagnostics_handoff_json` | Shape validator, inventory test, Rust reader validation test |
| `launcher-device-session-status` | `docs/examples/launcher-device-session-status.example.json` | Reader only; `pccx_core::device_session_status::validate_device_session_status_json` | Shape validator, inventory test, Rust reader validation test |
| `mcp-read-only-tool-plan` | `docs/examples/mcp-read-only-tool-plan.example.json` | Reader only; planned future MCP/tool adapter boundary over existing CLI/core commands | Shape validator, inventory test, Rust JSON-shape test |
| `mcp-permission-model` | `docs/examples/mcp-permission-model.example.json` | Reader only; planned permission profiles and approval gates for a future MCP/tool adapter | Shape validator, inventory test, Rust JSON-shape test |
| `mcp-audit-event` | `docs/examples/mcp-audit-event.example.json` | Reader only; planned redacted audit-event shape for future read-only tool requests | Shape validator, inventory test, Rust JSON-shape test |
| `plugin-boundary-plan` | `docs/examples/plugin-boundary-plan.example.json` | Reader only; planned plugin manifest and host API boundary over existing CLI/core commands | Shape validator, inventory test, Rust JSON-shape test |
| `plugin-permission-model` | `docs/examples/plugin-permission-model.example.json` | Reader only; planned plugin permission profiles, sandbox requirements, and approval gates | Shape validator, inventory test, Rust JSON-shape test |

## Current cross-repo direction

- `systemverilog-ide` should consume pccx-lab outputs as data through
  CLI/core boundaries. Fragile GUI automation is outside this contract.
- `pccx-llm-launcher` handoffs, descriptors, and result summaries should
  stay contract/data oriented until checked evidence exists.
- FPGA-side evidence should be validated later as evidence, log, or
  manifest data only when available. This boundary does not access
  hardware or sibling RTL repositories.
- No launcher runtime, editor runtime, provider, MCP runtime, hardware
  execution, or plugin compatibility commitment is claimed here.

Cross-repo requests should stay in GitHub issues, pull requests,
discussions, or project comments. Prefer boundary request, contract
alignment, evidence handoff, validation follow-up, or downstream
consumer note wording. Do not use private worker or tool language as
public coordination text, and do not expose or bypass staging repository
state in public requests.

## Local workflow assistant boundary

The Workflow Assistant is a local-only planning and draft-helper surface.
It may summarize bounded trace context, propose next steps, or request
existing GUI/Tauri helper actions that are backed by Rust core
boundaries. It must not add API keys, provider selectors, provider URLs,
browser network calls, or external assistant runtimes.

Assistant wording should stay in proposal, draft, helper, and planning
terms. The GUI must remain a thin surface over CLI/core or Tauri IPC
contracts; any future MCP, launcher, editor, plugin, or provider flow
needs a separately reviewed controlled boundary before implementation.

`npm run test:static` in `ui/` guards this boundary for GUI-visible
source and copy.

## status command

```
pccx-lab status [--format json]
```

`status` emits a deterministic JSON object matching
[`docs/examples/run-status.example.json`](examples/run-status.example.json).
It is host-only and static by design: it does not scan the workspace,
load traces, probe hardware, call providers, launch editor bridges, or
run verification scripts.

Top-level fields:

| Field | Meaning |
|---|---|
| `schemaVersion` | Status schema marker, currently `pccx.lab.status.v0`. |
| `labMode` | Current operating mode, currently `cli-first-gui-foundation`. |
| `workspaceState` | Host status with `traceLoaded: false` for this static boundary. |
| `availableWorkflows` | Reusable command or core boundaries visible to the GUI. |
| `pluginState` | Placeholder plugin state with `stableAbi: false`. |
| `guiState` | Minimal native-editor style surface metadata. |
| `diagnosticsState` | Current diagnostics command and scope. |
| `evidenceState` | Conservative evidence markers for hardware, timing, inference, and throughput. |
| `limitations` | Human-readable constraints carried with the status output. |

The GUI status panel renders this data through Tauri IPC. It does not
shell out to arbitrary commands and does not duplicate workflow logic.

## theme command

```
pccx-lab theme [--format json]
```

`theme` emits the early theme-neutral presentation layer contract in
[`docs/examples/theme-tokens.example.json`](examples/theme-tokens.example.json).
The contract is intentionally small:

- `background`
- `foreground`
- `mutedForeground`
- `border`
- `panelBackground`
- `accent`
- `danger`
- `warning`
- `success`

Current preset names are:

- `native-light`
- `native-dark`
- `compact-dark`
- `quiet-light`

These are semantic slots only. They are not a heavy design system and
do not promise a stable UI contract.

## workflows command

```
pccx-lab workflows [--format json]
```

`workflows` emits a deterministic descriptor-only catalog matching
[`docs/examples/workflow-descriptors.example.json`](examples/workflow-descriptors.example.json).
Each descriptor explains what a workflow boundary is for, who may
consume it later, and which safety constraints apply.

The catalog is intentionally non-executing. It does not spawn commands,
read trace files, scan project roots, probe hardware, call providers,
open network connections, start MCP runtimes, or touch the FPGA repo.
Every entry currently carries `executionState: "descriptor_only"` and
`evidenceState: "metadata-only"`.

Descriptor fields:

| Field | Meaning |
|---|---|
| `workflowId` | Stable descriptor identifier for this early catalog. |
| `category` | Safe grouping such as `status`, `diagnostics`, `trace`, `report`, `plugin_candidate`, or `future_mcp_candidate`. |
| `availabilityState` | Current readiness marker such as `available`, `experimental`, `early-scaffold`, or `planned`. |
| `executionState` | Always `descriptor_only` in this boundary. |
| `inputPolicy` | What input the descriptor accepts. Current descriptors accept no runtime input. |
| `outputPolicy` | Bounded metadata shape expected from this boundary or a future proposal. |
| `safetyFlags` | Static flags documenting the no-execution, no-shell, no-hardware, no-network posture. |
| `futureConsumers` | Intended future consumers such as GUI, CI/headless worker, future IDE/launcher consumer, or future MCP/tool consumer. |
| `limitations` | Explicit constraints carried with the descriptor. |

## workflow-proposals command

```
pccx-lab workflow-proposals [--format json]
```

`workflow-proposals` emits deterministic proposal-only previews matching
[`docs/examples/workflow-proposals.example.json`](examples/workflow-proposals.example.json).
These objects explain what a later approved run would do, without doing
it now.

The preview keeps command information structured. `fixedArgsPreview` is
a bounded token array, not a raw shell command string. Some proposals
require no runtime input; others mark `approvalRequired: true` because a
future boundary would need an approved local input before any execution
could be considered.

Proposal fields:

| Field | Meaning |
|---|---|
| `proposalId` | Stable preview identifier for this early proposal catalog. |
| `workflowId` | Descriptor id that the proposal is derived from. |
| `proposalState` | Always `proposal_only` in this boundary. |
| `approvalRequired` | Whether a later run would require explicit approval. |
| `commandKind` | Structured command category, not a shell string. |
| `fixedArgsPreview` | Bounded argument-token preview for fixed CLI boundaries. |
| `inputSummary` | Human-readable summary of required future input. |
| `outputPolicy` | Bounded output shape expected from a future approved run. |
| `expectedArtifacts` | Empty for the proposal listing boundary. |
| `limitations` | Explicit non-execution constraints. |

The proposal command does not execute workflows, read user paths, create
artifacts, run verification, start MCP runtimes, call providers, or
touch the FPGA repo.

## workflow-results command

```
pccx-lab workflow-results [--format json]
```

`workflow-results` emits deterministic summary-only result metadata
matching
[`docs/examples/workflow-results.example.json`](examples/workflow-results.example.json).
It is intentionally not a full log cache. The summaries omit
`stdoutLines`, `stderrLines`, full logs, generated artifacts, hardware
logs, provider logs, and FPGA repo paths.

Summary fields:

| Field | Meaning |
|---|---|
| `proposalId` | Fixed proposal id or a redacted placeholder for rejected input. |
| `workflowId` | Workflow id associated with the summary. |
| `status` | Summary status such as `blocked`, `rejected`, `completed`, `failed`, or `timed_out`. |
| `exitCode` | Exit code when a run result exists; `null` for blocked or rejected entries. |
| `startedAt` / `finishedAt` | `not-recorded` until a later cache records timestamps. |
| `durationMs` | Duration carried from a run result, or `0` for deterministic metadata entries. |
| `summary` | Short human-readable outcome. |
| `truncated` | Whether underlying returned output was truncated before summarization. |
| `redactionApplied` | Whether ids or returned output required redaction. |
| `outputPolicy` | Always summary-only for this boundary. |

The current list is deterministic metadata, not a persistent execution
cache. A later cache must preserve the same summary-only posture unless
a separate bounded log contract is reviewed.

## run-approved-workflow command

```
pccx-lab run-approved-workflow <proposal-id> [--format json]
```

`run-approved-workflow` is a disabled-by-default allowlisted runner
pilot. Without explicit local runner enablement, it emits a blocked JSON
result matching
[`docs/examples/workflow-runner-blocked.example.json`](examples/workflow-runner-blocked.example.json).

Default config:

```text
workflowRunner.enabled=false
workflowRunner.mode=disabled
workflowRunner.timeoutMs=30000
workflowRunner.maxOutputLines=120
```

When explicitly enabled for local validation, the pilot accepts only
known proposal ids whose command is a fixed pccx-lab argument list:

- `proposal-lab-status-contract` -> `status --format json`
- `proposal-theme-token-contract` -> `theme --format json`
- `proposal-workflow-descriptor-catalog` -> `workflows --format json`
- `proposal-workflow-proposal-catalog` -> `workflow-proposals --format json`

The runner uses process execution without shell interpolation. It does
not accept raw commands, arbitrary args, project paths, trace paths,
hardware settings, provider settings, network settings, launcher
settings, IDE settings, or FPGA repo paths. Results include exit code,
duration, bounded stdout/stderr lines, truncation status, and redaction
status.

## analyze command

```
pccx-lab analyze <path> [--format json]
```

`analyze` emits a diagnostics envelope for a SystemVerilog file. It is
an early scaffold for host-side file-shape checks only.

| Check | Code | Severity |
|---|---|---|
| File missing or unreadable | `PCCX-IO-001` | error |
| File content is empty | `PCCX-SHAPE-001` | error |
| No `module` declaration found | `PCCX-SHAPE-002` | error |
| `module` present but `endmodule` missing | `PCCX-SCAFFOLD-003` | error |

It does not perform full semantic parsing, hardware verification,
provider calls, MCP calls, or GUI-only checks.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | No error-severity diagnostics |
| 1 | At least one error-severity diagnostic |
| 2 | I/O failure or unsupported CLI usage |

Fixtures for integration testing:

- `fixtures/ok_module.sv`
- `fixtures/missing_endmodule.sv`
- `fixtures/empty.sv`

## diagnostics-handoff command

```
pccx-lab diagnostics-handoff validate --file <path> [--format json]
```

`diagnostics-handoff validate` reads a local launcher diagnostics
handoff JSON file and emits a deterministic validation summary. It is a
future-consumer boundary for pccx-llm-launcher data, not an execution
bridge.

The validator checks:

- required handoff fields
- diagnostic severity and category values
- launcher/model/runtime descriptor references
- JSON file, stdout JSON, and read-only local artifact transport sketches
- no telemetry, no automatic upload, and no write-back flags
- no runtime execution, hardware access, provider calls, network calls,
  MCP, LSP, or marketplace flow flags
- absence of private path, secret, model weight path, and unsupported
  claim markers

The command does not execute pccx-llm-launcher, load plugins, probe
hardware, call providers, upload telemetry, write files, or start GUI
logic. It also avoids echoing the supplied file path in the JSON summary.

The checked example is
[`docs/examples/launcher-diagnostics-handoff.example.json`](examples/launcher-diagnostics-handoff.example.json).
Fixture sync with pccx-llm-launcher is manual while this boundary remains
pre-compatibility.

## device-session-status command

```
pccx-lab device-session-status validate --file <path> [--format json]
```

`device-session-status validate` reads a local launcher device/session
status JSON document and emits a bounded JSON validation summary. The
summary does not echo the input path, so private local artifact paths
are not copied into output.

The command validates:

- device connection, model load, session, diagnostics, and readiness
  status-panel rows
- planned discovery paths
- ordered connection and launch flow steps
- error taxonomy entries with user remediation and claim boundaries
- read-only, no-hardware, no-serial, no-network, no-authentication, and
  no-runtime safety flags

It exits:

| Code | Meaning |
|---|---|
| 0 | Valid launcher device/session status JSON |
| 1 | Invalid JSON shape or unsafe status content |
| 2 | CLI usage or read error |

The checked example is
[`docs/examples/launcher-device-session-status.example.json`](examples/launcher-device-session-status.example.json).

This boundary does not execute pccx-llm-launcher, invoke pccx-lab
workflows, open serial ports, scan networks, attempt authentication,
probe KV260 hardware, load model assets, start runtime code, stream
logs, upload telemetry, or write artifacts. Future GUI, launcher, or
evidence workflows may render the summary as status data, but validation
logic should remain in pccx-core or an explicit CLI/core boundary.

## MCP read-only tool plan

The checked fixture
[`docs/examples/mcp-read-only-tool-plan.example.json`](examples/mcp-read-only-tool-plan.example.json)
maps a future MCP/tool adapter onto existing CLI/core contracts. It is a
planning boundary only: no MCP server, MCP client, runtime bridge,
provider call, network call, hardware access, repository mutation, or
GUI-only automation is implemented.

The initial read-only tool list is limited to fixed CLI/core boundaries:

- `status --format json`
- `workflows --format json`
- `workflow-proposals --format json`
- `workflow-results --format json`
- `diagnostics-handoff validate --file <approved-json-file> --format json`
- `device-session-status validate --file <approved-json-file> --format json`
- `analyze <approved-source-file> --format json`

The fixture also records the permission model and audit-log plan for a
future reviewed adapter. Default mode is read-only. File inputs require
explicit approval, command arguments stay structured, and blocked actions
include public push, release/tag control, hidden background changes,
arbitrary shell commands, provider calls, network calls, hardware probes,
runtime launch, model load, and telemetry upload.

## MCP permission model boundary

[`docs/examples/mcp-permission-model.example.json`](examples/mcp-permission-model.example.json)
defines the checked permission-profile shape for a future MCP/tool
adapter. It is descriptor-only and does not add a permission runtime,
MCP server, MCP client, command executor, repository write path, or GUI
automation path.

The fixture separates three permission profiles:

- `read_only_no_input` for fixed CLI/core status and descriptor commands
  that require no user path input.
- `read_only_approved_local_file` for read-only validators that require
  explicit user approval for a local input reference.
- `write_action_pending_review` for report generation, repository
  mutation, and other write-capable actions that remain deferred until a
  separate reviewed boundary exists.

The default decision for write actions is blocked. Raw shell commands,
silent fallback, background mutation, public push, release/tag control,
artifact writes, provider calls, network calls, hardware probes, KV260
access, FPGA repo access, runtime launch, model load, and telemetry
upload are explicitly blocked in this model.

The audit policy is still a planned shape. It requires future allowed
profiles to produce redacted audit metadata, but this fixture does not
create an audit log file, capture stdout or stderr, echo private paths,
or execute any command.

## MCP audit event boundary

[`docs/examples/mcp-audit-event.example.json`](examples/mcp-audit-event.example.json)
defines the checked event shape for the future read-only MCP/tool audit
log. It is an example-only, redacted metadata boundary. It records the
request id, tool id, fixed argument preview, approved input reference
kind, outcome state, validation summary, and redaction state that a
future adapter would need to preserve.

The fixture does not create an audit log file, execute a command, start
an MCP server or client, call a provider, use the network, touch
hardware, mutate a repository, or write artifacts. It also excludes
private paths, secrets, tokens, model weight paths, stdout, and stderr.

Deferred tools such as trace open, report generation, verification
comparison, and pull-request summary preparation require separate
reviewed boundaries before they can read additional inputs, write
artifacts, or prepare public repository text.

## plugin-boundary-plan

The checked fixture
[`docs/examples/plugin-boundary-plan.example.json`](examples/plugin-boundary-plan.example.json)
defines the first plugin manifest and host API planning boundary. It is
manifest-only and descriptor-only. No plugin loader, dynamic library
loading, untrusted execution, package distribution flow, GUI-only
workflow, shell command, provider call, network call, hardware access,
launcher/editor bridge, repository mutation, artifact write, public
push, or release/tag control is implemented.

The draft manifest shape records required fields such as `pluginId`,
`name`, `version`, `entryKind`, `capabilities`, `inputContracts`,
`outputContracts`, `permissions`, and `limitations`. Capability entries
are limited to planned diagnostics, report-panel, and trace-import
metadata. Trace import remains deferred until a separate summary
boundary exists.

The host API plan keeps plugin-facing data behind existing CLI/core
contracts: lab status, workflow descriptors, diagnostics envelopes, and
workflow result summaries. The GUI may render manifest and capability
metadata only after CLI/core contracts exist. No stable plugin ABI is promised.

## plugin permission model boundary

[`docs/examples/plugin-permission-model.example.json`](examples/plugin-permission-model.example.json)
defines the checked permission-profile shape for future plugin
capabilities. It is descriptor-only. It does not add a plugin runtime,
plugin loader, sandbox implementation, permission executor, dynamic
library loading, untrusted execution, package distribution flow, or
marketplace flow.

The fixture separates read-only profile planning from blocked or
deferred capabilities:

- `manifest_review_read_only` for approved manifest and capability
  review without loading plugin code.
- `diagnostics_summary_read_only` for an approved diagnostics envelope
  producing bounded summary metadata.
- `report_panel_metadata_read_only` for approved workflow result
  summaries producing bounded panel metadata without writing artifacts.
- `trace_import_pending_review` and `write_action_pending_review` for
  capabilities that remain blocked until separate reviewed boundaries
  exist.

The sandbox policy is a requirement model, not an implementation. It
requires future execution work to define process isolation, default
network denial, default filesystem-write denial, redacted audit
metadata, and explicit approval gates before any plugin code can run.
Dynamic code loading, untrusted execution, shell commands, provider
calls, network calls, hardware probes, KV260 access, FPGA repo access,
runtime launch, model load, telemetry upload, public push,
release/tag control, repository mutation, and artifact writes are
blocked in this boundary.

## GUI foundation

The current GUI addition is only a compact verification dashboard panel
for status and theme metadata. It reads:

- `pccx_core::status::lab_status` through the `lab_status` Tauri command.
- `pccx_core::theme::theme_contract` through the `theme_contract` Tauri command.
- `pccx_core::workflows::workflow_descriptors` through the
  `workflow_descriptors` Tauri command.
- `pccx_core::proposals::workflow_proposals` through the
  `workflow_proposals` Tauri command.
- `pccx_core::results::workflow_result_summaries` through the
  `workflow_result_summaries` Tauri command.
- `pccx_core::runner::workflow_runner_status` through the
  `workflow_runner_status` Tauri command.

The panel does not run FPGA flows, provider calls, MCP flows, IDE
bridges, launcher bridges, or arbitrary shell commands.

## Deferred work

| Area | Current position |
|---|---|
| Full GUI workflows | Deferred until reusable CLI/core commands exist. |
| Plugin ABI stability | Not promised. |
| Plugin loader/runtime | Not implemented in this foundation. |
| MCP runtime | Not implemented in this foundation. |
| Editor or launcher runtime bridge | Not implemented in this foundation. |
| Hardware inference and throughput status | Not claimed by status output. |
| Timing-closure status | Not claimed by status output. |

The intended direction is a quiet engineering UI over CLI/core data,
not a separate workflow engine or a separate product surface.
