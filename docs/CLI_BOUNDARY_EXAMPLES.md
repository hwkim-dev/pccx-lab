# pccx-lab CLI boundary examples

This page shows how GUI, editor-adjacent, launcher-adjacent, CI, and
future tool consumers should read pccx-lab boundary data. It is a
handoff guide over the existing CLI/core contracts, not a new runtime
integration.

Use the full fixtures in [`docs/examples/`](examples/) as the source of
truth for field shape. The snippets below are intentionally partial.

## Consumer rule

All consumers should enter through the CLI or the typed Tauri IPC
wrappers backed by `pccx-core`.

| Consumer | Boundary to use | Rule |
|---|---|---|
| GUI | Tauri IPC wrappers over core structs | Render core data; do not duplicate workflow logic. |
| CI or headless worker | `pccx-lab ... --format json` | Parse deterministic JSON and keep logs bounded. |
| Future editor consumer | CLI JSON, then reviewed IPC if needed | Do not bypass pccx-lab or read private GUI state. |
| Future launcher consumer | Status, diagnostics handoff, proposals, summaries | Treat runtime bridges as separate reviewed work. |
| Future MCP/tool consumer | Descriptor, proposal, and read-only tool-plan JSON | Consume descriptor-only contracts until a controlled adapter exists. |
| Future plugin consumer | Plugin boundary-plan JSON | Treat manifest and capability data as planning metadata until a loader boundary exists. |

No stable plugin ABI is promised. No provider, launcher, editor, or MCP
runtime is implemented by these examples.

## Status

```bash
pccx-lab status --format json
```

Full fixture: [`run-status.example.json`](examples/run-status.example.json)

```json
{
  "schemaVersion": "pccx.lab.status.v0",
  "labMode": "cli-first-gui-foundation",
  "workspaceState": {
    "state": "host-ready",
    "traceLoaded": false,
    "source": "static-core-status"
  },
  "evidenceState": {
    "hardwareProbe": "not-run",
    "timingClosure": "not-claimed",
    "inference": "not-claimed",
    "throughput": "not-claimed"
  }
}
```

Use this for lightweight shell, GUI, CI, and future tool status. It
does not load traces or probe hardware.

## Theme

```bash
pccx-lab theme --format json
```

Full fixture: [`theme-tokens.example.json`](examples/theme-tokens.example.json)

```json
{
  "schemaVersion": "pccx.lab.theme-tokens.v0",
  "tokenSlots": [
    "background",
    "foreground",
    "mutedForeground",
    "border",
    "panelBackground",
    "accent",
    "danger",
    "warning",
    "success"
  ],
  "presets": [
    {
      "name": "native-light"
    }
  ]
}
```

Use this to keep GUI surfaces theme-neutral. Do not hardcode workflow
state into theme tokens.

## Workflow Descriptors

```bash
pccx-lab workflows --format json
```

Full fixture:
[`workflow-descriptors.example.json`](examples/workflow-descriptors.example.json)

```json
{
  "workflowId": "lab-status-contract",
  "category": "status",
  "executionState": "descriptor_only",
  "evidenceState": "metadata-only",
  "futureConsumers": [
    "GUI",
    "CI/headless worker",
    "future IDE/launcher consumer",
    "future MCP/tool consumer"
  ]
}
```

Use descriptors to discover what the lab can describe. Descriptors are
not runs and must not be treated as approval to execute anything.

## Workflow Proposals

```bash
pccx-lab workflow-proposals --format json
```

Full fixture:
[`workflow-proposals.example.json`](examples/workflow-proposals.example.json)

```json
{
  "proposalId": "proposal-lab-status-contract",
  "workflowId": "lab-status-contract",
  "proposalState": "proposal_only",
  "approvalRequired": false,
  "fixedArgsPreview": [
    "status",
    "--format",
    "json"
  ]
}
```

Use proposals to show what a later approved run would do. The preview
is structured tokens, not a raw shell string.

## MCP Read-Only Tool Plan

Full fixture:
[`mcp-read-only-tool-plan.example.json`](examples/mcp-read-only-tool-plan.example.json)

```json
{
  "schemaVersion": "pccx.lab.mcp-read-only-tool-plan.v0",
  "planState": "descriptor_only",
  "adapterState": "not_implemented",
  "defaultMode": "read_only_first",
  "toolList": [
    {
      "toolId": "lab.status.read",
      "readOnly": true,
      "approvalRequired": false,
      "fixedArgsPreview": [
        "status",
        "--format",
        "json"
      ]
    }
  ],
  "safetyFlags": {
    "descriptorOnly": true,
    "readOnly": true,
    "mcpRuntimeImplemented": false,
    "shellExecution": false,
    "writeBack": false
  }
}
```

Use this fixture as the reviewed shape for future MCP/tool adapter
planning. It does not implement an MCP runtime and does not grant
approval to execute writes, shell commands, provider calls, hardware
access, launcher/editor bridges, release/tag control, or public pushes.

## MCP Read-Only Analysis Flow

Full fixture:
[`mcp-read-only-analysis-flow.example.json`](examples/mcp-read-only-analysis-flow.example.json)

```json
{
  "schemaVersion": "pccx.lab.mcp-read-only-analysis-flow.v0",
  "flowState": "dry_run_contract",
  "adapterState": "not_implemented",
  "defaultMode": "read_only",
  "flowSteps": [
    {
      "toolId": "lab.status.read",
      "fixedArgsPreview": [
        "status",
        "--format",
        "json"
      ],
      "approvalRequired": false,
      "sideEffectPolicy": "read-only metadata"
    }
  ],
  "reportPrototype": {
    "reportState": "summary_only_fixture",
    "trackedFileMutation": false,
    "artifactWrite": false
  }
}
```

Use this fixture to review how a future read-only tool adapter can
compose existing CLI/core summaries into a bounded report. It does not
start an MCP runtime, execute commands, read local files, write reports,
mutate repositories, call providers, use the network, touch hardware, or
control release/tag actions.

## Plugin Boundary Plan

Full fixture:
[`plugin-boundary-plan.example.json`](examples/plugin-boundary-plan.example.json)

```json
{
  "schemaVersion": "pccx.lab.plugin-boundary-plan.v0",
  "planState": "descriptor_only",
  "hostMode": "cli_first_gui_second",
  "manifestDraft": {
    "schemaVersion": "pccx.lab.plugin-manifest.v0",
    "manifestState": "draft"
  },
  "loadingBoundary": {
    "state": "not_implemented",
    "pluginCodeLoaded": false,
    "untrustedExecutionAllowed": false,
    "hostApiStable": false
  },
  "safetyFlags": {
    "descriptorOnly": true,
    "readOnly": true,
    "pluginRuntimeImplemented": false,
    "marketplaceFlow": false,
    "writeBack": false
  }
}
```

Use this fixture for manifest and host API alignment before implementing
any plugin loader. It does not load plugin code, execute untrusted code,
define a package distribution flow, or grant approval to write files or
mutate repositories.

## Plugin Dry-Run Flow

Full fixture:
[`plugin-dry-run-flow.example.json`](examples/plugin-dry-run-flow.example.json)

```json
{
  "schemaVersion": "pccx.lab.plugin-dry-run-flow.v0",
  "flowState": "dry_run_contract",
  "pluginRuntimeState": "not_implemented",
  "loaderState": "not_implemented",
  "samplePluginRef": {
    "entryKind": "manifest_only",
    "codeLoaded": false
  },
  "outputPrototype": {
    "outputState": "summary_only_fixture",
    "artifactWrite": false
  },
  "safetyFlags": {
    "dryRunOnly": true,
    "pluginLoaderImplemented": false,
    "commandExecution": false
  }
}
```

Use this fixture to review how future approved plugin manifest,
capability, diagnostics, and report-panel summaries can compose into a
bounded dry-run flow. It does not load plugin code, install packages,
execute commands, implement a sandbox, write reports, mutate
repositories, call providers, use the network, touch hardware, or
control releases/tags. No stable plugin ABI is promised.

## Plugin Permission Model

Full fixture:
[`plugin-permission-model.example.json`](examples/plugin-permission-model.example.json)

```json
{
  "schemaVersion": "pccx.lab.plugin-permission-model.v0",
  "modelState": "descriptor_only",
  "pluginRuntimeState": "not_implemented",
  "defaultMode": "disabled",
  "sandboxPolicy": {
    "sandboxRequiredBeforeExecution": true,
    "networkDisabledByDefault": true,
    "filesystemWriteDisabledByDefault": true,
    "untrustedExecutionAllowed": false
  },
  "safetyFlags": {
    "descriptorOnly": true,
    "readOnly": true,
    "pluginRuntimeImplemented": false,
    "sandboxImplemented": false,
    "shellExecution": false,
    "writeBack": false
  }
}
```

Use this fixture for permission-profile and sandbox-requirement planning.
It does not implement a plugin runtime, sandbox, permission executor,
dynamic code loading, package distribution, provider/network calls,
hardware access, artifact writes, release/tag control, or public pushes.

## Workflow Results

```bash
pccx-lab workflow-results --format json
```

Full fixture:
[`workflow-results.example.json`](examples/workflow-results.example.json)

```json
{
  "proposalId": "proposal-lab-status-contract",
  "workflowId": "lab-status-contract",
  "status": "blocked",
  "outputPolicy": "summary-only; stdout and stderr lines are omitted",
  "summary": "Workflow did not run because runner execution is disabled."
}
```

Use summaries to display bounded outcomes. Full logs, generated
artifacts, provider logs, hardware logs, and private paths stay outside
this summary contract.

## Handoff Checklist

- Prefer checked-in example fixtures over copied ad hoc JSON.
- Keep command arguments structured and bounded.
- Keep GUI and future consumers read-only until a reviewed execution
  boundary exists.
- Treat diagnostics handoff data as summaries, not as launcher runtime
  control.
- Treat launcher device/session status as local status data, not as
  proof that the target, runtime, model load, or log stream exists.
- Keep future tool adapters descriptor-only until their safety boundary
  is reviewed.
- Use the MCP read-only tool-plan fixture for tool-list, permission, and
  audit-plan alignment before implementing any adapter.
- Use the plugin boundary-plan fixture for manifest and host API
  alignment before implementing any loader.

## Launcher Device/Session Status

```bash
pccx-lab device-session-status validate --file <path> --format json
```

Full fixture:
[`launcher-device-session-status.example.json`](examples/launcher-device-session-status.example.json)

```json
{
  "schemaVersion": "pccx.deviceSessionStatus.v0",
  "targetDevice": "kv260",
  "connectionState": "not_configured",
  "modelLoadState": "not_loaded",
  "sessionState": "inactive",
  "diagnosticsState": "available_as_placeholder",
  "readinessState": "blocked"
}
```

Use this for future evidence/status panels that need to show launcher
device, model, session, diagnostics, and readiness state from a local
artifact. The pccx-lab reader validates the shape and emits a bounded
summary. It does not execute launcher commands, probe hardware, open
serial ports, scan networks, authenticate, start runtime code, stream
logs, upload telemetry, or write files.
