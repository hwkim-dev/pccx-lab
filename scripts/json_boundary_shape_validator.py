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


def validate_mcp_read_only_tool_plan(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-read-only-tool-plan.v0")
    require_string_fields(
        root,
        "$",
        ["tool", "planId", "planState", "adapterState", "automationPath", "defaultMode"],
    )
    if root["planState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.planState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only_first":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only_first")

    tools = require_object_array(require_field(root, "$", "toolList"), "$.toolList", min_items=1)
    for tool in tools:
        path = "$.toolList[]"
        require_string_fields(
            tool,
            path,
            [
                "toolId",
                "label",
                "category",
                "availabilityState",
                "commandKind",
                "inputPolicy",
                "outputPolicy",
                "auditEvent",
            ],
        )
        if expect_bool(require_field(tool, path, "readOnly"), child(path, "readOnly")) is not True:
            raise ShapeError("unexpected value at $.toolList[].readOnly: expected true")
        expect_bool(require_field(tool, path, "approvalRequired"), child(path, "approvalRequired"))
        require_string_array(
            require_field(tool, path, "fixedArgsPreview"),
            child(path, "fixedArgsPreview"),
            min_items=1,
        )

    deferred_tools = require_object_array(
        require_field(root, "$", "deferredTools"), "$.deferredTools", min_items=1
    )
    for tool in deferred_tools:
        require_string_fields(tool, "$.deferredTools[]", ["toolId", "availabilityState", "reason"])

    permission = expect_object(require_field(root, "$", "permissionModel"), "$.permissionModel")
    require_string_fields(permission, "$.permissionModel", ["defaultMode", "allowedCommandKind"])
    require_bool_fields(
        permission,
        "$.permissionModel",
        [
            "readOnlyByDefault",
            "writeActionsRequireApproval",
            "pathInputRequiresApproval",
            "rawShellCommandsAllowed",
        ],
    )
    for field in ["readOnlyByDefault", "writeActionsRequireApproval", "pathInputRequiresApproval"]:
        if permission[field] is not True:
            raise ShapeError(f"unexpected value at $.permissionModel.{field}: expected true")
    if permission["rawShellCommandsAllowed"] is not False:
        raise ShapeError("unexpected value at $.permissionModel.rawShellCommandsAllowed: expected false")
    require_string_array(require_field(permission, "$.permissionModel", "blockedActions"), "$.permissionModel.blockedActions", min_items=1)

    audit = expect_object(require_field(root, "$", "auditLogPlan"), "$.auditLogPlan")
    require_string_fields(audit, "$.auditLogPlan", ["state", "eventSchema", "storagePolicy"])
    require_string_array(require_field(audit, "$.auditLogPlan", "recordedFields"), "$.auditLogPlan.recordedFields", min_items=1)
    require_string_array(require_field(audit, "$.auditLogPlan", "redactedFields"), "$.auditLogPlan.redactedFields", min_items=1)

    commands = require_object_array(
        require_field(root, "$", "commandMap"), "$.commandMap", min_items=1
    )
    for command in commands:
        path = "$.commandMap[]"
        require_string_fields(
            command,
            path,
            ["toolId", "coreBoundary", "inputKind", "sideEffectPolicy"],
        )
        require_string_array(
            require_field(command, path, "fixedArgsPreview"),
            child(path, "fixedArgsPreview"),
            min_items=1,
        )

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "modelWeightsIncluded",
        "privatePathsIncluded",
        "secretsIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_mcp_read_only_analysis_flow(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-read-only-analysis-flow.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "flowId",
            "flowState",
            "adapterState",
            "defaultMode",
            "automationPath",
        ],
    )
    if root["flowState"] != "dry_run_contract":
        raise ShapeError("unexpected value at $.flowState: expected dry_run_contract")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    refs = require_object_array(
        require_field(root, "$", "entryBoundaryRefs"),
        "$.entryBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(
            ref,
            "$.entryBoundaryRefs[]",
            ["refId", "schemaVersion", "examplePath", "state"],
        )

    steps = require_object_array(
        require_field(root, "$", "flowSteps"),
        "$.flowSteps",
        min_items=1,
    )
    seen_orders = set()
    for step in steps:
        path = "$.flowSteps[]"
        require_string_fields(
            step,
            path,
            [
                "stepId",
                "toolId",
                "commandKind",
                "inputReferenceKind",
                "expectedOutputBoundary",
                "reportContribution",
                "sideEffectPolicy",
                "auditEvent",
            ],
        )
        order = expect_integer(require_field(step, path, "order"), child(path, "order"))
        if order in seen_orders:
            raise ShapeError(f"duplicate value at {child(path, 'order')}: {order}")
        seen_orders.add(order)
        if expect_bool(require_field(step, path, "approvalRequired"), child(path, "approvalRequired")) is not False:
            raise ShapeError("unexpected value at $.flowSteps[].approvalRequired: expected false")
        require_string_array(
            require_field(step, path, "fixedArgsPreview"),
            child(path, "fixedArgsPreview"),
            min_items=1,
        )

    report = expect_object(
        require_field(root, "$", "reportPrototype"),
        "$.reportPrototype",
    )
    require_string_fields(
        report,
        "$.reportPrototype",
        ["reportState", "reportFormat", "outputPolicy"],
    )
    if report["reportState"] != "summary_only_fixture":
        raise ShapeError(
            "unexpected value at $.reportPrototype.reportState: expected summary_only_fixture"
        )
    require_bool_fields(
        report,
        "$.reportPrototype",
        [
            "trackedFileMutation",
            "artifactWrite",
            "pathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
            "privatePathsIncluded",
        ],
    )
    for field in [
        "trackedFileMutation",
        "artifactWrite",
        "pathEchoAllowed",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogIncluded",
        "privatePathsIncluded",
    ]:
        if report[field] is not False:
            raise ShapeError(f"unexpected value at $.reportPrototype.{field}: expected false")

    validation = expect_object(
        require_field(root, "$", "validationPolicy"),
        "$.validationPolicy",
    )
    require_string_fields(validation, "$.validationPolicy", ["state", "noMutationCheck", "reportReview"])
    true_validation_flags = ["approvedInputRequiredForPathSteps"]
    false_validation_flags = [
        "commandExecutionByFixture",
        "trackedFileMutationAllowed",
        "artifactWriteAllowed",
    ]
    require_bool_fields(
        validation,
        "$.validationPolicy",
        true_validation_flags + false_validation_flags,
    )
    for flag in true_validation_flags:
        if validation[flag] is not True:
            raise ShapeError(f"unexpected value at $.validationPolicy.{flag}: expected true")
    for flag in false_validation_flags:
        if validation[flag] is not False:
            raise ShapeError(f"unexpected value at $.validationPolicy.{flag}: expected false")

    require_string_array(require_field(root, "$", "blockedActions"), "$.blockedActions", min_items=1)

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "flowPrototypeOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "modelWeightsIncluded",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_mcp_read_only_report_contract(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-read-only-report-contract.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "contractId",
            "contractState",
            "adapterState",
            "defaultMode",
            "automationPath",
        ],
    )
    if root["contractState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.contractState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    refs = require_object_array(
        require_field(root, "$", "entryBoundaryRefs"),
        "$.entryBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(
            ref,
            "$.entryBoundaryRefs[]",
            ["refId", "schemaVersion", "examplePath", "state"],
        )

    sections = require_object_array(
        require_field(root, "$", "reportSections"),
        "$.reportSections",
        min_items=4,
    )
    section_ids = set()
    for section in sections:
        path = "$.reportSections[]"
        require_string_fields(
            section,
            path,
            [
                "sectionId",
                "sourceBoundary",
                "outputKind",
                "sectionState",
                "summary",
            ],
        )
        section_id = section["sectionId"]
        if section_id in section_ids:
            raise ShapeError(f"duplicate value at $.reportSections[].sectionId: {section_id}")
        section_ids.add(section_id)
        expect_integer(require_field(section, path, "itemLimit"), child(path, "itemLimit"))
        true_fields = ["summaryOnly"]
        false_fields = [
            "artifactWrite",
            "repositoryMutation",
            "privatePathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
        ]
        require_bool_fields(section, path, true_fields + false_fields)
        if section["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.reportSections[].summaryOnly: expected true")
        for field in false_fields:
            if section[field] is not False:
                raise ShapeError(f"unexpected value at $.reportSections[].{field}: expected false")
        fields = require_object_array(
            require_field(section, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.reportSections[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    sample_report = expect_object(require_field(root, "$", "sampleReport"), "$.sampleReport")
    require_string_fields(
        sample_report,
        "$.sampleReport",
        ["reportId", "reportState", "reportFormat", "overallStatus", "createdAt"],
    )
    if sample_report["reportState"] != "summary_only_fixture":
        raise ShapeError("unexpected value at $.sampleReport.reportState: expected summary_only_fixture")
    sample_false_fields = [
        "trackedFileMutation",
        "artifactWrite",
        "pathEchoAllowed",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogIncluded",
        "privatePathsIncluded",
        "generatedArtifactsIncluded",
    ]
    require_bool_fields(sample_report, "$.sampleReport", sample_false_fields)
    for field in sample_false_fields:
        if sample_report[field] is not False:
            raise ShapeError(f"unexpected value at $.sampleReport.{field}: expected false")

    sample_sections = require_object_array(
        require_field(sample_report, "$.sampleReport", "sections"),
        "$.sampleReport.sections",
        min_items=1,
    )
    for section in sample_sections:
        path = "$.sampleReport.sections[]"
        require_string_fields(
            section,
            path,
            ["sectionId", "title", "summary", "sourceRef", "evidenceState"],
        )
        if section["sectionId"] not in section_ids:
            raise ShapeError(
                "unexpected value at $.sampleReport.sections[].sectionId: "
                f"unknown section {section['sectionId']}"
            )
        expect_integer(require_field(section, path, "itemCount"), child(path, "itemCount"))
        require_bool_fields(section, path, ["pathIncluded", "artifactWrite"])
        for field in ["pathIncluded", "artifactWrite"]:
            if section[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleReport.sections[].{field}: expected false")

    output_policy = expect_object(require_field(root, "$", "outputPolicy"), "$.outputPolicy")
    require_string_fields(output_policy, "$.outputPolicy", ["state", "noMutationRule", "redactionRule"])
    true_policy_flags = ["summaryOnly", "approvalRequiredForPathInputs", "auditRequired"]
    false_policy_flags = [
        "commandExecutionByFixture",
        "trackedFileMutationAllowed",
        "artifactWriteAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
    ]
    require_bool_fields(output_policy, "$.outputPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if output_policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.outputPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if output_policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.outputPolicy.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "arbitrary-shell-command",
        "artifact-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "reportFixtureOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "modelWeightsIncluded",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_mcp_permission_model(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-permission-model.v0")
    require_string_fields(
        root,
        "$",
        ["tool", "modelId", "modelState", "adapterState", "defaultMode"],
    )
    if root["modelState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.modelState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    approval = expect_object(require_field(root, "$", "approvalPolicy"), "$.approvalPolicy")
    require_string_field(approval, "$.approvalPolicy", "state")
    approval_true_flags = [
        "userApprovalRequiredForPathInput",
        "userApprovalRequiredForWriteAction",
        "userApprovalRequiredForArtifactOutput",
    ]
    approval_false_flags = [
        "rawShellCommandsAllowed",
        "silentFallbackAllowed",
        "backgroundMutationAllowed",
    ]
    require_bool_fields(
        approval,
        "$.approvalPolicy",
        approval_true_flags + approval_false_flags,
    )
    for flag in approval_true_flags:
        if approval[flag] is not True:
            raise ShapeError(f"unexpected value at $.approvalPolicy.{flag}: expected true")
    for flag in approval_false_flags:
        if approval[flag] is not False:
            raise ShapeError(f"unexpected value at $.approvalPolicy.{flag}: expected false")

    profiles = require_object_array(
        require_field(root, "$", "permissionProfiles"),
        "$.permissionProfiles",
        min_items=1,
    )
    profile_ids = set()
    for profile in profiles:
        path = "$.permissionProfiles[]"
        require_string_fields(
            profile,
            path,
            [
                "profileId",
                "profileState",
                "inputReferenceKind",
                "outputPolicy",
            ],
        )
        profile_id = profile["profileId"]
        profile_ids.add(profile_id)
        require_string_array(
            require_field(profile, path, "allowedCommandKinds"),
            child(path, "allowedCommandKinds"),
        )
        expect_bool(
            require_field(profile, path, "requiresUserApproval"),
            child(path, "requiresUserApproval"),
        )
        if expect_bool(require_field(profile, path, "auditRequired"), child(path, "auditRequired")) is not True:
            raise ShapeError("unexpected value at $.permissionProfiles[].auditRequired: expected true")
        require_string_array(require_field(profile, path, "examples"), child(path, "examples"))

        if profile_id == "write_action_pending_review":
            if profile["profileState"] != "deferred":
                raise ShapeError(
                    "unexpected value at $.permissionProfiles[].profileState: "
                    "write_action_pending_review must be deferred"
                )
            if profile["allowedCommandKinds"] != []:
                raise ShapeError(
                    "unexpected value at $.permissionProfiles[].allowedCommandKinds: "
                    "write_action_pending_review must not allow command kinds"
                )

    actions = require_object_array(
        require_field(root, "$", "actionClasses"),
        "$.actionClasses",
        min_items=1,
    )
    for action in actions:
        path = "$.actionClasses[]"
        require_string_fields(
            action,
            path,
            ["actionClass", "permissionProfile", "defaultDecision", "sideEffectPolicy"],
        )
        if action["permissionProfile"] not in profile_ids:
            raise ShapeError(
                "unexpected value at $.actionClasses[].permissionProfile: "
                f"unknown profile {action['permissionProfile']}"
            )

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "arbitrary-shell-command",
        "public-push",
        "release-or-tag",
        "repository-write-back",
        "artifact-write",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    audit = expect_object(require_field(root, "$", "auditPolicy"), "$.auditPolicy")
    require_string_fields(audit, "$.auditPolicy", ["state", "eventSchema"])
    audit_true_flags = ["auditRequiredForAllowedProfiles", "redactionRequired"]
    audit_false_flags = ["pathEchoAllowed", "stdoutCaptureAllowed", "stderrCaptureAllowed"]
    require_bool_fields(audit, "$.auditPolicy", audit_true_flags + audit_false_flags)
    for flag in audit_true_flags:
        if audit[flag] is not True:
            raise ShapeError(f"unexpected value at $.auditPolicy.{flag}: expected true")
    for flag in audit_false_flags:
        if audit[flag] is not False:
            raise ShapeError(f"unexpected value at $.auditPolicy.{flag}: expected false")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "modelWeightsIncluded",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_mcp_approval_request(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-approval-request.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "requestId",
            "requestState",
            "adapterState",
            "defaultMode",
            "automationPath",
        ],
    )
    if root["requestState"] != "approval_required":
        raise ShapeError("unexpected value at $.requestState: expected approval_required")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    requested = expect_object(require_field(root, "$", "requestedTool"), "$.requestedTool")
    require_string_fields(
        requested,
        "$.requestedTool",
        [
            "toolId",
            "commandKind",
            "permissionProfile",
            "inputReferenceKind",
            "outputBoundary",
            "sideEffectPolicy",
        ],
    )
    if expect_bool(require_field(requested, "$.requestedTool", "approvalRequired"), "$.requestedTool.approvalRequired") is not True:
        raise ShapeError("unexpected value at $.requestedTool.approvalRequired: expected true")
    require_string_array(
        require_field(requested, "$.requestedTool", "fixedArgsPreview"),
        "$.requestedTool.fixedArgsPreview",
        min_items=1,
    )

    approval = expect_object(require_field(root, "$", "approvalPolicy"), "$.approvalPolicy")
    require_string_fields(approval, "$.approvalPolicy", ["state", "decisionState"])
    approval_true_flags = ["userApprovalRequired"]
    approval_false_flags = [
        "writeActionAllowed",
        "artifactWriteAllowed",
        "repositoryMutationAllowed",
        "pathEchoAllowed",
        "rawShellCommandsAllowed",
        "silentFallbackAllowed",
        "backgroundMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(approval, "$.approvalPolicy", approval_true_flags + approval_false_flags)
    if approval["userApprovalRequired"] is not True:
        raise ShapeError("unexpected value at $.approvalPolicy.userApprovalRequired: expected true")
    for flag in approval_false_flags:
        if approval[flag] is not False:
            raise ShapeError(f"unexpected value at $.approvalPolicy.{flag}: expected false")

    mutation = expect_object(
        require_field(root, "$", "repositoryMutationBoundary"),
        "$.repositoryMutationBoundary",
    )
    require_string_fields(mutation, "$.repositoryMutationBoundary", ["state", "requiredBeforeWrite"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "artifactWriteAllowed",
        "writeBackAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.repositoryMutationBoundary", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.repositoryMutationBoundary.{flag}: expected false")

    redaction = expect_object(require_field(root, "$", "redactionPolicy"), "$.redactionPolicy")
    require_string_field(redaction, "$.redactionPolicy", "state")
    redaction_true_flags = ["approvedInputRefOnly"]
    redaction_false_flags = [
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "modelWeightPathsIncluded",
    ]
    require_bool_fields(redaction, "$.redactionPolicy", redaction_true_flags + redaction_false_flags)
    if redaction["approvedInputRefOnly"] is not True:
        raise ShapeError("unexpected value at $.redactionPolicy.approvedInputRefOnly: expected true")
    for flag in redaction_false_flags:
        if redaction[flag] is not False:
            raise ShapeError(f"unexpected value at $.redactionPolicy.{flag}: expected false")

    checks = require_object_array(
        require_field(root, "$", "approvalChecklist"),
        "$.approvalChecklist",
        min_items=1,
    )
    for check in checks:
        require_string_fields(
            check,
            "$.approvalChecklist[]",
            ["checkId", "state", "requiredBefore", "summary"],
        )

    audit_ref = expect_object(require_field(root, "$", "auditEventRef"), "$.auditEventRef")
    require_string_fields(
        audit_ref,
        "$.auditEventRef",
        ["schemaVersion", "examplePath", "eventState", "storageState"],
    )

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "permission-executor",
        "arbitrary-shell-command",
        "artifact-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "approvalFixtureOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "permissionExecutorImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "modelWeightsIncluded",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_mcp_approval_decision(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-approval-decision.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "decisionId",
            "requestId",
            "decisionState",
            "adapterState",
            "defaultMode",
            "automationPath",
        ],
    )
    if root["decisionState"] != "denied":
        raise ShapeError("unexpected value at $.decisionState: expected denied")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    request_ref = expect_object(require_field(root, "$", "sourceRequestRef"), "$.sourceRequestRef")
    require_string_fields(
        request_ref,
        "$.sourceRequestRef",
        ["schemaVersion", "examplePath", "requestState"],
    )

    decision = expect_object(require_field(root, "$", "decisionPolicy"), "$.decisionPolicy")
    require_string_fields(decision, "$.decisionPolicy", ["state", "decisionSource"])
    decision_true_flags = ["userDecisionRequired", "denied"]
    decision_false_flags = [
        "approved",
        "toolInvocationAllowed",
        "writeActionAllowed",
        "artifactWriteAllowed",
        "repositoryMutationAllowed",
        "pathEchoAllowed",
        "rawShellCommandsAllowed",
        "silentFallbackAllowed",
        "backgroundMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(decision, "$.decisionPolicy", decision_true_flags + decision_false_flags)
    for flag in decision_true_flags:
        if decision[flag] is not True:
            raise ShapeError(f"unexpected value at $.decisionPolicy.{flag}: expected true")
    for flag in decision_false_flags:
        if decision[flag] is not False:
            raise ShapeError(f"unexpected value at $.decisionPolicy.{flag}: expected false")

    inputs = expect_object(require_field(root, "$", "decisionInputs"), "$.decisionInputs")
    require_string_field(inputs, "$.decisionInputs", "inputReferenceKind")
    input_true_flags = ["inputRefOnly"]
    input_false_flags = [
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "modelWeightPathsIncluded",
    ]
    require_bool_fields(inputs, "$.decisionInputs", input_true_flags + input_false_flags)
    if inputs["inputRefOnly"] is not True:
        raise ShapeError("unexpected value at $.decisionInputs.inputRefOnly: expected true")
    for flag in input_false_flags:
        if inputs[flag] is not False:
            raise ShapeError(f"unexpected value at $.decisionInputs.{flag}: expected false")

    gate = expect_object(require_field(root, "$", "toolInvocationGate"), "$.toolInvocationGate")
    require_string_fields(gate, "$.toolInvocationGate", ["state", "requiredBeforeInvocation"])
    gate_false_flags = [
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "networkCallAllowed",
        "providerCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
    ]
    require_bool_fields(gate, "$.toolInvocationGate", gate_false_flags)
    for flag in gate_false_flags:
        if gate[flag] is not False:
            raise ShapeError(f"unexpected value at $.toolInvocationGate.{flag}: expected false")

    mutation = expect_object(
        require_field(root, "$", "repositoryMutationBoundary"),
        "$.repositoryMutationBoundary",
    )
    require_string_fields(mutation, "$.repositoryMutationBoundary", ["state", "requiredBeforeWrite"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "artifactWriteAllowed",
        "writeBackAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.repositoryMutationBoundary", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.repositoryMutationBoundary.{flag}: expected false")

    audit_ref = expect_object(require_field(root, "$", "auditEventRef"), "$.auditEventRef")
    require_string_fields(
        audit_ref,
        "$.auditEventRef",
        ["schemaVersion", "examplePath", "eventState", "storageState"],
    )

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "approval-executor",
        "permission-executor",
        "arbitrary-shell-command",
        "tool-invocation",
        "artifact-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "approvalDecisionFixtureOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "approvalExecutorImplemented",
        "permissionExecutorImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "modelWeightsIncluded",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_mcp_blocked_invocation_result(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-blocked-invocation-result.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "resultId",
            "requestId",
            "decisionId",
            "resultState",
            "adapterState",
            "defaultMode",
            "automationPath",
        ],
    )
    if root["resultState"] != "blocked_by_policy":
        raise ShapeError("unexpected value at $.resultState: expected blocked_by_policy")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    request_ref = expect_object(require_field(root, "$", "sourceRequestRef"), "$.sourceRequestRef")
    require_string_fields(
        request_ref,
        "$.sourceRequestRef",
        ["schemaVersion", "examplePath", "requestState"],
    )

    decision_ref = expect_object(require_field(root, "$", "sourceDecisionRef"), "$.sourceDecisionRef")
    require_string_fields(
        decision_ref,
        "$.sourceDecisionRef",
        ["schemaVersion", "examplePath", "decisionState"],
    )
    if decision_ref["decisionState"] != "denied":
        raise ShapeError("unexpected value at $.sourceDecisionRef.decisionState: expected denied")

    tool_request = expect_object(require_field(root, "$", "toolRequest"), "$.toolRequest")
    require_string_fields(
        tool_request,
        "$.toolRequest",
        ["toolId", "commandKind", "approvedInputReferenceKind"],
    )
    require_string_array(require_field(tool_request, "$.toolRequest", "fixedArgsPreview"), "$.toolRequest.fixedArgsPreview")
    for field in ["pathEchoAllowed", "rawShellCommandAllowed"]:
        if expect_bool(require_field(tool_request, "$.toolRequest", field), f"$.toolRequest.{field}") is not False:
            raise ShapeError(f"unexpected value at $.toolRequest.{field}: expected false")

    blocked = expect_object(require_field(root, "$", "blockedResult"), "$.blockedResult")
    require_string_fields(blocked, "$.blockedResult", ["state", "reason", "summary"])
    if blocked["state"] != "not_executed":
        raise ShapeError("unexpected value at $.blockedResult.state: expected not_executed")
    expect_nullable_integer(require_field(blocked, "$.blockedResult", "exitCode"), "$.blockedResult.exitCode")
    blocked_true_flags = ["summaryOnly"]
    blocked_false_flags = [
        "toolInvocationAttempted",
        "commandExecutionAttempted",
        "localFileReadAttempted",
        "artifactWriteAttempted",
        "repositoryMutationAttempted",
    ]
    require_bool_fields(blocked, "$.blockedResult", blocked_true_flags + blocked_false_flags)
    if blocked["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.blockedResult.summaryOnly: expected true")
    for flag in blocked_false_flags:
        if blocked[flag] is not False:
            raise ShapeError(f"unexpected value at $.blockedResult.{flag}: expected false")

    output = expect_object(require_field(root, "$", "outputPreview"), "$.outputPreview")
    require_string_fields(output, "$.outputPreview", ["state", "resultFormat"])
    output_false_flags = [
        "diagnosticsProduced",
        "reportProduced",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "privatePathsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(output, "$.outputPreview", output_false_flags)
    for flag in output_false_flags:
        if output[flag] is not False:
            raise ShapeError(f"unexpected value at $.outputPreview.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactWriteAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    audit_ref = expect_object(require_field(root, "$", "auditEventRef"), "$.auditEventRef")
    require_string_fields(
        audit_ref,
        "$.auditEventRef",
        ["schemaVersion", "examplePath", "eventState", "storageState"],
    )

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "approval-executor",
        "permission-executor",
        "arbitrary-shell-command",
        "tool-invocation",
        "command-execution",
        "local-file-read",
        "artifact-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "blockedResultFixtureOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "approvalExecutorImplemented",
        "permissionExecutorImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "modelWeightsIncluded",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "diagnosticsProduced",
        "reportProduced",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_mcp_audit_event(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-audit-event.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "eventId",
            "requestId",
            "eventState",
            "adapterState",
            "timestamp",
            "toolId",
            "auditEvent",
            "commandKind",
            "approvedInputReferenceKind",
            "outcomeState",
            "sideEffectPolicy",
        ],
    )
    if root["eventState"] != "example_only":
        raise ShapeError("unexpected value at $.eventState: expected example_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["outcomeState"] != "not_executed":
        raise ShapeError("unexpected value at $.outcomeState: expected not_executed")

    require_string_array(
        require_field(root, "$", "fixedArgsPreview"),
        "$.fixedArgsPreview",
        min_items=1,
    )

    validation = expect_object(
        require_field(root, "$", "validationSummary"),
        "$.validationSummary",
    )
    require_string_fields(validation, "$.validationSummary", ["state", "summary"])
    require_bool_fields(
        validation,
        "$.validationSummary",
        ["summaryOnly", "pathEchoed", "stdoutCaptured", "stderrCaptured", "artifactWritten"],
    )
    if validation["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.validationSummary.summaryOnly: expected true")
    for field in ["pathEchoed", "stdoutCaptured", "stderrCaptured", "artifactWritten"]:
        if validation[field] is not False:
            raise ShapeError(f"unexpected value at $.validationSummary.{field}: expected false")

    redaction = expect_object(require_field(root, "$", "redactionState"), "$.redactionState")
    require_string_field(redaction, "$.redactionState", "state")
    redaction_false_flags = [
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "modelWeightPathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
    ]
    require_bool_fields(redaction, "$.redactionState", redaction_false_flags)
    for flag in redaction_false_flags:
        if redaction[flag] is not False:
            raise ShapeError(f"unexpected value at $.redactionState.{flag}: expected false")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_plugin_permission_model(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-permission-model.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "modelId",
            "modelState",
            "pluginRuntimeState",
            "defaultMode",
            "manifestSource",
        ],
    )
    if root["modelState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.modelState: expected descriptor_only")
    if root["pluginRuntimeState"] != "not_implemented":
        raise ShapeError("unexpected value at $.pluginRuntimeState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")

    approval = expect_object(require_field(root, "$", "approvalPolicy"), "$.approvalPolicy")
    require_string_field(approval, "$.approvalPolicy", "state")
    approval_true_flags = [
        "manifestApprovalRequired",
        "localInputApprovalRequired",
        "capabilityEscalationRequiresReview",
        "artifactOutputRequiresReview",
    ]
    approval_false_flags = [
        "rawShellCommandsAllowed",
        "silentFallbackAllowed",
        "backgroundMutationAllowed",
        "unreviewedCapabilityAllowed",
    ]
    require_bool_fields(approval, "$.approvalPolicy", approval_true_flags + approval_false_flags)
    for flag in approval_true_flags:
        if approval[flag] is not True:
            raise ShapeError(f"unexpected value at $.approvalPolicy.{flag}: expected true")
    for flag in approval_false_flags:
        if approval[flag] is not False:
            raise ShapeError(f"unexpected value at $.approvalPolicy.{flag}: expected false")

    sandbox = expect_object(require_field(root, "$", "sandboxPolicy"), "$.sandboxPolicy")
    require_string_field(sandbox, "$.sandboxPolicy", "state")
    sandbox_true_flags = [
        "sandboxRequiredBeforeExecution",
        "processIsolationRequired",
        "networkDisabledByDefault",
        "filesystemWriteDisabledByDefault",
    ]
    sandbox_false_flags = [
        "dynamicLibraryLoadAllowed",
        "untrustedExecutionAllowed",
        "privatePathEchoAllowed",
        "stdoutCaptureAllowed",
        "stderrCaptureAllowed",
    ]
    require_bool_fields(sandbox, "$.sandboxPolicy", sandbox_true_flags + sandbox_false_flags)
    for flag in sandbox_true_flags:
        if sandbox[flag] is not True:
            raise ShapeError(f"unexpected value at $.sandboxPolicy.{flag}: expected true")
    for flag in sandbox_false_flags:
        if sandbox[flag] is not False:
            raise ShapeError(f"unexpected value at $.sandboxPolicy.{flag}: expected false")

    profiles = require_object_array(
        require_field(root, "$", "permissionProfiles"),
        "$.permissionProfiles",
        min_items=1,
    )
    profile_ids = set()
    for profile in profiles:
        path = "$.permissionProfiles[]"
        require_string_fields(
            profile,
            path,
            [
                "profileId",
                "profileState",
                "inputReferenceKind",
                "outputPolicy",
            ],
        )
        profile_id = profile["profileId"]
        profile_ids.add(profile_id)
        expect_bool(
            require_field(profile, path, "requiresUserApproval"),
            child(path, "requiresUserApproval"),
        )
        if expect_bool(require_field(profile, path, "auditRequired"), child(path, "auditRequired")) is not True:
            raise ShapeError("unexpected value at $.permissionProfiles[].auditRequired: expected true")
        require_string_array(
            require_field(profile, path, "allowedCapabilityIds"),
            child(path, "allowedCapabilityIds"),
        )
        require_string_array(
            require_field(profile, path, "allowedInputContracts"),
            child(path, "allowedInputContracts"),
        )
        require_string_array(
            require_field(profile, path, "allowedOutputContracts"),
            child(path, "allowedOutputContracts"),
        )
        require_string_array(require_field(profile, path, "examples"), child(path, "examples"), min_items=1)

        if profile_id in ["trace_import_pending_review", "write_action_pending_review"]:
            if profile["profileState"] != "deferred":
                raise ShapeError(
                    "unexpected value at $.permissionProfiles[].profileState: "
                    f"{profile_id} must be deferred"
                )
            for field in ["allowedCapabilityIds", "allowedInputContracts", "allowedOutputContracts"]:
                if profile[field] != []:
                    raise ShapeError(
                        "unexpected value at $.permissionProfiles[]."
                        f"{field}: {profile_id} must not allow entries"
                    )

    gates = require_object_array(
        require_field(root, "$", "capabilityGates"),
        "$.capabilityGates",
        min_items=1,
    )
    for gate in gates:
        path = "$.capabilityGates[]"
        require_string_fields(
            gate,
            path,
            ["capabilityId", "permissionProfile", "defaultDecision", "sideEffectPolicy"],
        )
        if gate["permissionProfile"] not in profile_ids:
            raise ShapeError(
                "unexpected value at $.capabilityGates[].permissionProfile: "
                f"unknown profile {gate['permissionProfile']}"
            )

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "dynamic-code-load",
        "untrusted-execution",
        "plugin-package-install",
        "marketplace-flow",
        "arbitrary-shell-command",
        "repository-write-back",
        "artifact-write",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    audit = expect_object(require_field(root, "$", "auditPolicy"), "$.auditPolicy")
    require_string_fields(audit, "$.auditPolicy", ["state", "eventSchema"])
    audit_true_flags = ["auditRequiredForAllowedProfiles", "redactionRequired"]
    audit_false_flags = [
        "privatePathEchoAllowed",
        "stdoutCaptureAllowed",
        "stderrCaptureAllowed",
        "artifactPathEchoAllowed",
    ]
    require_bool_fields(audit, "$.auditPolicy", audit_true_flags + audit_false_flags)
    for flag in audit_true_flags:
        if audit[flag] is not True:
            raise ShapeError(f"unexpected value at $.auditPolicy.{flag}: expected true")
    for flag in audit_false_flags:
        if audit[flag] is not False:
            raise ShapeError(f"unexpected value at $.auditPolicy.{flag}: expected false")

    external = expect_object(
        require_field(root, "$", "externalIntegrationBoundary"),
        "$.externalIntegrationBoundary",
    )
    require_string_fields(external, "$.externalIntegrationBoundary", ["state", "rule"])
    require_string_array(
        require_field(external, "$.externalIntegrationBoundary", "consumers"),
        "$.externalIntegrationBoundary.consumers",
        min_items=1,
    )

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "untrustedExecutionAllowed",
        "sandboxImplemented",
        "stablePluginAbiPromised",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "secretsIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_plugin_audit_event(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-audit-event.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "eventId",
            "requestId",
            "eventState",
            "pluginRuntimeState",
            "loaderState",
            "timestamp",
            "pluginId",
            "capabilityId",
            "auditEvent",
            "commandKind",
            "approvedInputReferenceKind",
            "permissionProfile",
            "outcomeState",
            "sideEffectPolicy",
        ],
    )
    if root["eventState"] != "example_only":
        raise ShapeError("unexpected value at $.eventState: expected example_only")
    if root["pluginRuntimeState"] != "not_implemented":
        raise ShapeError("unexpected value at $.pluginRuntimeState: expected not_implemented")
    if root["loaderState"] != "not_implemented":
        raise ShapeError("unexpected value at $.loaderState: expected not_implemented")
    if root["outcomeState"] != "not_executed":
        raise ShapeError("unexpected value at $.outcomeState: expected not_executed")

    require_string_array(
        require_field(root, "$", "fixedArgsPreview"),
        "$.fixedArgsPreview",
        min_items=1,
    )

    validation = expect_object(
        require_field(root, "$", "validationSummary"),
        "$.validationSummary",
    )
    require_string_fields(validation, "$.validationSummary", ["state", "summary"])
    validation_true_flags = ["summaryOnly"]
    validation_false_flags = [
        "pathEchoed",
        "stdoutCaptured",
        "stderrCaptured",
        "artifactWritten",
        "pluginCodeLoaded",
        "packageInstalled",
        "dynamicLibrariesLoaded",
    ]
    require_bool_fields(
        validation,
        "$.validationSummary",
        validation_true_flags + validation_false_flags,
    )
    if validation["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.validationSummary.summaryOnly: expected true")
    for field in validation_false_flags:
        if validation[field] is not False:
            raise ShapeError(f"unexpected value at $.validationSummary.{field}: expected false")

    redaction = expect_object(require_field(root, "$", "redactionState"), "$.redactionState")
    require_string_field(redaction, "$.redactionState", "state")
    redaction_false_flags = [
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "modelWeightPathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(redaction, "$.redactionState", redaction_false_flags)
    for flag in redaction_false_flags:
        if redaction[flag] is not False:
            raise ShapeError(f"unexpected value at $.redactionState.{flag}: expected false")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "auditFixtureOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "stablePluginAbiPromised",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_plugin_boundary_plan(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-boundary-plan.v0")
    require_string_fields(root, "$", ["tool", "planId", "planState", "hostMode"])
    if root["planState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.planState: expected descriptor_only")
    if root["hostMode"] != "cli_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_first_gui_second")

    manifest = expect_object(require_field(root, "$", "manifestDraft"), "$.manifestDraft")
    require_string_fields(
        manifest,
        "$.manifestDraft",
        ["schemaVersion", "manifestState"],
    )
    require_string_array(
        require_field(manifest, "$.manifestDraft", "requiredFields"),
        "$.manifestDraft.requiredFields",
        min_items=1,
    )
    require_string_array(
        require_field(manifest, "$.manifestDraft", "optionalFields"),
        "$.manifestDraft.optionalFields",
    )
    require_string_array(
        require_field(manifest, "$.manifestDraft", "limitations"),
        "$.manifestDraft.limitations",
        min_items=1,
    )

    capabilities = require_object_array(
        require_field(root, "$", "capabilityCatalog"),
        "$.capabilityCatalog",
        min_items=1,
    )
    for capability in capabilities:
        require_string_fields(
            capability,
            "$.capabilityCatalog[]",
            [
                "capabilityId",
                "capabilityState",
                "inputPolicy",
                "outputPolicy",
                "permissionProfile",
            ],
        )

    loading = expect_object(require_field(root, "$", "loadingBoundary"), "$.loadingBoundary")
    require_string_fields(loading, "$.loadingBoundary", ["state", "defaultMode"])
    require_string_array(
        require_field(loading, "$.loadingBoundary", "allowedDuringPlan"),
        "$.loadingBoundary.allowedDuringPlan",
        min_items=1,
    )
    require_bool_fields(
        loading,
        "$.loadingBoundary",
        [
            "pluginCodeLoaded",
            "dynamicLibrariesLoaded",
            "untrustedExecutionAllowed",
            "hostApiStable",
        ],
    )
    for field in [
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "untrustedExecutionAllowed",
        "hostApiStable",
    ]:
        if loading[field] is not False:
            raise ShapeError(f"unexpected value at $.loadingBoundary.{field}: expected false")

    host_api = expect_object(require_field(root, "$", "hostApiBoundary"), "$.hostApiBoundary")
    require_string_field(host_api, "$.hostApiBoundary", "state")
    exposed = require_object_array(
        require_field(host_api, "$.hostApiBoundary", "exposedContracts"),
        "$.hostApiBoundary.exposedContracts",
        min_items=1,
    )
    for contract in exposed:
        path = "$.hostApiBoundary.exposedContracts[]"
        require_string_fields(contract, path, ["contractId", "coreBoundary", "exposureState"])
        if expect_bool(require_field(contract, path, "readOnly"), child(path, "readOnly")) is not True:
            raise ShapeError("unexpected value at $.hostApiBoundary.exposedContracts[].readOnly: expected true")
    require_string_array(
        require_field(host_api, "$.hostApiBoundary", "forbiddenAccess"),
        "$.hostApiBoundary.forbiddenAccess",
        min_items=1,
    )

    sample = expect_object(require_field(root, "$", "samplePluginPlan"), "$.samplePluginPlan")
    require_string_fields(
        sample,
        "$.samplePluginPlan",
        [
            "pluginId",
            "sampleState",
            "entryKind",
            "inputContract",
            "outputContract",
            "executionState",
        ],
    )
    if sample["executionState"] != "not_implemented":
        raise ShapeError("unexpected value at $.samplePluginPlan.executionState: expected not_implemented")
    require_string_array(
        require_field(sample, "$.samplePluginPlan", "limitations"),
        "$.samplePluginPlan.limitations",
        min_items=1,
    )

    security = expect_object(require_field(root, "$", "securityModel"), "$.securityModel")
    require_string_field(security, "$.securityModel", "state")
    require_bool_fields(
        security,
        "$.securityModel",
        [
            "sandboxRequired",
            "explicitApprovalRequired",
            "permissionsDefaultDeny",
            "rawShellCommandsAllowed",
            "networkAccessAllowed",
            "fileWriteAllowed",
        ],
    )
    for field in ["sandboxRequired", "explicitApprovalRequired", "permissionsDefaultDeny"]:
        if security[field] is not True:
            raise ShapeError(f"unexpected value at $.securityModel.{field}: expected true")
    for field in ["rawShellCommandsAllowed", "networkAccessAllowed", "fileWriteAllowed"]:
        if security[field] is not False:
            raise ShapeError(f"unexpected value at $.securityModel.{field}: expected false")
    require_string_array(
        require_field(security, "$.securityModel", "blockedActions"),
        "$.securityModel.blockedActions",
        min_items=1,
    )

    cli = expect_object(require_field(root, "$", "cliFirstPlan"), "$.cliFirstPlan")
    require_string_fields(cli, "$.cliFirstPlan", ["state", "guiPolicy"])
    commands = require_object_array(
        require_field(cli, "$.cliFirstPlan", "proposedCommands"),
        "$.cliFirstPlan.proposedCommands",
        min_items=1,
    )
    for command in commands:
        path = "$.cliFirstPlan.proposedCommands[]"
        require_string_fields(command, path, ["commandId", "availabilityState", "sideEffectPolicy"])
        require_string_array(
            require_field(command, path, "fixedArgsPreview"),
            child(path, "fixedArgsPreview"),
            min_items=1,
        )

    external = expect_object(
        require_field(root, "$", "externalIntegrationBoundary"),
        "$.externalIntegrationBoundary",
    )
    require_string_fields(external, "$.externalIntegrationBoundary", ["state", "rule"])
    require_string_array(
        require_field(external, "$.externalIntegrationBoundary", "consumers"),
        "$.externalIntegrationBoundary.consumers",
        min_items=1,
    )

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "untrustedExecutionAllowed",
        "stablePluginAbiPromised",
        "marketplaceFlow",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "modelExecution",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_plugin_dry_run_flow(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-dry-run-flow.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "flowId",
            "flowState",
            "pluginRuntimeState",
            "loaderState",
            "defaultMode",
            "hostMode",
            "automationPath",
        ],
    )
    if root["flowState"] != "dry_run_contract":
        raise ShapeError("unexpected value at $.flowState: expected dry_run_contract")
    if root["pluginRuntimeState"] != "not_implemented":
        raise ShapeError("unexpected value at $.pluginRuntimeState: expected not_implemented")
    if root["loaderState"] != "not_implemented":
        raise ShapeError("unexpected value at $.loaderState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")
    if root["hostMode"] != "cli_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "entryBoundaryRefs"),
        "$.entryBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(
            ref,
            "$.entryBoundaryRefs[]",
            ["refId", "schemaVersion", "examplePath", "state"],
        )

    sample = expect_object(require_field(root, "$", "samplePluginRef"), "$.samplePluginRef")
    require_string_fields(sample, "$.samplePluginRef", ["pluginId", "manifestState", "entryKind"])
    require_bool_fields(
        sample,
        "$.samplePluginRef",
        ["codeLoaded", "packageInstalled", "dynamicLibrariesLoaded"],
    )
    for field in ["codeLoaded", "packageInstalled", "dynamicLibrariesLoaded"]:
        if sample[field] is not False:
            raise ShapeError(f"unexpected value at $.samplePluginRef.{field}: expected false")

    steps = require_object_array(
        require_field(root, "$", "flowSteps"),
        "$.flowSteps",
        min_items=1,
    )
    seen_orders = set()
    for step in steps:
        path = "$.flowSteps[]"
        require_string_fields(
            step,
            path,
            [
                "stepId",
                "toolId",
                "commandKind",
                "inputReferenceKind",
                "expectedOutputBoundary",
                "reportContribution",
                "sideEffectPolicy",
                "auditEvent",
            ],
        )
        order = expect_integer(require_field(step, path, "order"), child(path, "order"))
        if order in seen_orders:
            raise ShapeError(f"duplicate value at {child(path, 'order')}: {order}")
        seen_orders.add(order)
        if expect_bool(require_field(step, path, "approvalRequired"), child(path, "approvalRequired")) is not True:
            raise ShapeError("unexpected value at $.flowSteps[].approvalRequired: expected true")
        require_string_array(
            require_field(step, path, "fixedArgsPreview"),
            child(path, "fixedArgsPreview"),
            min_items=1,
        )
        require_bool_fields(step, path, ["artifactWrite", "repositoryMutation"])
        for field in ["artifactWrite", "repositoryMutation"]:
            if step[field] is not False:
                raise ShapeError(f"unexpected value at $.flowSteps[].{field}: expected false")

    output = expect_object(require_field(root, "$", "outputPrototype"), "$.outputPrototype")
    require_string_fields(output, "$.outputPrototype", ["outputState", "outputFormat", "outputPolicy"])
    if output["outputState"] != "summary_only_fixture":
        raise ShapeError("unexpected value at $.outputPrototype.outputState: expected summary_only_fixture")
    require_bool_fields(
        output,
        "$.outputPrototype",
        [
            "trackedFileMutation",
            "artifactWrite",
            "pathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
            "privatePathsIncluded",
        ],
    )
    for field in [
        "trackedFileMutation",
        "artifactWrite",
        "pathEchoAllowed",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogIncluded",
        "privatePathsIncluded",
    ]:
        if output[field] is not False:
            raise ShapeError(f"unexpected value at $.outputPrototype.{field}: expected false")

    validation = expect_object(require_field(root, "$", "validationPolicy"), "$.validationPolicy")
    require_string_fields(validation, "$.validationPolicy", ["state", "noMutationCheck", "reviewRule"])
    true_validation_flags = ["localInputRequiresApproval", "manifestApprovalRequired"]
    false_validation_flags = [
        "commandExecutionByFixture",
        "trackedFileMutationAllowed",
        "artifactWriteAllowed",
        "pluginCodeLoadAllowed",
    ]
    require_bool_fields(
        validation,
        "$.validationPolicy",
        true_validation_flags + false_validation_flags,
    )
    for flag in true_validation_flags:
        if validation[flag] is not True:
            raise ShapeError(f"unexpected value at $.validationPolicy.{flag}: expected true")
    for flag in false_validation_flags:
        if validation[flag] is not False:
            raise ShapeError(f"unexpected value at $.validationPolicy.{flag}: expected false")

    require_string_array(require_field(root, "$", "blockedActions"), "$.blockedActions", min_items=1)

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "dryRunOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "stablePluginAbiPromised",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_plugin_input_contract(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-input-contract.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "contractId",
            "contractState",
            "pluginRuntimeState",
            "loaderState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["contractState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.contractState: expected descriptor_only")
    if root["pluginRuntimeState"] != "not_implemented":
        raise ShapeError("unexpected value at $.pluginRuntimeState: expected not_implemented")
    if root["loaderState"] != "not_implemented":
        raise ShapeError("unexpected value at $.loaderState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")
    if root["hostMode"] != "cli_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_first_gui_second")

    sample = expect_object(require_field(root, "$", "samplePluginRef"), "$.samplePluginRef")
    require_string_fields(sample, "$.samplePluginRef", ["pluginId", "manifestState", "entryKind"])
    require_bool_fields(
        sample,
        "$.samplePluginRef",
        ["codeLoaded", "packageInstalled", "dynamicLibrariesLoaded"],
    )
    for field in ["codeLoaded", "packageInstalled", "dynamicLibrariesLoaded"]:
        if sample[field] is not False:
            raise ShapeError(f"unexpected value at $.samplePluginRef.{field}: expected false")

    source_refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in source_refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(
            ref,
            path,
            ["refId", "schemaVersion", "examplePath", "approvalState"],
        )
        if expect_bool(require_field(ref, path, "pathEchoAllowed"), child(path, "pathEchoAllowed")) is not False:
            raise ShapeError("unexpected value at $.sourceBoundaryRefs[].pathEchoAllowed: expected false")

    input_contracts = require_object_array(
        require_field(root, "$", "inputContracts"),
        "$.inputContracts",
        min_items=2,
    )
    for input_contract in input_contracts:
        path = "$.inputContracts[]"
        require_string_fields(
            input_contract,
            path,
            [
                "inputId",
                "schemaVersion",
                "capabilityId",
                "inputKind",
                "inputState",
                "permissionProfile",
                "sourceRef",
                "summary",
            ],
        )
        true_fields = ["summaryOnly", "approvalRequired"]
        false_fields = [
            "localFileRead",
            "rawTraceRead",
            "rawReportRead",
            "artifactRead",
            "privatePathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
        ]
        require_bool_fields(input_contract, path, true_fields + false_fields)
        for field in true_fields:
            if input_contract[field] is not True:
                raise ShapeError(f"unexpected value at $.inputContracts[].{field}: expected true")
        for field in false_fields:
            if input_contract[field] is not False:
                raise ShapeError(f"unexpected value at $.inputContracts[].{field}: expected false")
        fields = require_object_array(
            require_field(input_contract, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.inputContracts[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    preview = expect_object(require_field(root, "$", "sampleInputPreview"), "$.sampleInputPreview")
    diagnostics = expect_object(
        require_field(preview, "$.sampleInputPreview", "diagnosticEnvelopeSummary"),
        "$.sampleInputPreview.diagnosticEnvelopeSummary",
    )
    require_string_fields(
        diagnostics,
        "$.sampleInputPreview.diagnosticEnvelopeSummary",
        ["sourceRef", "highestSeverity"],
    )
    expect_integer(
        require_field(diagnostics, "$.sampleInputPreview.diagnosticEnvelopeSummary", "diagnosticCount"),
        "$.sampleInputPreview.diagnosticEnvelopeSummary.diagnosticCount",
    )
    for field in [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
    ]:
        if expect_bool(
            require_field(diagnostics, "$.sampleInputPreview.diagnosticEnvelopeSummary", field),
            f"$.sampleInputPreview.diagnosticEnvelopeSummary.{field}",
        ) is not False:
            raise ShapeError(f"unexpected value at $.sampleInputPreview.diagnosticEnvelopeSummary.{field}: expected false")

    workflow = expect_object(
        require_field(preview, "$.sampleInputPreview", "workflowResultSummary"),
        "$.sampleInputPreview.workflowResultSummary",
    )
    require_string_fields(
        workflow,
        "$.sampleInputPreview.workflowResultSummary",
        ["sourceRef", "highestState"],
    )
    expect_integer(
        require_field(workflow, "$.sampleInputPreview.workflowResultSummary", "resultCount"),
        "$.sampleInputPreview.workflowResultSummary.resultCount",
    )
    for field in [
        "artifactPathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
    ]:
        if expect_bool(
            require_field(workflow, "$.sampleInputPreview.workflowResultSummary", field),
            f"$.sampleInputPreview.workflowResultSummary.{field}",
        ) is not False:
            raise ShapeError(f"unexpected value at $.sampleInputPreview.workflowResultSummary.{field}: expected false")

    trace_gate = expect_object(
        require_field(preview, "$.sampleInputPreview", "traceInputGate"),
        "$.sampleInputPreview.traceInputGate",
    )
    require_string_field(trace_gate, "$.sampleInputPreview.traceInputGate", "state")
    if expect_bool(
        require_field(trace_gate, "$.sampleInputPreview.traceInputGate", "traceSummaryRequired"),
        "$.sampleInputPreview.traceInputGate.traceSummaryRequired",
    ) is not True:
        raise ShapeError("unexpected value at $.sampleInputPreview.traceInputGate.traceSummaryRequired: expected true")
    for field in ["rawTraceInputAllowed", "pathEchoAllowed"]:
        if expect_bool(
            require_field(trace_gate, "$.sampleInputPreview.traceInputGate", field),
            f"$.sampleInputPreview.traceInputGate.{field}",
        ) is not False:
            raise ShapeError(f"unexpected value at $.sampleInputPreview.traceInputGate.{field}: expected false")

    input_policy = expect_object(require_field(root, "$", "inputPolicy"), "$.inputPolicy")
    require_string_fields(input_policy, "$.inputPolicy", ["state", "noMutationRule", "redactionRule"])
    true_policy_flags = ["summaryOnly", "approvalRequired", "auditRequired"]
    false_policy_flags = [
        "trackedFileMutationAllowed",
        "localFileReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "artifactReadAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
    ]
    require_bool_fields(input_policy, "$.inputPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if input_policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.inputPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if input_policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.inputPolicy.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "dynamic-code-load",
        "untrusted-execution",
        "plugin-package-install",
        "marketplace-flow",
        "arbitrary-shell-command",
        "local-file-read",
        "raw-trace-read",
        "raw-report-read",
        "artifact-read",
        "artifact-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "inputFixtureOnly", "summaryOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "inputReaderImplemented",
        "rawTraceRead",
        "rawReportRead",
        "localFileRead",
        "stablePluginAbiPromised",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "readsArtifacts",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


def validate_plugin_output_contract(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-output-contract.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "contractId",
            "contractState",
            "pluginRuntimeState",
            "loaderState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["contractState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.contractState: expected descriptor_only")
    if root["pluginRuntimeState"] != "not_implemented":
        raise ShapeError("unexpected value at $.pluginRuntimeState: expected not_implemented")
    if root["loaderState"] != "not_implemented":
        raise ShapeError("unexpected value at $.loaderState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")
    if root["hostMode"] != "cli_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_first_gui_second")

    sample = expect_object(require_field(root, "$", "samplePluginRef"), "$.samplePluginRef")
    require_string_fields(sample, "$.samplePluginRef", ["pluginId", "manifestState", "entryKind"])
    require_bool_fields(
        sample,
        "$.samplePluginRef",
        ["codeLoaded", "packageInstalled", "dynamicLibrariesLoaded"],
    )
    for field in ["codeLoaded", "packageInstalled", "dynamicLibrariesLoaded"]:
        if sample[field] is not False:
            raise ShapeError(f"unexpected value at $.samplePluginRef.{field}: expected false")

    inputs = require_object_array(
        require_field(root, "$", "inputBoundaryRefs"),
        "$.inputBoundaryRefs",
        min_items=1,
    )
    for ref in inputs:
        path = "$.inputBoundaryRefs[]"
        require_string_fields(
            ref,
            path,
            ["refId", "schemaVersion", "examplePath", "approvalState"],
        )
        if expect_bool(require_field(ref, path, "pathEchoAllowed"), child(path, "pathEchoAllowed")) is not False:
            raise ShapeError("unexpected value at $.inputBoundaryRefs[].pathEchoAllowed: expected false")

    outputs = require_object_array(
        require_field(root, "$", "outputContracts"),
        "$.outputContracts",
        min_items=3,
    )
    for output in outputs:
        path = "$.outputContracts[]"
        require_string_fields(
            output,
            path,
            [
                "outputId",
                "schemaVersion",
                "capabilityId",
                "outputKind",
                "outputState",
                "sourceInputRef",
                "permissionProfile",
                "displayTarget",
                "summary",
            ],
        )
        true_fields = ["summaryOnly"]
        false_fields = [
            "artifactWrite",
            "repositoryMutation",
            "privatePathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
        ]
        require_bool_fields(output, path, true_fields + false_fields)
        if output["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.outputContracts[].summaryOnly: expected true")
        for field in false_fields:
            if output[field] is not False:
                raise ShapeError(f"unexpected value at $.outputContracts[].{field}: expected false")
        fields = require_object_array(
            require_field(output, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.outputContracts[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    sample_output = expect_object(require_field(root, "$", "sampleOutput"), "$.sampleOutput")
    diagnostic_items = require_object_array(
        require_field(sample_output, "$.sampleOutput", "diagnosticSummaryItems"),
        "$.sampleOutput.diagnosticSummaryItems",
        min_items=1,
    )
    for item in diagnostic_items:
        path = "$.sampleOutput.diagnosticSummaryItems[]"
        require_string_fields(
            item,
            path,
            ["itemId", "severity", "code", "message", "sourceRef", "evidenceState"],
        )
        expect_integer(require_field(item, path, "line"), child(path, "line"))
        expect_integer(require_field(item, path, "column"), child(path, "column"))
        if expect_bool(require_field(item, path, "pathIncluded"), child(path, "pathIncluded")) is not False:
            raise ShapeError("unexpected value at $.sampleOutput.diagnosticSummaryItems[].pathIncluded: expected false")

    panel_items = require_object_array(
        require_field(sample_output, "$.sampleOutput", "reportPanelItems"),
        "$.sampleOutput.reportPanelItems",
        min_items=1,
    )
    for item in panel_items:
        path = "$.sampleOutput.reportPanelItems[]"
        require_string_fields(
            item,
            path,
            ["itemId", "panelId", "title", "state", "sourceRef", "presentation"],
        )
        require_bool_fields(item, path, ["artifactWrite", "pathIncluded"])
        for field in ["artifactWrite", "pathIncluded"]:
            if item[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleOutput.reportPanelItems[].{field}: expected false")

    report_items = require_object_array(
        require_field(sample_output, "$.sampleOutput", "reportItems"),
        "$.sampleOutput.reportItems",
        min_items=1,
    )
    for item in report_items:
        path = "$.sampleOutput.reportItems[]"
        require_string_fields(
            item,
            path,
            ["itemId", "reportSection", "title", "summary", "sourceRef"],
        )
        require_bool_fields(item, path, ["artifactWrite", "generatedArtifact", "pathIncluded"])
        for field in ["artifactWrite", "generatedArtifact", "pathIncluded"]:
            if item[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleOutput.reportItems[].{field}: expected false")

    output_policy = expect_object(require_field(root, "$", "outputPolicy"), "$.outputPolicy")
    require_string_fields(output_policy, "$.outputPolicy", ["state", "noMutationRule", "redactionRule"])
    true_policy_flags = ["summaryOnly", "approvalRequiredForInputs", "auditRequired"]
    false_policy_flags = [
        "trackedFileMutationAllowed",
        "artifactWriteAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
    ]
    require_bool_fields(output_policy, "$.outputPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if output_policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.outputPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if output_policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.outputPolicy.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "dynamic-code-load",
        "untrusted-execution",
        "plugin-package-install",
        "marketplace-flow",
        "arbitrary-shell-command",
        "artifact-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "runtime-launch",
        "model-load",
        "telemetry-upload",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "outputFixtureOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "stablePluginAbiPromised",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "telemetry",
        "writeBack",
        "writesArtifacts",
        "publicPush",
        "releaseOrTag",
    ]
    require_bool_fields(safety, "$.safetyFlags", true_flags + false_flags)
    for flag in true_flags:
        if safety[flag] is not True:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected true")
    for flag in false_flags:
        if safety[flag] is not False:
            raise ShapeError(f"unexpected value at $.safetyFlags.{flag}: expected false")

    require_string_array(require_field(root, "$", "limitations"), "$.limitations", min_items=1)
    require_string_array(require_field(root, "$", "issueRefs"), "$.issueRefs", min_items=1)


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
    BoundarySpec("mcp-read-only-tool-plan", "docs/examples/mcp-read-only-tool-plan.example.json", validate_mcp_read_only_tool_plan),
    BoundarySpec("mcp-read-only-analysis-flow", "docs/examples/mcp-read-only-analysis-flow.example.json", validate_mcp_read_only_analysis_flow),
    BoundarySpec("mcp-read-only-report-contract", "docs/examples/mcp-read-only-report-contract.example.json", validate_mcp_read_only_report_contract),
    BoundarySpec("mcp-permission-model", "docs/examples/mcp-permission-model.example.json", validate_mcp_permission_model),
    BoundarySpec("mcp-approval-request", "docs/examples/mcp-approval-request.example.json", validate_mcp_approval_request),
    BoundarySpec("mcp-approval-decision", "docs/examples/mcp-approval-decision.example.json", validate_mcp_approval_decision),
    BoundarySpec("mcp-blocked-invocation-result", "docs/examples/mcp-blocked-invocation-result.example.json", validate_mcp_blocked_invocation_result),
    BoundarySpec("mcp-audit-event", "docs/examples/mcp-audit-event.example.json", validate_mcp_audit_event),
    BoundarySpec("plugin-permission-model", "docs/examples/plugin-permission-model.example.json", validate_plugin_permission_model),
    BoundarySpec("plugin-audit-event", "docs/examples/plugin-audit-event.example.json", validate_plugin_audit_event),
    BoundarySpec("plugin-boundary-plan", "docs/examples/plugin-boundary-plan.example.json", validate_plugin_boundary_plan),
    BoundarySpec("plugin-dry-run-flow", "docs/examples/plugin-dry-run-flow.example.json", validate_plugin_dry_run_flow),
    BoundarySpec("plugin-input-contract", "docs/examples/plugin-input-contract.example.json", validate_plugin_input_contract),
    BoundarySpec("plugin-output-contract", "docs/examples/plugin-output-contract.example.json", validate_plugin_output_contract),
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
