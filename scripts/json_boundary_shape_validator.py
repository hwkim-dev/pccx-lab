#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 pccxai
"""Validate documented CLI/core JSON boundary example shapes."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Callable


class ShapeError(Exception):
    """Validation failure with a human-actionable JSON path."""


@dataclass(frozen=True)
class BoundarySpec:
    kind: str
    relpath: str
    validate: Callable[[Any], None]


def child(path: str, field: str) -> str:
    return f"{path}.{field}" if path != "$" else f"$.{field}"


def indexed(path: str, index: int) -> str:
    return f"{path}[{index}]"


def type_name(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int) or isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def expect_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShapeError(f"expected object at {path}, got {type_name(value)}")
    return value


def expect_array(value: Any, path: str, *, min_items: int = 0) -> list[Any]:
    if not isinstance(value, list):
        raise ShapeError(f"expected array at {path}, got {type_name(value)}")
    if len(value) < min_items:
        raise ShapeError(f"expected at least {min_items} item(s) at {path}")
    return value


def expect_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ShapeError(f"expected string at {path}, got {type_name(value)}")
    return value


def expect_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ShapeError(f"expected boolean at {path}, got {type_name(value)}")
    return value


def expect_integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ShapeError(f"expected integer at {path}, got {type_name(value)}")
    return value


def expect_nullable_integer(value: Any, path: str) -> int | None:
    if value is None:
        return None
    return expect_integer(value, path)


def require_field(obj: dict[str, Any], path: str, field: str) -> Any:
    if field not in obj:
        raise ShapeError(f"missing required field {child(path, field)}")
    return obj[field]


def require_string_field(obj: dict[str, Any], path: str, field: str) -> str:
    return expect_string(require_field(obj, path, field), child(path, field))


def require_schema(obj: dict[str, Any], path: str, expected: str) -> None:
    actual = require_string_field(obj, path, "schemaVersion")
    if actual != expected:
        raise ShapeError(
            f"unexpected value at {child(path, 'schemaVersion')}: "
            f"expected {expected}, got {actual}"
        )


def require_string_array(value: Any, path: str, *, min_items: int = 0) -> None:
    items = expect_array(value, path, min_items=min_items)
    for index, item in enumerate(items):
        expect_string(item, indexed(path, index))


def require_object_array(value: Any, path: str, *, min_items: int = 0) -> list[dict[str, Any]]:
    items = expect_array(value, path, min_items=min_items)
    return [expect_object(item, indexed(path, index)) for index, item in enumerate(items)]


def require_string_fields(obj: dict[str, Any], path: str, fields: list[str]) -> None:
    for field in fields:
        require_string_field(obj, path, field)


def require_bool_fields(obj: dict[str, Any], path: str, fields: list[str]) -> None:
    for field in fields:
        expect_bool(require_field(obj, path, field), child(path, field))


def validate_diagnostics_envelope(value: Any) -> None:
    root = expect_object(value, "$")
    require_string_fields(root, "$", ["_note", "envelope", "tool", "source"])
    if root["envelope"] != "0":
        raise ShapeError("unexpected value at $.envelope: expected 0")
    diagnostics = require_object_array(require_field(root, "$", "diagnostics"), "$.diagnostics")
    for diagnostic in diagnostics:
        path = "$.diagnostics[]"
        expect_integer(require_field(diagnostic, path, "line"), child(path, "line"))
        expect_integer(require_field(diagnostic, path, "column"), child(path, "column"))
        require_string_fields(diagnostic, path, ["severity", "code", "message", "source"])


def validate_lab_status(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.status.v0")
    require_string_fields(root, "$", ["tool", "version", "labMode"])

    workspace = expect_object(require_field(root, "$", "workspaceState"), "$.workspaceState")
    require_string_fields(workspace, "$.workspaceState", ["state", "source", "note"])
    expect_bool(
        require_field(workspace, "$.workspaceState", "traceLoaded"),
        "$.workspaceState.traceLoaded",
    )

    workflows = require_object_array(
        require_field(root, "$", "availableWorkflows"), "$.availableWorkflows", min_items=1
    )
    for workflow in workflows:
        require_string_fields(workflow, "$.availableWorkflows[]", ["id", "label", "status", "boundary", "note"])

    plugin = expect_object(require_field(root, "$", "pluginState"), "$.pluginState")
    require_string_fields(plugin, "$.pluginState", ["status", "note"])
    expect_bool(require_field(plugin, "$.pluginState", "stableAbi"), "$.pluginState.stableAbi")

    gui = expect_object(require_field(root, "$", "guiState"), "$.guiState")
    require_string_fields(gui, "$.guiState", ["status", "style", "surface", "statusSource", "themeSchemaVersion"])
    require_string_array(require_field(gui, "$.guiState", "themePresets"), "$.guiState.themePresets")

    diagnostics = expect_object(require_field(root, "$", "diagnosticsState"), "$.diagnosticsState")
    require_string_fields(diagnostics, "$.diagnosticsState", ["status", "command", "scope"])

    evidence = expect_object(require_field(root, "$", "evidenceState"), "$.evidenceState")
    require_string_fields(evidence, "$.evidenceState", ["hardwareProbe", "timingClosure", "inference", "throughput", "note"])
    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)


def validate_theme_tokens(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.theme-tokens.v0")
    require_string_array(require_field(root, "$", "tokenSlots"), "$.tokenSlots", min_items=1)
    presets = require_object_array(require_field(root, "$", "presets"), "$.presets", min_items=1)
    for preset in presets:
        path = "$.presets[]"
        require_string_fields(preset, path, ["name", "description"])
        tokens = expect_object(require_field(preset, path, "tokens"), child(path, "tokens"))
        require_string_fields(
            tokens,
            child(path, "tokens"),
            [
                "background",
                "foreground",
                "mutedForeground",
                "border",
                "panelBackground",
                "accent",
                "danger",
                "warning",
                "success",
            ],
        )
    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)


def validate_workflow_descriptors(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.workflow-descriptors.v0")
    require_string_field(root, "$", "tool")
    descriptors = require_object_array(require_field(root, "$", "descriptors"), "$.descriptors", min_items=1)
    for descriptor in descriptors:
        path = "$.descriptors[]"
        require_string_fields(
            descriptor,
            path,
            [
                "workflowId",
                "label",
                "category",
                "description",
                "availabilityState",
                "executionState",
                "inputPolicy",
                "outputPolicy",
                "evidenceState",
            ],
        )
        require_string_array(require_field(descriptor, path, "safetyFlags"), child(path, "safetyFlags"), min_items=1)
        require_string_array(require_field(descriptor, path, "futureConsumers"), child(path, "futureConsumers"), min_items=1)
        require_string_array(require_field(descriptor, path, "limitations"), child(path, "limitations"), min_items=1)
    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)


def validate_workflow_proposals(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.workflow-proposals.v0")
    require_string_field(root, "$", "tool")
    proposals = require_object_array(require_field(root, "$", "proposals"), "$.proposals", min_items=1)
    for proposal in proposals:
        path = "$.proposals[]"
        require_string_fields(
            proposal,
            path,
            [
                "proposalId",
                "workflowId",
                "label",
                "proposalState",
                "commandKind",
                "inputSummary",
                "outputPolicy",
            ],
        )
        expect_bool(require_field(proposal, path, "approvalRequired"), child(path, "approvalRequired"))
        require_string_array(require_field(proposal, path, "fixedArgsPreview"), child(path, "fixedArgsPreview"))
        require_string_array(require_field(proposal, path, "safetyFlags"), child(path, "safetyFlags"), min_items=1)
        require_string_array(require_field(proposal, path, "expectedArtifacts"), child(path, "expectedArtifacts"))
        require_string_array(require_field(proposal, path, "limitations"), child(path, "limitations"), min_items=1)
    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)


def validate_workflow_results(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.workflow-results.v0")
    require_string_field(root, "$", "tool")
    expect_integer(require_field(root, "$", "maxEntries"), "$.maxEntries")
    summaries = require_object_array(require_field(root, "$", "summaries"), "$.summaries", min_items=1)
    for summary in summaries:
        path = "$.summaries[]"
        require_string_fields(
            summary,
            path,
            [
                "schemaVersion",
                "proposalId",
                "workflowId",
                "status",
                "startedAt",
                "finishedAt",
                "summary",
                "outputPolicy",
            ],
        )
        expect_nullable_integer(require_field(summary, path, "exitCode"), child(path, "exitCode"))
        expect_integer(require_field(summary, path, "durationMs"), child(path, "durationMs"))
        expect_bool(require_field(summary, path, "truncated"), child(path, "truncated"))
        expect_bool(require_field(summary, path, "redactionApplied"), child(path, "redactionApplied"))
        require_string_array(require_field(summary, path, "limitations"), child(path, "limitations"), min_items=1)
    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)


def validate_workflow_runner_result(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.workflow-runner-result.v0")
    require_string_fields(root, "$", ["proposalId", "workflowId", "status", "mode"])
    expect_bool(require_field(root, "$", "runnerEnabled"), "$.runnerEnabled")
    expect_nullable_integer(require_field(root, "$", "exitCode"), "$.exitCode")
    expect_integer(require_field(root, "$", "durationMs"), "$.durationMs")
    require_string_array(require_field(root, "$", "stdoutLines"), "$.stdoutLines")
    require_string_array(require_field(root, "$", "stderrLines"), "$.stderrLines")
    expect_bool(require_field(root, "$", "truncated"), "$.truncated")
    expect_bool(require_field(root, "$", "redactionApplied"), "$.redactionApplied")
    require_string_array(require_field(root, "$", "safetyFlags"), "$.safetyFlags", min_items=1)
    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)


def validate_launcher_handoff(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.diagnosticsHandoff.v0")
    require_string_fields(root, "$", ["handoffId", "handoffKind", "createdAt", "sessionId", "targetKind"])

    for field in [
        "producer",
        "consumer",
        "launcherStatusRef",
        "modelDescriptorRef",
        "runtimeDescriptorRef",
        "targetDevice",
        "privacyFlags",
        "safetyFlags",
    ]:
        expect_object(require_field(root, "$", field), child("$", field))

    producer = root["producer"]
    require_string_fields(producer, "$.producer", ["id", "role", "execution"])
    consumer = root["consumer"]
    require_string_fields(consumer, "$.consumer", ["id", "role", "boundary", "state"])

    launcher = root["launcherStatusRef"]
    require_string_fields(launcher, "$.launcherStatusRef", ["schemaVersion", "operationId", "referenceKind", "coupling"])
    model = root["modelDescriptorRef"]
    require_string_fields(model, "$.modelDescriptorRef", ["schemaVersion", "modelId", "referenceKind", "fixture"])
    runtime = root["runtimeDescriptorRef"]
    require_string_fields(runtime, "$.runtimeDescriptorRef", ["schemaVersion", "runtimeId", "referenceKind", "fixture"])
    target = root["targetDevice"]
    require_string_fields(target, "$.targetDevice", ["id", "label", "accessState", "configurationState"])

    diagnostics = require_object_array(require_field(root, "$", "diagnostics"), "$.diagnostics", min_items=1)
    for diagnostic in diagnostics:
        path = "$.diagnostics[]"
        require_string_fields(
            diagnostic,
            path,
            [
                "category",
                "diagnosticId",
                "evidenceState",
                "redactionState",
                "severity",
                "source",
                "suggestedNextAction",
                "summary",
                "title",
            ],
        )
        require_string_array(require_field(diagnostic, path, "relatedContractRefs"), child(path, "relatedContractRefs"), min_items=1)

    evidence_refs = require_object_array(require_field(root, "$", "evidenceRefs"), "$.evidenceRefs", min_items=1)
    for evidence_ref in evidence_refs:
        require_string_fields(evidence_ref, "$.evidenceRefs[]", ["evidenceId", "referenceKind", "state"])

    artifact_refs = require_object_array(require_field(root, "$", "artifactRefs"), "$.artifactRefs", min_items=1)
    for artifact_ref in artifact_refs:
        require_string_fields(artifact_ref, "$.artifactRefs[]", ["artifactId", "artifactKind", "reference", "referenceKind"])

    privacy = root["privacyFlags"]
    require_string_fields(privacy, "$.privacyFlags", ["telemetryPolicy", "uploadPolicy"])
    require_bool_fields(
        privacy,
        "$.privacyFlags",
        [
            "automaticUpload",
            "generatedBlobsIncluded",
            "modelWeightPathsIncluded",
            "privatePathsIncluded",
            "providerConfigsIncluded",
            "rawFullLogsIncluded",
            "secretsIncluded",
            "tokensIncluded",
            "userPromptsIncluded",
            "userSourceCodeIncluded",
        ],
    )

    safety = root["safetyFlags"]
    require_string_fields(
        safety,
        "$.safetyFlags",
        ["contractKind", "descriptorPolicy", "evidencePolicy", "hardwarePolicy", "runtimePolicy", "writeBackPolicy"],
    )
    require_bool_fields(
        safety,
        "$.safetyFlags",
        [
            "automaticUpload",
            "dataOnly",
            "executesLauncher",
            "executesPccxLab",
            "kv260Access",
            "lspImplemented",
            "marketplaceFlow",
            "mcpServerImplemented",
            "modelExecution",
            "networkCalls",
            "providerCalls",
            "readOnly",
            "runtimeExecution",
            "shellExecution",
            "telemetry",
            "touchesHardware",
            "writeBack",
        ],
    )

    transport = require_object_array(require_field(root, "$", "transport"), "$.transport", min_items=1)
    for item in transport:
        require_string_fields(item, "$.transport[]", ["direction", "execution", "mode", "state", "transportKind"])

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs")


def validate_launcher_device_session_status(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.deviceSessionStatus.v0")
    require_string_fields(
        root,
        "$",
        [
            "statusId",
            "fixtureVersion",
            "lastUpdatedSource",
            "targetDevice",
            "targetBoard",
            "targetModel",
            "statusAnswer",
            "connectionState",
            "discoveryState",
            "authenticationState",
            "runtimeState",
            "modelLoadState",
            "sessionState",
            "logStreamState",
            "diagnosticsState",
            "readinessState",
        ],
    )

    status_panel = require_object_array(
        require_field(root, "$", "statusPanel"), "$.statusPanel", min_items=1
    )
    for row in status_panel:
        require_string_fields(
            row,
            "$.statusPanel[]",
            ["rowId", "label", "state", "summary", "nextAction"],
        )

    discovery_paths = require_object_array(
        require_field(root, "$", "discoveryPaths"), "$.discoveryPaths", min_items=1
    )
    for path in discovery_paths:
        require_string_fields(
            path,
            "$.discoveryPaths[]",
            ["pathId", "transport", "state", "summary", "suggestedUserAction"],
        )

    flow_steps = require_object_array(
        require_field(root, "$", "connectionLaunchFlow"),
        "$.connectionLaunchFlow",
        min_items=1,
    )
    for step in flow_steps:
        expect_integer(require_field(step, "$.connectionLaunchFlow[]", "order"), "$.connectionLaunchFlow[].order")
        require_string_fields(
            step,
            "$.connectionLaunchFlow[]",
            [
                "stepId",
                "stage",
                "state",
                "userAction",
                "launcherAction",
                "statusPanelUpdate",
                "sideEffectPolicy",
            ],
        )

    errors = require_object_array(
        require_field(root, "$", "errorTaxonomy"), "$.errorTaxonomy", min_items=1
    )
    for error in errors:
        require_string_fields(
            error,
            "$.errorTaxonomy[]",
            [
                "errorId",
                "stage",
                "severity",
                "state",
                "userMessage",
                "suggestedRemediation",
                "claimBoundary",
            ],
        )

    diagnostics = expect_object(
        require_field(root, "$", "pccxLabDiagnostics"), "$.pccxLabDiagnostics"
    )
    require_string_fields(
        diagnostics,
        "$.pccxLabDiagnostics",
        ["state", "mode", "lowerBoundary"],
    )
    require_bool_fields(
        diagnostics,
        "$.pccxLabDiagnostics",
        ["automaticUpload", "executesPccxLab", "writeBack"],
    )

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    require_bool_fields(
        safety,
        "$.safetyFlags",
        [
            "authenticationAttempt",
            "automaticUpload",
            "dataOnly",
            "deterministic",
            "executesPccxLab",
            "executesSystemverilogIde",
            "firmwareFlashing",
            "generatedBlobsIncluded",
            "hardwareDumpsIncluded",
            "kv260Access",
            "modelExecution",
            "modelLoaded",
            "modelWeightPathsIncluded",
            "networkCalls",
            "networkScan",
            "opensSerialPort",
            "packageInstallation",
            "privatePathsIncluded",
            "providerCalls",
            "readOnly",
            "runtimeExecution",
            "secretsIncluded",
            "serialWrites",
            "sshExecution",
            "stableApiAbiClaim",
            "telemetry",
            "tokensIncluded",
            "touchesHardware",
            "writeBack",
            "writesArtifacts",
        ],
    )

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs")


SPECS = [
    BoundarySpec("diagnostics-envelope", "docs/examples/diagnostics-envelope.example.json", validate_diagnostics_envelope),
    BoundarySpec("lab-status", "docs/examples/run-status.example.json", validate_lab_status),
    BoundarySpec("theme-tokens", "docs/examples/theme-tokens.example.json", validate_theme_tokens),
    BoundarySpec("workflow-descriptors", "docs/examples/workflow-descriptors.example.json", validate_workflow_descriptors),
    BoundarySpec("workflow-proposals", "docs/examples/workflow-proposals.example.json", validate_workflow_proposals),
    BoundarySpec("workflow-results", "docs/examples/workflow-results.example.json", validate_workflow_results),
    BoundarySpec("workflow-runner-result", "docs/examples/workflow-runner-blocked.example.json", validate_workflow_runner_result),
    BoundarySpec("launcher-diagnostics-handoff", "docs/examples/launcher-diagnostics-handoff.example.json", validate_launcher_handoff),
    BoundarySpec("launcher-device-session-status", "docs/examples/launcher-device-session-status.example.json", validate_launcher_device_session_status),
]


def validate_root(root: Path) -> int:
    failures = 0
    for spec in SPECS:
        path = root / spec.relpath
        if not path.is_file():
            print(
                f"[FAIL]  {path} [{spec.kind}] missing boundary example",
                file=sys.stderr,
            )
            failures += 1
            continue

        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError as error:
            print(
                f"[FAIL]  {path} [{spec.kind}] invalid JSON: "
                f"line {error.lineno} column {error.colno}: {error.msg}",
                file=sys.stderr,
            )
            failures += 1
            continue

        try:
            spec.validate(value)
        except ShapeError as error:
            print(f"[FAIL]  {path} [{spec.kind}] {error}", file=sys.stderr)
            failures += 1
            continue

        print(f"[PASS]  {path} [{spec.kind}] shape ok")

    if failures:
        print(f"[FAIL]  shape validation: {failures} failure(s)", file=sys.stderr)
        return 1

    print("[INFO]  shape validation: all checks passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate pccx-lab documented JSON boundary example shapes."
    )
    parser.add_argument(
        "--root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="repository root containing docs/examples",
    )
    args = parser.parse_args()
    return validate_root(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
