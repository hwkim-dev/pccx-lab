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


def validate_mcp_tool_list(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-tool-list.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "toolListId",
            "listState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["listState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.listState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    if not any(
        ref["refId"] == "mcp_read_only_tool_plan"
        and ref.get("toolPlanAvailable") is True
        and ref.get("commandExecutorAllowed") is False
        and ref.get("mcpRuntimeAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_read_only_tool_plan disabled source reference")
    if not any(
        ref["refId"] == "mcp_permission_model"
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("approvalExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_permission_model disabled source reference")
    if not any(
        ref["refId"] == "mcp_evidence_manifest"
        and ref.get("summaryOnly") is True
        and ref.get("fileReaderAllowed") is False
        and ref.get("artifactReaderAllowed") is False
        and ref.get("reportWriterAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_evidence_manifest summary-only source reference")

    request = expect_object(require_field(root, "$", "toolListRequest"), "$.toolListRequest")
    require_string_fields(
        request,
        "$.toolListRequest",
        [
            "requestKind",
            "commandKind",
            "sourceReferenceKind",
            "outputBoundary",
            "summary",
        ],
    )
    if request["requestKind"] != "planned_mcp_tool_listing":
        raise ShapeError("unexpected value at $.toolListRequest.requestKind: expected planned_mcp_tool_listing")
    require_string_array(
        require_field(request, "$.toolListRequest", "fixedArgsPreview"),
        "$.toolListRequest.fixedArgsPreview",
        min_items=1,
    )
    request_true_flags = ["summaryOnly", "inputRefOnly"]
    request_false_flags = [
        "approvalRequired",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "permissionExecutorAllowed",
        "approvalExecutorAllowed",
        "auditLoggerAllowed",
        "toolInvocationAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
        "stableApiAbiClaim",
        "marketplaceClaim",
    ]
    require_bool_fields(request, "$.toolListRequest", request_true_flags + request_false_flags)
    for flag in request_true_flags:
        if request[flag] is not True:
            raise ShapeError(f"unexpected value at $.toolListRequest.{flag}: expected true")
    for flag in request_false_flags:
        if request[flag] is not False:
            raise ShapeError(f"unexpected value at $.toolListRequest.{flag}: expected false")

    tools = require_object_array(require_field(root, "$", "tools"), "$.tools", min_items=1)
    tool_ids = set()
    for tool in tools:
        path = "$.tools[]"
        require_string_fields(
            tool,
            path,
            [
                "toolId",
                "displayName",
                "category",
                "toolState",
                "listState",
                "permissionProfile",
                "inputPolicy",
                "outputPolicy",
                "reviewSource",
                "commandPreviewKind",
            ],
        )
        tool_ids.add(tool["toolId"])
        true_flags = ["approvedForListing", "requiresSeparateInvocationBoundary"]
        false_flags = [
            "approvedForInvocation",
            "toolInvocationAllowed",
            "commandExecutionAllowed",
            "localFileReadAllowed",
            "repositoryReadAllowed",
            "artifactReadAllowed",
            "reportWriteAllowed",
        ]
        require_bool_fields(tool, path, true_flags + false_flags)
        for flag in true_flags:
            if tool[flag] is not True:
                raise ShapeError(f"unexpected value at {path}.{flag}: expected true")
        for flag in false_flags:
            if tool[flag] is not False:
                raise ShapeError(f"unexpected value at {path}.{flag}: expected false")
    for tool_id in [
        "lab.status.read",
        "lab.workflows.list",
        "lab.workflowProposals.preview",
        "lab.workflowResults.summarize",
        "lab.diagnosticsHandoff.validate",
        "lab.deviceSessionStatus.validate",
        "lab.fileShapeDiagnostics.analyze",
    ]:
        if tool_id not in tool_ids:
            raise ShapeError(f"missing tool id in $.tools: {tool_id}")

    deferred = require_object_array(
        require_field(root, "$", "deferredTools"),
        "$.deferredTools",
        min_items=1,
    )
    deferred_ids = set()
    for tool in deferred:
        path = "$.deferredTools[]"
        require_string_fields(tool, path, ["toolId", "toolState", "reason"])
        deferred_ids.add(tool["toolId"])
        require_bool_fields(tool, path, ["approvedForListing", "approvedForInvocation", "toolInvocationAllowed"])
        if tool["approvedForListing"] is not True:
            raise ShapeError("unexpected value at $.deferredTools[].approvedForListing: expected true")
        for flag in ["approvedForInvocation", "toolInvocationAllowed"]:
            if tool[flag] is not False:
                raise ShapeError(f"unexpected value at $.deferredTools[].{flag}: expected false")
    for tool_id in [
        "lab.trace.open",
        "lab.report.generate",
        "lab.verification.compare",
        "lab.pullRequestSummary.prepare",
    ]:
        if tool_id not in deferred_ids:
            raise ShapeError(f"missing deferred tool id in $.deferredTools: {tool_id}")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(
        require_field(display, "$.displayPolicy", "allowedFields"),
        "$.displayPolicy.allowedFields",
        min_items=1,
    )
    require_string_array(
        require_field(display, "$.displayPolicy", "blockedFields"),
        "$.displayPolicy.blockedFields",
        min_items=1,
    )
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "rawCommandIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    if display["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.displayPolicy.summaryOnly: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "auditLogWriteAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-start",
        "mcp-transport-start",
        "tool-invocation",
        "permission-executor",
        "approval-executor",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "raw-log-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "audit-log-write",
        "repository-write-back",
        "marketplace-flow",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "summaryOnly", "toolListFixtureOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpTransportImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "permissionExecutorImplemented",
        "approvalExecutorImplemented",
        "auditLoggerImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "auditPersistence",
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
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
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


def validate_mcp_tool_detail(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-tool-detail.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "toolDetailId",
            "detailState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["detailState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.detailState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    if not any(
        ref["refId"] == "mcp_tool_list"
        and ref.get("toolListAvailable") is True
        and ref.get("toolDetailAvailable") is True
        and ref.get("commandExecutorAllowed") is False
        and ref.get("mcpRuntimeAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_tool_list disabled source reference")
    if not any(
        ref["refId"] == "mcp_permission_model"
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("approvalExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_permission_model disabled source reference")
    if not any(
        ref["refId"] == "mcp_evidence_manifest"
        and ref.get("summaryOnly") is True
        and ref.get("fileReaderAllowed") is False
        and ref.get("artifactReaderAllowed") is False
        and ref.get("reportWriterAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_evidence_manifest summary-only source reference")

    request = expect_object(require_field(root, "$", "toolDetailRequest"), "$.toolDetailRequest")
    require_string_fields(
        request,
        "$.toolDetailRequest",
        [
            "requestKind",
            "commandKind",
            "selectedToolId",
            "sourceReferenceKind",
            "outputBoundary",
            "summary",
        ],
    )
    if request["requestKind"] != "planned_mcp_tool_detail":
        raise ShapeError("unexpected value at $.toolDetailRequest.requestKind: expected planned_mcp_tool_detail")
    if request["selectedToolId"] != "lab.status.read":
        raise ShapeError("unexpected value at $.toolDetailRequest.selectedToolId: expected lab.status.read")
    require_string_array(
        require_field(request, "$.toolDetailRequest", "fixedArgsPreview"),
        "$.toolDetailRequest.fixedArgsPreview",
        min_items=1,
    )
    request_true_flags = ["summaryOnly", "inputRefOnly"]
    request_false_flags = [
        "approvalRequired",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "permissionExecutorAllowed",
        "approvalExecutorAllowed",
        "auditLoggerAllowed",
        "toolInvocationAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
        "stableApiAbiClaim",
        "marketplaceClaim",
    ]
    require_bool_fields(request, "$.toolDetailRequest", request_true_flags + request_false_flags)
    for flag in request_true_flags:
        if request[flag] is not True:
            raise ShapeError(f"unexpected value at $.toolDetailRequest.{flag}: expected true")
    for flag in request_false_flags:
        if request[flag] is not False:
            raise ShapeError(f"unexpected value at $.toolDetailRequest.{flag}: expected false")

    selected = expect_object(require_field(root, "$", "selectedTool"), "$.selectedTool")
    require_string_fields(
        selected,
        "$.selectedTool",
        [
            "toolId",
            "displayName",
            "category",
            "toolState",
            "detailState",
            "listState",
            "permissionProfile",
            "reviewSource",
            "commandPreviewKind",
            "summary",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if selected["toolId"] != request["selectedToolId"]:
        raise ShapeError("selected tool id must match $.toolDetailRequest.selectedToolId")
    if selected["detailState"] != "visible_descriptor":
        raise ShapeError("unexpected value at $.selectedTool.detailState: expected visible_descriptor")

    input_descriptor = expect_object(
        require_field(selected, "$.selectedTool", "inputDescriptor"),
        "$.selectedTool.inputDescriptor",
    )
    require_string_fields(
        input_descriptor,
        "$.selectedTool.inputDescriptor",
        ["descriptorState", "acceptedInputKind", "acceptedInputSummary"],
    )
    input_false_flags = [
        "userPathAccepted",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "providerConfigReadAllowed",
        "environmentReadAllowed",
        "secretsReadAllowed",
        "tokensReadAllowed",
    ]
    require_bool_fields(input_descriptor, "$.selectedTool.inputDescriptor", input_false_flags)
    for flag in input_false_flags:
        if input_descriptor[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedTool.inputDescriptor.{flag}: expected false")

    output_descriptor = expect_object(
        require_field(selected, "$.selectedTool", "outputDescriptor"),
        "$.selectedTool.outputDescriptor",
    )
    require_string_fields(output_descriptor, "$.selectedTool.outputDescriptor", ["descriptorState", "boundaryRef"])
    output_false_flags = [
        "payloadIncluded",
        "responseBodyIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "reportContentIncluded",
    ]
    require_bool_fields(output_descriptor, "$.selectedTool.outputDescriptor", output_false_flags)
    for flag in output_false_flags:
        if output_descriptor[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedTool.outputDescriptor.{flag}: expected false")

    invocation = expect_object(
        require_field(selected, "$.selectedTool", "invocationPolicy"),
        "$.selectedTool.invocationPolicy",
    )
    invocation_true_flags = [
        "requiresSeparateInvocationBoundary",
        "approvalRequiredBeforeInvocation",
        "approvedForListing",
        "approvedForDetail",
    ]
    invocation_false_flags = [
        "approvedForInvocation",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "permissionExecutorAllowed",
        "approvalExecutorAllowed",
        "auditLoggerAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
    ]
    require_bool_fields(
        invocation,
        "$.selectedTool.invocationPolicy",
        invocation_true_flags + invocation_false_flags,
    )
    for flag in invocation_true_flags:
        if invocation[flag] is not True:
            raise ShapeError(f"unexpected value at $.selectedTool.invocationPolicy.{flag}: expected true")
    for flag in invocation_false_flags:
        if invocation[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedTool.invocationPolicy.{flag}: expected false")

    related = require_object_array(
        require_field(root, "$", "relatedToolRefs"),
        "$.relatedToolRefs",
        min_items=1,
    )
    for tool in related:
        path = "$.relatedToolRefs[]"
        require_string_fields(tool, path, ["toolId", "relationship"])
        require_bool_fields(tool, path, ["detailIncluded", "approvedForDetail", "toolInvocationAllowed"])
        for flag in ["detailIncluded", "approvedForDetail", "toolInvocationAllowed"]:
            if tool[flag] is not False:
                raise ShapeError(f"unexpected value at $.relatedToolRefs[].{flag}: expected false")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(
        require_field(display, "$.displayPolicy", "allowedFields"),
        "$.displayPolicy.allowedFields",
        min_items=1,
    )
    require_string_array(
        require_field(display, "$.displayPolicy", "blockedFields"),
        "$.displayPolicy.blockedFields",
        min_items=1,
    )
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "rawCommandIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "reportContentIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    if display["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.displayPolicy.summaryOnly: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "auditLogWriteAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-start",
        "mcp-transport-start",
        "tool-invocation",
        "permission-executor",
        "approval-executor",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "raw-log-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "audit-log-write",
        "repository-write-back",
        "marketplace-flow",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "summaryOnly", "toolDetailFixtureOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpTransportImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "permissionExecutorImplemented",
        "approvalExecutorImplemented",
        "auditLoggerImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "auditPersistence",
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
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
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


def validate_mcp_sample_plan(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-sample-plan.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "samplePlanId",
            "planState",
            "sampleState",
            "adapterState",
            "defaultMode",
            "hostMode",
            "automationPath",
        ],
    )
    if root["planState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.planState: expected descriptor_only")
    if root["sampleState"] != "plan_only":
        raise ShapeError("unexpected value at $.sampleState: expected plan_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")
    if root["automationPath"] != "cli-core-first-gui-independent":
        raise ShapeError("unexpected value at $.automationPath: expected cli-core-first-gui-independent")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "mcp_read_only_tool_plan",
        "mcp_tool_detail",
        "mcp_read_only_analysis_flow",
        "mcp_read_only_report_contract",
        "mcp_permission_model",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "mcp_read_only_tool_plan"
        and ref.get("toolPlanAvailable") is True
        and ref.get("commandExecutorAllowed") is False
        and ref.get("mcpRuntimeAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_read_only_tool_plan disabled source reference")
    if not any(
        ref["refId"] == "mcp_tool_detail"
        and ref.get("toolDetailAvailable") is True
        and ref.get("selectedToolId") == "lab.status.read"
        and ref.get("commandExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_tool_detail disabled source reference")
    if not any(
        ref["refId"] == "mcp_read_only_analysis_flow"
        and ref.get("flowShapeAvailable") is True
        and ref.get("flowExecutionAllowed") is False
        and ref.get("commandExecutionAllowed") is False
        and ref.get("reportWriteAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_read_only_analysis_flow disabled source reference")
    if not any(
        ref["refId"] == "mcp_read_only_report_contract"
        and ref.get("reportShapeAvailable") is True
        and ref.get("reportContentIncluded") is False
        and ref.get("reportWriteAllowed") is False
        and ref.get("artifactWriteAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_read_only_report_contract summary-only source reference")
    if not any(
        ref["refId"] == "mcp_permission_model"
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("approvalExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_permission_model disabled source reference")

    sample = expect_object(require_field(root, "$", "sampleTool"), "$.sampleTool")
    require_string_fields(
        sample,
        "$.sampleTool",
        [
            "toolId",
            "displayName",
            "sampleKind",
            "sampleState",
            "toolState",
            "permissionProfile",
            "commandPreviewKind",
            "outputBoundaryRef",
            "executionState",
            "summary",
        ],
    )
    if sample["toolId"] != "lab.status.read":
        raise ShapeError("unexpected value at $.sampleTool.toolId: expected lab.status.read")
    if sample["sampleState"] != "plan_only":
        raise ShapeError("unexpected value at $.sampleTool.sampleState: expected plan_only")
    if sample["executionState"] != "not_implemented":
        raise ShapeError("unexpected value at $.sampleTool.executionState: expected not_implemented")
    sample_true_flags = ["toolDescriptorOnly"]
    sample_false_flags = [
        "commandArgsMaterialized",
        "rawCommandIncluded",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "permissionExecutorAllowed",
        "approvalExecutorAllowed",
        "auditLoggerAllowed",
        "toolInvocationAllowed",
    ]
    require_bool_fields(sample, "$.sampleTool", sample_true_flags + sample_false_flags)
    for flag in sample_true_flags:
        if sample[flag] is not True:
            raise ShapeError(f"unexpected value at $.sampleTool.{flag}: expected true")
    for flag in sample_false_flags:
        if sample[flag] is not False:
            raise ShapeError(f"unexpected value at $.sampleTool.{flag}: expected false")

    flow = expect_object(require_field(root, "$", "sampleFlow"), "$.sampleFlow")
    require_string_fields(
        flow,
        "$.sampleFlow",
        [
            "flowId",
            "flowState",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.sampleFlow.flowState: expected blocked")
    if flow["commandKind"] != "planned-cli-fixed-args":
        raise ShapeError("unexpected value at $.sampleFlow.commandKind: expected planned-cli-fixed-args")
    require_string_array(
        require_field(flow, "$.sampleFlow", "fixedArgsPreview"),
        "$.sampleFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.sampleFlow", "steps"), "$.sampleFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.sampleFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "tool_descriptor_review",
        "permission_profile_review",
        "report_contract_review",
        "sample_client_gate",
        "sample_invocation_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing sample flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.sampleFlow", "blockedReasonRefs"),
        "$.sampleFlow.blockedReasonRefs",
        min_items=1,
    )

    io_boundary = expect_object(require_field(root, "$", "inputOutputBoundary"), "$.inputOutputBoundary")
    require_string_fields(
        io_boundary,
        "$.inputOutputBoundary",
        ["state", "acceptedInputKind", "inputContractSchema", "outputContractSchema"],
    )
    if io_boundary["state"] != "summary_only":
        raise ShapeError("unexpected value at $.inputOutputBoundary.state: expected summary_only")
    io_false_flags = [
        "labStatusPayloadIncluded",
        "workflowResultContentIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "promptContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "inputReaderAllowed",
        "traceImporterAllowed",
        "reportReaderAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
    ]
    require_bool_fields(io_boundary, "$.inputOutputBoundary", io_false_flags)
    for flag in io_false_flags:
        if io_boundary[flag] is not False:
            raise ShapeError(f"unexpected value at $.inputOutputBoundary.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForPlan"]
    review_false_flags = [
        "approvedForClientImplementation",
        "approvedForTransport",
        "approvedForRuntime",
        "approvedForCommandExecution",
        "approvedForInvocation",
        "approvedForPermissionExecution",
        "approvedForApprovalExecution",
        "approvedForAuditLogWrite",
        "approvedForReportWrite",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-start",
        "mcp-transport-start",
        "mcp-runtime-start",
        "tool-invocation",
        "permission-executor",
        "approval-executor",
        "audit-log-write",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "raw-log-read",
        "artifact-read",
        "artifact-write",
        "report-read",
        "report-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "auditLogWriteAllowed",
        "toolInvocationAllowed",
        "permissionExecutionAllowed",
        "approvalExecutionAllowed",
        "commandExecutionAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "rawCommandIncluded",
        "localPathsIncluded",
        "repositoryPathsIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "reportContentIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "samplePlanFixtureOnly",
    ]
    false_flags = [
        "sampleToolImplemented",
        "sampleToolExecuted",
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpTransportImplemented",
        "commandExecutorImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "permissionExecutorImplemented",
        "approvalExecutorImplemented",
        "auditLoggerImplemented",
        "auditPersistence",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
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
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_mcp_sample_result(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-sample-result.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "sampleResultId",
            "resultState",
            "sampleState",
            "adapterState",
            "defaultMode",
            "hostMode",
            "automationPath",
        ],
    )
    if root["resultState"] != "blocked_summary":
        raise ShapeError("unexpected value at $.resultState: expected blocked_summary")
    if root["sampleState"] != "not_executed":
        raise ShapeError("unexpected value at $.sampleState: expected not_executed")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")
    if root["automationPath"] != "cli-core-first-gui-independent":
        raise ShapeError("unexpected value at $.automationPath: expected cli-core-first-gui-independent")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "mcp_sample_plan",
        "mcp_tool_detail",
        "mcp_read_only_report_contract",
        "mcp_evidence_detail",
        "mcp_blocked_invocation_result",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "mcp_sample_plan"
        and ref.get("samplePlanAvailable") is True
        and ref.get("sampleExecuted") is False
        and ref.get("commandExecutionAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_sample_plan disabled source reference")
    if not any(
        ref["refId"] == "mcp_tool_detail"
        and ref.get("toolDetailAvailable") is True
        and ref.get("selectedToolId") == "lab.status.read"
        and ref.get("commandExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_tool_detail disabled source reference")
    if not any(
        ref["refId"] == "mcp_read_only_report_contract"
        and ref.get("reportShapeAvailable") is True
        and ref.get("reportContentIncluded") is False
        and ref.get("reportReadAllowed") is False
        and ref.get("reportWriteAllowed") is False
        and ref.get("artifactWriteAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_read_only_report_contract summary-only source reference")
    if not any(
        ref["refId"] == "mcp_evidence_detail"
        and ref.get("evidenceDetailAvailable") is True
        and ref.get("summaryOnly") is True
        and ref.get("artifactReadAllowed") is False
        and ref.get("reportReadAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_evidence_detail summary-only source reference")
    if not any(
        ref["refId"] == "mcp_blocked_invocation_result"
        and ref.get("blockedResultAvailable") is True
        and ref.get("invocationExecuted") is False
        and ref.get("commandExecutionAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_blocked_invocation_result disabled source reference")

    sample = expect_object(require_field(root, "$", "sampleResult"), "$.sampleResult")
    require_string_fields(
        sample,
        "$.sampleResult",
        [
            "sampleToolId",
            "displayName",
            "resultKind",
            "resultState",
            "sampleState",
            "invocationState",
            "outputBoundaryRef",
            "samplePlanRef",
            "summary",
        ],
    )
    if sample["sampleToolId"] != "lab.status.read":
        raise ShapeError("unexpected value at $.sampleResult.sampleToolId: expected lab.status.read")
    if sample["resultState"] != "blocked_summary":
        raise ShapeError("unexpected value at $.sampleResult.resultState: expected blocked_summary")
    if sample["sampleState"] != "not_executed":
        raise ShapeError("unexpected value at $.sampleResult.sampleState: expected not_executed")
    if sample["invocationState"] != "not_invoked":
        raise ShapeError("unexpected value at $.sampleResult.invocationState: expected not_invoked")
    sample_true_flags = ["summaryOnly", "resultDescriptorOnly"]
    sample_false_flags = [
        "payloadIncluded",
        "labStatusPayloadIncluded",
        "workflowResultContentIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "sampleToolImplemented",
        "sampleToolExecuted",
        "sampleResultProduced",
        "toolInvocationAttempted",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "permissionExecutorAllowed",
        "approvalExecutorAllowed",
        "auditLoggerAllowed",
        "toolInvocationAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
    ]
    require_bool_fields(sample, "$.sampleResult", sample_true_flags + sample_false_flags)
    for flag in sample_true_flags:
        if sample[flag] is not True:
            raise ShapeError(f"unexpected value at $.sampleResult.{flag}: expected true")
    for flag in sample_false_flags:
        if sample[flag] is not False:
            raise ShapeError(f"unexpected value at $.sampleResult.{flag}: expected false")

    flow = expect_object(require_field(root, "$", "resultFlow"), "$.resultFlow")
    require_string_fields(
        flow,
        "$.resultFlow",
        [
            "flowId",
            "flowState",
            "resultKind",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.resultFlow.flowState: expected blocked")
    if flow["commandKind"] != "planned-cli-fixed-args":
        raise ShapeError("unexpected value at $.resultFlow.commandKind: expected planned-cli-fixed-args")
    require_string_array(
        require_field(flow, "$.resultFlow", "fixedArgsPreview"),
        "$.resultFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.resultFlow", "steps"), "$.resultFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.resultFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "sample_plan_review",
        "selected_tool_review",
        "blocked_result_reference",
        "result_envelope_gate",
        "sample_invocation_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing sample result flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.resultFlow", "blockedReasonRefs"),
        "$.resultFlow.blockedReasonRefs",
        min_items=1,
    )

    envelope = expect_object(require_field(root, "$", "resultEnvelope"), "$.resultEnvelope")
    require_string_fields(
        envelope,
        "$.resultEnvelope",
        ["state", "acceptedInputKind", "resultContractSchema", "outputContractSchema", "payloadPolicy"],
    )
    if envelope["state"] != "summary_only":
        raise ShapeError("unexpected value at $.resultEnvelope.state: expected summary_only")
    envelope_false_flags = [
        "payloadIncluded",
        "labStatusPayloadIncluded",
        "workflowResultContentIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "promptContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "inputReaderAllowed",
        "resultPayloadReaderAllowed",
        "traceImporterAllowed",
        "reportReaderAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
    ]
    require_bool_fields(envelope, "$.resultEnvelope", envelope_false_flags)
    for flag in envelope_false_flags:
        if envelope[flag] is not False:
            raise ShapeError(f"unexpected value at $.resultEnvelope.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForDescriptorResult"]
    review_false_flags = [
        "approvedForClientImplementation",
        "approvedForTransport",
        "approvedForRuntime",
        "approvedForCommandExecution",
        "approvedForInvocation",
        "approvedForPermissionExecution",
        "approvedForApprovalExecution",
        "approvedForAuditLogWrite",
        "approvedForReportRead",
        "approvedForReportWrite",
        "approvedForArtifactRead",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "rawCommandIncluded",
        "localPathsIncluded",
        "repositoryPathsIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "reportContentIncluded",
        "payloadIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "auditLogWriteAllowed",
        "toolInvocationAllowed",
        "permissionExecutionAllowed",
        "approvalExecutionAllowed",
        "commandExecutionAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-start",
        "mcp-transport-start",
        "mcp-runtime-start",
        "tool-invocation",
        "permission-executor",
        "audit-log-write",
        "command-execution",
        "local-file-read",
        "repository-read",
        "result-payload-read",
        "report-read",
        "report-write",
        "artifact-read",
        "artifact-write",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "model-load",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "sampleResultFixtureOnly",
    ]
    false_flags = [
        "sampleToolImplemented",
        "sampleToolExecuted",
        "sampleResultProduced",
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpTransportImplemented",
        "commandExecutorImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "permissionExecutorImplemented",
        "approvalExecutorImplemented",
        "auditLoggerImplemented",
        "auditPersistence",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "resultPayloadReaderImplemented",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
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
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_mcp_sample_catalog(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-sample-catalog.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "sampleCatalogId",
            "catalogState",
            "sampleState",
            "adapterState",
            "defaultMode",
            "hostMode",
            "automationPath",
        ],
    )
    if root["catalogState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.catalogState: expected descriptor_only")
    if root["sampleState"] != "listed_not_executed":
        raise ShapeError("unexpected value at $.sampleState: expected listed_not_executed")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "mcp_sample_plan",
        "mcp_sample_result",
        "mcp_tool_detail",
        "mcp_permission_model",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "mcp_sample_plan"
        and ref.get("samplePlanAvailable") is True
        and ref.get("sampleExecuted") is False
        and ref.get("commandExecutionAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_sample_plan disabled source reference")
    if not any(
        ref["refId"] == "mcp_sample_result"
        and ref.get("sampleResultAvailable") is True
        and ref.get("sampleResultProduced") is False
        and ref.get("resultPayloadReaderAllowed") is False
        and ref.get("reportReaderAllowed") is False
        and ref.get("artifactReaderAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_sample_result disabled source reference")
    if not any(
        ref["refId"] == "mcp_tool_detail"
        and ref.get("toolDetailAvailable") is True
        and ref.get("selectedToolId") == "lab.status.read"
        and ref.get("commandExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_tool_detail disabled source reference")
    if not any(
        ref["refId"] == "mcp_permission_model"
        and ref.get("permissionModelAvailable") is True
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("approvalExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_permission_model disabled source reference")

    summary = expect_object(require_field(root, "$", "catalogSummary"), "$.catalogSummary")
    require_string_fields(
        summary,
        "$.catalogSummary",
        ["catalogKind", "sourceReferenceKind", "summary"],
    )
    entry_count = expect_integer(require_field(summary, "$.catalogSummary", "entryCount"), "$.catalogSummary.entryCount")
    if entry_count < 1:
        raise ShapeError("expected at least 1 entry at $.catalogSummary.entryCount")
    summary_true_flags = ["summaryOnly", "descriptorOnly", "generatedFromApprovedSummaries"]
    summary_false_flags = [
        "sampleDiscoveryImplemented",
        "commandExecutorAllowed",
        "toolInvocationAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
    ]
    require_bool_fields(summary, "$.catalogSummary", summary_true_flags + summary_false_flags)
    for flag in summary_true_flags:
        if summary[flag] is not True:
            raise ShapeError(f"unexpected value at $.catalogSummary.{flag}: expected true")
    for flag in summary_false_flags:
        if summary[flag] is not False:
            raise ShapeError(f"unexpected value at $.catalogSummary.{flag}: expected false")

    entries = require_object_array(require_field(root, "$", "sampleEntries"), "$.sampleEntries", min_items=1)
    for entry in entries:
        path = "$.sampleEntries[]"
        require_string_fields(
            entry,
            path,
            [
                "sampleToolId",
                "displayName",
                "sampleKind",
                "catalogEntryState",
                "planState",
                "resultState",
                "sampleState",
                "invocationState",
                "outputBoundaryRef",
                "samplePlanRef",
                "sampleResultRef",
                "permissionProfile",
                "summary",
            ],
        )
        if entry["sampleToolId"] != "lab.status.read":
            raise ShapeError("unexpected value at $.sampleEntries[].sampleToolId: expected lab.status.read")
        if entry["catalogEntryState"] != "listed_descriptor_only":
            raise ShapeError("unexpected value at $.sampleEntries[].catalogEntryState: expected listed_descriptor_only")
        if entry["planState"] != "descriptor_only":
            raise ShapeError("unexpected value at $.sampleEntries[].planState: expected descriptor_only")
        if entry["resultState"] != "blocked_summary":
            raise ShapeError("unexpected value at $.sampleEntries[].resultState: expected blocked_summary")
        if entry["sampleState"] != "not_executed":
            raise ShapeError("unexpected value at $.sampleEntries[].sampleState: expected not_executed")
        if entry["invocationState"] != "not_invoked":
            raise ShapeError("unexpected value at $.sampleEntries[].invocationState: expected not_invoked")
        entry_true_flags = [
            "summaryOnly",
            "descriptorOnly",
            "samplePlanAvailable",
            "sampleResultAvailable",
        ]
        entry_false_flags = [
            "sampleToolImplemented",
            "sampleToolExecuted",
            "sampleResultProduced",
            "toolInvocationAttempted",
            "commandArgsIncluded",
            "localPathsIncluded",
            "repositoryPathsIncluded",
            "labStatusPayloadIncluded",
            "workflowResultContentIncluded",
            "reportContentIncluded",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogsIncluded",
            "artifactPathsIncluded",
            "privatePathsIncluded",
            "commandExecutionAllowed",
            "shellExecutionAllowed",
            "runtimeExecutionAllowed",
            "mcpServerAllowed",
            "mcpClientAllowed",
            "mcpRuntimeAllowed",
            "mcpTransportAllowed",
            "permissionExecutorAllowed",
            "approvalExecutorAllowed",
            "auditLoggerAllowed",
            "toolInvocationAllowed",
            "resultPayloadReaderAllowed",
            "reportReaderAllowed",
            "reportWriteAllowed",
            "artifactReaderAllowed",
            "artifactWriteAllowed",
        ]
        require_bool_fields(entry, path, entry_true_flags + entry_false_flags)
        for flag in entry_true_flags:
            if entry[flag] is not True:
                raise ShapeError(f"unexpected value at {child(path, flag)}: expected true")
        for flag in entry_false_flags:
            if entry[flag] is not False:
                raise ShapeError(f"unexpected value at {child(path, flag)}: expected false")

    flow = expect_object(require_field(root, "$", "catalogFlow"), "$.catalogFlow")
    require_string_fields(
        flow,
        "$.catalogFlow",
        [
            "flowId",
            "flowState",
            "catalogKind",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.catalogFlow.flowState: expected blocked")
    if flow["commandKind"] != "planned-cli-fixed-args":
        raise ShapeError("unexpected value at $.catalogFlow.commandKind: expected planned-cli-fixed-args")
    require_string_array(
        require_field(flow, "$.catalogFlow", "fixedArgsPreview"),
        "$.catalogFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.catalogFlow", "steps"), "$.catalogFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.catalogFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "sample_plan_reference",
        "sample_result_reference",
        "catalog_listing_gate",
        "sample_invocation_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing MCP sample catalog flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.catalogFlow", "blockedReasonRefs"),
        "$.catalogFlow.blockedReasonRefs",
        min_items=1,
    )

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "rawCommandIncluded",
        "localPathsIncluded",
        "repositoryPathsIncluded",
        "privatePathsIncluded",
        "labStatusPayloadIncluded",
        "workflowResultContentIncluded",
        "resultPayloadIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForCatalogDescriptor"]
    review_false_flags = [
        "approvedForClientImplementation",
        "approvedForTransport",
        "approvedForRuntime",
        "approvedForCommandExecution",
        "approvedForInvocation",
        "approvedForPermissionExecution",
        "approvedForApprovalExecution",
        "approvedForAuditLogWrite",
        "approvedForPayloadRead",
        "approvedForReportRead",
        "approvedForReportWrite",
        "approvedForArtifactRead",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "repositoryMutationAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "toolInvocationAllowed",
        "permissionExecutionAllowed",
        "approvalExecutionAllowed",
        "auditLogWriteAllowed",
        "commandExecutionAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "sample-discovery",
        "mcp-server-start",
        "mcp-client-start",
        "mcp-transport-open",
        "mcp-runtime-start",
        "command-execution",
        "tool-invocation",
        "permission-executor",
        "approval-executor",
        "audit-logger",
        "result-payload-read",
        "report-read",
        "report-write",
        "artifact-read",
        "artifact-write",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "model-load",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "sampleCatalogFixtureOnly",
    ]
    false_flags = [
        "sampleDiscoveryImplemented",
        "sampleToolImplemented",
        "sampleToolExecuted",
        "sampleResultProduced",
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpTransportImplemented",
        "commandExecutorImplemented",
        "permissionExecutorImplemented",
        "approvalExecutorImplemented",
        "auditLoggerImplemented",
        "resultPayloadReaderImplemented",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "toolInvocationImplemented",
        "stableApiAbiClaim",
        "marketplaceClaim",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "rawCommandIncluded",
        "localPathsIncluded",
        "repositoryPathsIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_mcp_sample_detail(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-sample-detail.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "sampleDetailId",
            "detailState",
            "sampleState",
            "resultState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["detailState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.detailState: expected descriptor_only")
    if root["sampleState"] != "listed_not_executed":
        raise ShapeError("unexpected value at $.sampleState: expected listed_not_executed")
    if root["resultState"] != "blocked_summary":
        raise ShapeError("unexpected value at $.resultState: expected blocked_summary")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "mcp_sample_catalog",
        "mcp_sample_result",
        "mcp_sample_plan",
        "mcp_tool_detail",
        "mcp_permission_model",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "mcp_sample_catalog"
        and ref.get("sampleCatalogAvailable") is True
        and ref.get("sampleDiscoveryAllowed") is False
        and ref.get("commandExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_sample_catalog disabled source reference")
    if not any(
        ref["refId"] == "mcp_sample_result"
        and ref.get("sampleResultAvailable") is True
        and ref.get("sampleResultProduced") is False
        and ref.get("resultPayloadReaderAllowed") is False
        and ref.get("reportReaderAllowed") is False
        and ref.get("artifactReaderAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_sample_result disabled source reference")
    if not any(
        ref["refId"] == "mcp_sample_plan"
        and ref.get("samplePlanAvailable") is True
        and ref.get("sampleExecuted") is False
        and ref.get("commandExecutionAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_sample_plan disabled source reference")
    if not any(
        ref["refId"] == "mcp_tool_detail"
        and ref.get("toolDetailAvailable") is True
        and ref.get("selectedToolId") == "lab.status.read"
        and ref.get("commandExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_tool_detail disabled source reference")
    if not any(
        ref["refId"] == "mcp_permission_model"
        and ref.get("permissionModelAvailable") is True
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("approvalExecutorAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_permission_model disabled source reference")

    sample = expect_object(require_field(root, "$", "selectedSample"), "$.selectedSample")
    require_string_fields(
        sample,
        "$.selectedSample",
        [
            "sampleToolId",
            "displayName",
            "sampleKind",
            "detailState",
            "catalogEntryState",
            "planState",
            "resultState",
            "sampleState",
            "invocationState",
            "outputBoundaryRef",
            "sampleCatalogRef",
            "samplePlanRef",
            "sampleResultRef",
            "selectedToolId",
            "permissionProfile",
            "summary",
        ],
    )
    expected_sample_values = {
        "sampleToolId": "lab.status.read",
        "detailState": "selected_descriptor_only",
        "catalogEntryState": "listed_descriptor_only",
        "planState": "descriptor_only",
        "resultState": "blocked_summary",
        "sampleState": "not_executed",
        "invocationState": "not_invoked",
        "selectedToolId": "lab.status.read",
        "outputBoundaryRef": "pccx.lab.status.v0",
    }
    for field, expected in expected_sample_values.items():
        if sample[field] != expected:
            raise ShapeError(f"unexpected value at $.selectedSample.{field}: expected {expected}")
    sample_true_flags = [
        "summaryOnly",
        "descriptorOnly",
        "sampleCatalogAvailable",
        "samplePlanAvailable",
        "sampleResultAvailable",
        "toolDetailAvailable",
    ]
    sample_false_flags = [
        "sampleToolImplemented",
        "sampleToolExecuted",
        "sampleResultProduced",
        "toolInvocationAttempted",
        "commandArgsIncluded",
        "rawCommandIncluded",
        "localPathsIncluded",
        "repositoryPathsIncluded",
        "labStatusPayloadIncluded",
        "workflowResultContentIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "resultPayloadIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "permissionExecutorAllowed",
        "approvalExecutorAllowed",
        "auditLoggerAllowed",
        "toolInvocationAllowed",
        "resultPayloadReaderAllowed",
        "reportReaderAllowed",
        "reportWriteAllowed",
        "artifactReaderAllowed",
        "artifactWriteAllowed",
    ]
    require_bool_fields(sample, "$.selectedSample", sample_true_flags + sample_false_flags)
    for flag in sample_true_flags:
        if sample[flag] is not True:
            raise ShapeError(f"unexpected value at $.selectedSample.{flag}: expected true")
    for flag in sample_false_flags:
        if sample[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedSample.{flag}: expected false")

    sections = require_object_array(require_field(root, "$", "detailSections"), "$.detailSections", min_items=1)
    section_ids = set()
    for section in sections:
        path = "$.detailSections[]"
        require_string_fields(section, path, ["sectionId", "sectionState", "summary"])
        require_string_array(require_field(section, path, "allowedFieldRefs"), child(path, "allowedFieldRefs"), min_items=1)
        require_string_array(require_field(section, path, "blockedFieldRefs"), child(path, "blockedFieldRefs"), min_items=1)
        require_bool_fields(section, path, ["summaryOnly", "contentIncluded", "pathEchoAllowed", "rawCommandIncluded"])
        section_ids.add(section["sectionId"])
        if section["summaryOnly"] is not True:
            raise ShapeError(f"unexpected value at {child(path, 'summaryOnly')}: expected true")
        for field in ["contentIncluded", "pathEchoAllowed", "rawCommandIncluded"]:
            if section[field] is not False:
                raise ShapeError(f"unexpected value at {child(path, field)}: expected false")
    for section_id in ["sample_identity", "boundary_references", "execution_status"]:
        if section_id not in section_ids:
            raise ShapeError(f"missing MCP sample detail section: {section_id}")

    flow = expect_object(require_field(root, "$", "detailFlow"), "$.detailFlow")
    require_string_fields(
        flow,
        "$.detailFlow",
        [
            "flowId",
            "flowState",
            "detailKind",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.detailFlow.flowState: expected blocked")
    if flow["commandKind"] != "planned-cli-fixed-args":
        raise ShapeError("unexpected value at $.detailFlow.commandKind: expected planned-cli-fixed-args")
    require_string_array(
        require_field(flow, "$.detailFlow", "fixedArgsPreview"),
        "$.detailFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.detailFlow", "steps"), "$.detailFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.detailFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "sample_catalog_reference",
        "sample_result_reference",
        "detail_display_gate",
        "sample_invocation_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing MCP sample detail flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.detailFlow", "blockedReasonRefs"),
        "$.detailFlow.blockedReasonRefs",
        min_items=1,
    )

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "rawCommandIncluded",
        "localPathsIncluded",
        "repositoryPathsIncluded",
        "privatePathsIncluded",
        "labStatusPayloadIncluded",
        "workflowResultContentIncluded",
        "resultPayloadIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForSampleDetailDescriptor"]
    review_false_flags = [
        "approvedForSampleDiscovery",
        "approvedForClientImplementation",
        "approvedForTransport",
        "approvedForRuntime",
        "approvedForCommandExecution",
        "approvedForInvocation",
        "approvedForPermissionExecution",
        "approvedForApprovalExecution",
        "approvedForAuditLogWrite",
        "approvedForPayloadRead",
        "approvedForReportRead",
        "approvedForReportWrite",
        "approvedForArtifactRead",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "repositoryMutationAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "toolInvocationAllowed",
        "permissionExecutionAllowed",
        "approvalExecutionAllowed",
        "auditLogWriteAllowed",
        "commandExecutionAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "sample-discovery",
        "tool-discovery",
        "mcp-server-start",
        "mcp-client-start",
        "mcp-transport-open",
        "mcp-runtime-start",
        "command-execution",
        "tool-invocation",
        "permission-executor",
        "approval-executor",
        "audit-logger",
        "result-payload-read",
        "lab-status-payload-read",
        "workflow-result-read",
        "report-read",
        "report-write",
        "artifact-read",
        "artifact-write",
        "repository-read",
        "repository-mutation",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "model-load",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "sampleDetailFixtureOnly",
    ]
    false_flags = [
        "sampleDiscoveryImplemented",
        "sampleToolImplemented",
        "sampleToolExecuted",
        "sampleResultProduced",
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpTransportImplemented",
        "commandExecutorImplemented",
        "permissionExecutorImplemented",
        "approvalExecutorImplemented",
        "auditLoggerImplemented",
        "resultPayloadReaderImplemented",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "toolInvocationImplemented",
        "stableApiAbiClaim",
        "marketplaceClaim",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "rawCommandIncluded",
        "localPathsIncluded",
        "repositoryPathsIncluded",
        "labStatusPayloadIncluded",
        "workflowResultContentIncluded",
        "resultPayloadIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_mcp_verification_run_comparison(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-verification-run-comparison.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "comparisonId",
            "comparisonState",
            "adapterState",
            "defaultMode",
            "automationPath",
        ],
    )
    if root["comparisonState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.comparisonState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in ["pathEchoAllowed", "artifactWriteAllowed"]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")

    inputs = require_object_array(
        require_field(root, "$", "comparisonInputs"),
        "$.comparisonInputs",
        min_items=2,
    )
    run_ids = set()
    for input_item in inputs:
        path = "$.comparisonInputs[]"
        require_string_fields(
            input_item,
            path,
            [
                "inputId",
                "runId",
                "schemaVersion",
                "inputKind",
                "inputState",
                "sourceRef",
                "summary",
            ],
        )
        run_id = input_item["runId"]
        if run_id in run_ids:
            raise ShapeError(f"duplicate value at $.comparisonInputs[].runId: {run_id}")
        run_ids.add(run_id)
        if input_item["inputKind"] != "workflow_result_summary":
            raise ShapeError("unexpected value at $.comparisonInputs[].inputKind: expected workflow_result_summary")
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
            "artifactPathIncluded",
        ]
        require_bool_fields(input_item, path, true_fields + false_fields)
        for field in true_fields:
            if input_item[field] is not True:
                raise ShapeError(f"unexpected value at $.comparisonInputs[].{field}: expected true")
        for field in false_fields:
            if input_item[field] is not False:
                raise ShapeError(f"unexpected value at $.comparisonInputs[].{field}: expected false")
        fields = require_object_array(
            require_field(input_item, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.comparisonInputs[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    policy = expect_object(require_field(root, "$", "comparisonPolicy"), "$.comparisonPolicy")
    require_string_fields(policy, "$.comparisonPolicy", ["state", "comparisonKind", "redactionRule"])
    expect_integer(require_field(policy, "$.comparisonPolicy", "maxRuns"), "$.comparisonPolicy.maxRuns")
    true_policy_flags = ["summaryOnly", "approvalRequired", "auditRequired"]
    false_policy_flags = [
        "commandExecutionAllowed",
        "localFileReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
    ]
    require_bool_fields(policy, "$.comparisonPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.comparisonPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.comparisonPolicy.{flag}: expected false")

    comparison = expect_object(require_field(root, "$", "sampleComparison"), "$.sampleComparison")
    require_string_fields(
        comparison,
        "$.sampleComparison",
        ["comparisonState", "baselineRunId", "candidateRunId", "overallStatus"],
    )
    if comparison["comparisonState"] != "summary_only_fixture":
        raise ShapeError("unexpected value at $.sampleComparison.comparisonState: expected summary_only_fixture")
    runs = require_object_array(require_field(comparison, "$.sampleComparison", "runs"), "$.sampleComparison.runs", min_items=2)
    for run in runs:
        path = "$.sampleComparison.runs[]"
        require_string_fields(run, path, ["runId", "workflowId", "status"])
        if run["runId"] not in run_ids:
            raise ShapeError(f"unexpected value at $.sampleComparison.runs[].runId: unknown run {run['runId']}")
        for field in ["diagnosticCount", "warningCount", "errorCount", "durationMs"]:
            expect_integer(require_field(run, path, field), child(path, field))
        run_false_fields = [
            "pathIncluded",
            "artifactPathIncluded",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogsIncluded",
        ]
        require_bool_fields(run, path, run_false_fields)
        for field in run_false_fields:
            if run[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleComparison.runs[].{field}: expected false")

    deltas = expect_object(require_field(comparison, "$.sampleComparison", "deltas"), "$.sampleComparison.deltas")
    for field in ["diagnosticCountDelta", "warningCountDelta", "errorCountDelta"]:
        expect_integer(require_field(deltas, "$.sampleComparison.deltas", field), f"$.sampleComparison.deltas.{field}")
    require_string_array(require_field(deltas, "$.sampleComparison.deltas", "newDiagnosticKinds"), "$.sampleComparison.deltas.newDiagnosticKinds")
    require_string_array(require_field(deltas, "$.sampleComparison.deltas", "resolvedDiagnosticKinds"), "$.sampleComparison.deltas.resolvedDiagnosticKinds")
    comparison_true_fields = ["summaryOnly"]
    comparison_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
    ]
    require_bool_fields(comparison, "$.sampleComparison", comparison_true_fields + comparison_false_fields)
    if comparison["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.sampleComparison.summaryOnly: expected true")
    for field in comparison_false_fields:
        if comparison[field] is not False:
            raise ShapeError(f"unexpected value at $.sampleComparison.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "permission-executor",
        "tool-invocation",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "raw-trace-read",
        "raw-report-read",
        "artifact-read",
        "artifact-write",
        "report-write",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "comparisonFixtureOnly", "summaryOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "permissionExecutorImplemented",
        "toolInvocationPathImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
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
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "telemetry",
        "writeBack",
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


def validate_mcp_pr_summary_handoff(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-pr-summary-handoff.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "handoffId",
            "handoffState",
            "adapterState",
            "defaultMode",
            "handoffKind",
        ],
    )
    if root["handoffState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.handoffState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["handoffKind"] != "pr_summary_packet":
        raise ShapeError("unexpected value at $.handoffKind: expected pr_summary_packet")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "pathEchoAllowed",
            "artifactWriteAllowed",
            "rawReportAllowed",
            "writeActionAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")

    inputs = require_object_array(
        require_field(root, "$", "handoffInputs"),
        "$.handoffInputs",
        min_items=2,
    )
    input_ids = set()
    allowed_input_kinds = {"issue_summary", "change_summary", "validation_summary"}
    for input_item in inputs:
        path = "$.handoffInputs[]"
        require_string_fields(
            input_item,
            path,
            [
                "inputId",
                "inputKind",
                "inputState",
                "sourceRef",
                "summary",
            ],
        )
        input_id = input_item["inputId"]
        if input_id in input_ids:
            raise ShapeError(f"duplicate value at $.handoffInputs[].inputId: {input_id}")
        input_ids.add(input_id)
        if input_item["inputKind"] not in allowed_input_kinds:
            raise ShapeError(
                "unexpected value at $.handoffInputs[].inputKind: "
                f"expected one of {sorted(allowed_input_kinds)}"
            )
        if input_item["inputState"] != "approved_summary_only":
            raise ShapeError("unexpected value at $.handoffInputs[].inputState: expected approved_summary_only")
        true_fields = ["summaryOnly", "approvalRequired"]
        false_fields = [
            "localFileRead",
            "repositoryRead",
            "rawTraceRead",
            "rawReportRead",
            "artifactRead",
            "privatePathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
            "artifactPathIncluded",
        ]
        require_bool_fields(input_item, path, true_fields + false_fields)
        for field in true_fields:
            if input_item[field] is not True:
                raise ShapeError(f"unexpected value at $.handoffInputs[].{field}: expected true")
        for field in false_fields:
            if input_item[field] is not False:
                raise ShapeError(f"unexpected value at $.handoffInputs[].{field}: expected false")
        fields = require_object_array(
            require_field(input_item, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.handoffInputs[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    policy = expect_object(require_field(root, "$", "handoffPolicy"), "$.handoffPolicy")
    require_string_fields(policy, "$.handoffPolicy", ["state", "handoffKind", "redactionRule"])
    if policy["state"] != "planned":
        raise ShapeError("unexpected value at $.handoffPolicy.state: expected planned")
    if policy["handoffKind"] != "summary_only_pr_metadata":
        raise ShapeError(
            "unexpected value at $.handoffPolicy.handoffKind: expected summary_only_pr_metadata"
        )
    expect_integer(require_field(policy, "$.handoffPolicy", "maxSections"), "$.handoffPolicy.maxSections")
    true_policy_flags = ["summaryOnly", "approvalRequired", "auditRequired"]
    false_policy_flags = [
        "commandExecutionAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
        "prCreationAllowed",
        "prCommentAllowed",
        "issueCommentAllowed",
        "projectMutationAllowed",
        "publicTextPublicationAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
    ]
    require_bool_fields(policy, "$.handoffPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.handoffPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.handoffPolicy.{flag}: expected false")

    handoff = expect_object(require_field(root, "$", "sampleHandoff"), "$.sampleHandoff")
    require_string_fields(
        handoff,
        "$.sampleHandoff",
        ["handoffState", "targetRepository", "titlePreview"],
    )
    if handoff["handoffState"] != "summary_only_fixture":
        raise ShapeError("unexpected value at $.sampleHandoff.handoffState: expected summary_only_fixture")

    section_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
    ]
    sections = require_object_array(
        require_field(handoff, "$.sampleHandoff", "bodySections"),
        "$.sampleHandoff.bodySections",
        min_items=2,
    )
    for section in sections:
        path = "$.sampleHandoff.bodySections[]"
        require_string_fields(section, path, ["sectionId", "sectionKind", "heading", "summary"])
        require_bool_fields(section, path, ["summaryOnly"] + section_false_fields)
        if section["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleHandoff.bodySections[].summaryOnly: expected true")
        for field in section_false_fields:
            if section[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleHandoff.bodySections[].{field}: expected false")

    checklist = require_object_array(
        require_field(handoff, "$.sampleHandoff", "checklistItems"),
        "$.sampleHandoff.checklistItems",
        min_items=1,
    )
    for item in checklist:
        path = "$.sampleHandoff.checklistItems[]"
        require_string_fields(item, path, ["itemId", "state", "label"])
        require_bool_fields(
            item,
            path,
            ["summaryOnly", "commandIncluded", "pathIncluded", "artifactPathIncluded"],
        )
        if item["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleHandoff.checklistItems[].summaryOnly: expected true")
        for field in ["commandIncluded", "pathIncluded", "artifactPathIncluded"]:
            if item[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleHandoff.checklistItems[].{field}: expected false")

    validation_lines = require_object_array(
        require_field(handoff, "$.sampleHandoff", "validationLines"),
        "$.sampleHandoff.validationLines",
        min_items=1,
    )
    for line in validation_lines:
        path = "$.sampleHandoff.validationLines[]"
        require_string_fields(line, path, ["lineId", "result", "summary"])
        require_bool_fields(
            line,
            path,
            [
                "summaryOnly",
                "commandIncluded",
                "stdoutIncluded",
                "stderrIncluded",
                "rawLogsIncluded",
                "artifactPathIncluded",
            ],
        )
        if line["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleHandoff.validationLines[].summaryOnly: expected true")
        for field in [
            "commandIncluded",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogsIncluded",
            "artifactPathIncluded",
        ]:
            if line[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleHandoff.validationLines[].{field}: expected false")

    handoff_true_fields = ["summaryOnly"]
    handoff_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
        "prCreated",
        "prCommentCreated",
        "issueCommentCreated",
        "projectUpdated",
        "publicTextPublished",
    ]
    require_bool_fields(handoff, "$.sampleHandoff", handoff_true_fields + handoff_false_fields)
    if handoff["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.sampleHandoff.summaryOnly: expected true")
    for field in handoff_false_fields:
        if handoff[field] is not False:
            raise ShapeError(f"unexpected value at $.sampleHandoff.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
        "prCreationAllowed",
        "prCommentAllowed",
        "issueCommentAllowed",
        "projectMutationAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "permission-executor",
        "tool-invocation",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "repository-write-back",
        "pr-create",
        "pr-comment",
        "issue-comment",
        "project-update",
        "public-text-publish",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "handoffFixtureOnly", "summaryOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "permissionExecutorImplemented",
        "toolInvocationPathImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "prCreation",
        "prComment",
        "issueComment",
        "projectMutation",
        "publicTextPublication",
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
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "telemetry",
        "writeBack",
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


def validate_mcp_review_packet(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-review-packet.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "reviewPacketId",
            "reviewState",
            "adapterState",
            "defaultMode",
            "packetKind",
            "automationPath",
        ],
    )
    if root["reviewState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.reviewState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["packetKind"] != "summary_only_review_packet":
        raise ShapeError("unexpected value at $.packetKind: expected summary_only_review_packet")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "pathEchoAllowed",
            "artifactWriteAllowed",
            "rawReportAllowed",
            "writeActionAllowed",
            "toolInvocationAllowed",
            "commandExecutionAllowed",
            "reportWriteAllowed",
            "publicTextPublicationAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")

    inputs = require_object_array(
        require_field(root, "$", "reviewInputs"),
        "$.reviewInputs",
        min_items=4,
    )
    input_ids = set()
    allowed_input_kinds = {
        "permission_summary",
        "approval_summary",
        "blocked_result_summary",
        "validation_comparison_summary",
        "handoff_summary",
    }
    for input_item in inputs:
        path = "$.reviewInputs[]"
        require_string_fields(
            input_item,
            path,
            [
                "inputId",
                "inputKind",
                "inputState",
                "sourceRef",
                "summary",
            ],
        )
        input_id = input_item["inputId"]
        if input_id in input_ids:
            raise ShapeError(f"duplicate value at $.reviewInputs[].inputId: {input_id}")
        input_ids.add(input_id)
        if input_item["inputKind"] not in allowed_input_kinds:
            raise ShapeError(
                "unexpected value at $.reviewInputs[].inputKind: "
                f"expected one of {sorted(allowed_input_kinds)}"
            )
        if input_item["inputState"] != "approved_summary_only":
            raise ShapeError("unexpected value at $.reviewInputs[].inputState: expected approved_summary_only")
        true_fields = ["summaryOnly", "approvalRequired"]
        false_fields = [
            "localFileRead",
            "repositoryRead",
            "rawTraceRead",
            "rawReportRead",
            "artifactRead",
            "privatePathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
            "artifactPathIncluded",
        ]
        require_bool_fields(input_item, path, true_fields + false_fields)
        for field in true_fields:
            if input_item[field] is not True:
                raise ShapeError(f"unexpected value at $.reviewInputs[].{field}: expected true")
        for field in false_fields:
            if input_item[field] is not False:
                raise ShapeError(f"unexpected value at $.reviewInputs[].{field}: expected false")
        fields = require_object_array(
            require_field(input_item, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.reviewInputs[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    policy = expect_object(require_field(root, "$", "reviewPolicy"), "$.reviewPolicy")
    require_string_fields(policy, "$.reviewPolicy", ["state", "packetKind", "redactionRule"])
    if policy["state"] != "planned":
        raise ShapeError("unexpected value at $.reviewPolicy.state: expected planned")
    if policy["packetKind"] != "summary_only_review_packet":
        raise ShapeError("unexpected value at $.reviewPolicy.packetKind: expected summary_only_review_packet")
    expect_integer(require_field(policy, "$.reviewPolicy", "maxSections"), "$.reviewPolicy.maxSections")
    true_policy_flags = ["summaryOnly", "approvalRequired", "auditRequired"]
    false_policy_flags = [
        "commandExecutionAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
        "prCreationAllowed",
        "prCommentAllowed",
        "issueCommentAllowed",
        "projectMutationAllowed",
        "publicTextPublicationAllowed",
        "toolInvocationAllowed",
        "permissionExecutionAllowed",
        "approvalExecutionAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
    ]
    require_bool_fields(policy, "$.reviewPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewPolicy.{flag}: expected false")

    packet = expect_object(require_field(root, "$", "sampleReviewPacket"), "$.sampleReviewPacket")
    require_string_fields(
        packet,
        "$.sampleReviewPacket",
        ["reviewPacketState", "targetRepository", "titlePreview"],
    )
    if packet["reviewPacketState"] != "summary_only_fixture":
        raise ShapeError("unexpected value at $.sampleReviewPacket.reviewPacketState: expected summary_only_fixture")

    section_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
    ]
    sections = require_object_array(
        require_field(packet, "$.sampleReviewPacket", "reviewSections"),
        "$.sampleReviewPacket.reviewSections",
        min_items=2,
    )
    for section in sections:
        path = "$.sampleReviewPacket.reviewSections[]"
        require_string_fields(section, path, ["sectionId", "sectionKind", "heading", "summary"])
        require_bool_fields(section, path, ["summaryOnly"] + section_false_fields)
        if section["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleReviewPacket.reviewSections[].summaryOnly: expected true")
        for field in section_false_fields:
            if section[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleReviewPacket.reviewSections[].{field}: expected false")

    risk_rows = require_object_array(
        require_field(packet, "$.sampleReviewPacket", "riskRows"),
        "$.sampleReviewPacket.riskRows",
        min_items=1,
    )
    for row in risk_rows:
        path = "$.sampleReviewPacket.riskRows[]"
        require_string_fields(row, path, ["rowId", "severity", "sourceRef", "summary", "mitigation"])
        require_bool_fields(
            row,
            path,
            ["summaryOnly", "commandIncluded", "pathIncluded", "artifactPathIncluded"],
        )
        if row["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleReviewPacket.riskRows[].summaryOnly: expected true")
        for field in ["commandIncluded", "pathIncluded", "artifactPathIncluded"]:
            if row[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleReviewPacket.riskRows[].{field}: expected false")

    checklist = require_object_array(
        require_field(packet, "$.sampleReviewPacket", "checklistItems"),
        "$.sampleReviewPacket.checklistItems",
        min_items=1,
    )
    for item in checklist:
        path = "$.sampleReviewPacket.checklistItems[]"
        require_string_fields(item, path, ["itemId", "state", "label"])
        require_bool_fields(
            item,
            path,
            ["summaryOnly", "commandIncluded", "pathIncluded", "artifactPathIncluded"],
        )
        if item["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleReviewPacket.checklistItems[].summaryOnly: expected true")
        for field in ["commandIncluded", "pathIncluded", "artifactPathIncluded"]:
            if item[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleReviewPacket.checklistItems[].{field}: expected false")

    validation_lines = require_object_array(
        require_field(packet, "$.sampleReviewPacket", "validationLines"),
        "$.sampleReviewPacket.validationLines",
        min_items=1,
    )
    for line in validation_lines:
        path = "$.sampleReviewPacket.validationLines[]"
        require_string_fields(line, path, ["lineId", "result", "summary"])
        require_bool_fields(
            line,
            path,
            [
                "summaryOnly",
                "commandIncluded",
                "stdoutIncluded",
                "stderrIncluded",
                "rawLogsIncluded",
                "artifactPathIncluded",
            ],
        )
        if line["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleReviewPacket.validationLines[].summaryOnly: expected true")
        for field in [
            "commandIncluded",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogsIncluded",
            "artifactPathIncluded",
        ]:
            if line[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleReviewPacket.validationLines[].{field}: expected false")

    packet_true_fields = ["summaryOnly"]
    packet_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
        "toolInvoked",
        "prCreated",
        "prCommentCreated",
        "issueCommentCreated",
        "projectUpdated",
        "publicTextPublished",
    ]
    require_bool_fields(packet, "$.sampleReviewPacket", packet_true_fields + packet_false_fields)
    if packet["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.sampleReviewPacket.summaryOnly: expected true")
    for field in packet_false_fields:
        if packet[field] is not False:
            raise ShapeError(f"unexpected value at $.sampleReviewPacket.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
        "prCreationAllowed",
        "prCommentAllowed",
        "issueCommentAllowed",
        "projectMutationAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "approval-executor",
        "permission-executor",
        "tool-invocation",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "repository-write-back",
        "pr-create",
        "pr-comment",
        "issue-comment",
        "project-update",
        "public-text-publish",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "reviewPacketFixtureOnly", "summaryOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "approvalExecutorImplemented",
        "permissionExecutorImplemented",
        "toolInvocationPathImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "prCreation",
        "prComment",
        "issueComment",
        "projectMutation",
        "publicTextPublication",
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
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "telemetry",
        "writeBack",
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


def validate_mcp_evidence_manifest(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-evidence-manifest.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "manifestId",
            "manifestState",
            "adapterState",
            "defaultMode",
            "manifestKind",
        ],
    )
    if root["manifestState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.manifestState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["manifestKind"] != "approved_summary_evidence_refs":
        raise ShapeError(
            "unexpected value at $.manifestKind: expected approved_summary_evidence_refs"
        )

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=3,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        if "summaryOnly" in ref and expect_bool(require_field(ref, path, "summaryOnly"), child(path, "summaryOnly")) is not True:
            raise ShapeError("unexpected value at $.sourceBoundaryRefs[].summaryOnly: expected true")
        for field in [
            "pathEchoAllowed",
            "artifactReadAllowed",
            "artifactWriteAllowed",
            "hardwareAccessAllowed",
            "rawTraceAllowed",
            "rawReportAllowed",
            "publicTextPublicationAllowed",
            "repositoryMutationAllowed",
            "toolInvocationAllowed",
            "auditLoggerAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")

    evidence_refs = require_object_array(
        require_field(root, "$", "approvedEvidenceRefs"),
        "$.approvedEvidenceRefs",
        min_items=3,
    )
    evidence_ids = set()
    for evidence in evidence_refs:
        path = "$.approvedEvidenceRefs[]"
        require_string_fields(
            evidence,
            path,
            ["evidenceId", "evidenceKind", "evidenceState", "sourceRef", "summary"],
        )
        evidence_id = evidence["evidenceId"]
        if evidence_id in evidence_ids:
            raise ShapeError(f"duplicate value at $.approvedEvidenceRefs[].evidenceId: {evidence_id}")
        evidence_ids.add(evidence_id)
        if evidence["evidenceState"] != "approved_summary_only":
            raise ShapeError(
                "unexpected value at $.approvedEvidenceRefs[].evidenceState: "
                "expected approved_summary_only"
            )
        true_fields = ["summaryOnly", "approvalRequired", "approvedSummaryRef"]
        false_fields = [
            "localFileRead",
            "repositoryRead",
            "rawTraceRead",
            "rawReportRead",
            "rawLogRead",
            "artifactRead",
            "artifactWrite",
            "privatePathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
            "artifactPathIncluded",
            "hardwareDumpIncluded",
            "boardDumpIncluded",
            "modelWeightPathIncluded",
        ]
        require_bool_fields(evidence, path, true_fields + false_fields)
        for field in true_fields:
            if evidence[field] is not True:
                raise ShapeError(f"unexpected value at $.approvedEvidenceRefs[].{field}: expected true")
        for field in false_fields:
            if evidence[field] is not False:
                raise ShapeError(f"unexpected value at $.approvedEvidenceRefs[].{field}: expected false")
        descriptors = require_object_array(
            require_field(evidence, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for descriptor in descriptors:
            require_string_fields(
                descriptor,
                "$.approvedEvidenceRefs[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    policy = expect_object(require_field(root, "$", "manifestPolicy"), "$.manifestPolicy")
    require_string_fields(policy, "$.manifestPolicy", ["state", "manifestKind", "redactionRule"])
    if policy["state"] != "planned":
        raise ShapeError("unexpected value at $.manifestPolicy.state: expected planned")
    if policy["manifestKind"] != "approved_summary_refs_only":
        raise ShapeError(
            "unexpected value at $.manifestPolicy.manifestKind: "
            "expected approved_summary_refs_only"
        )
    expect_integer(require_field(policy, "$.manifestPolicy", "maxEvidenceRefs"), "$.manifestPolicy.maxEvidenceRefs")
    true_policy_flags = ["summaryOnly", "approvalRequired", "auditRequired"]
    false_policy_flags = [
        "mcpRuntimeAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "evidenceArtifactWriteAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
        "publicTextPublicationAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
        "hardwareAccessAllowed",
        "kv260AccessAllowed",
        "fpgaRepoAccessAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "modelLoadAllowed",
    ]
    require_bool_fields(policy, "$.manifestPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.manifestPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.manifestPolicy.{flag}: expected false")

    manifest = expect_object(require_field(root, "$", "sampleManifest"), "$.sampleManifest")
    require_string_fields(manifest, "$.sampleManifest", ["manifestState", "targetScope", "summary"])
    if manifest["manifestState"] != "summary_only_fixture":
        raise ShapeError(
            "unexpected value at $.sampleManifest.manifestState: expected summary_only_fixture"
        )
    manifest_true_fields = ["summaryOnly"]
    manifest_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
        "hardwareDumpIncluded",
        "boardDumpIncluded",
        "modelPathsIncluded",
        "manifestPublished",
        "evidenceArtifactWritten",
    ]
    require_bool_fields(manifest, "$.sampleManifest", manifest_true_fields + manifest_false_fields)
    if manifest["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.sampleManifest.summaryOnly: expected true")
    for field in manifest_false_fields:
        if manifest[field] is not False:
            raise ShapeError(f"unexpected value at $.sampleManifest.{field}: expected false")

    row_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
        "rawLogsIncluded",
        "artifactPathIncluded",
        "hardwareDumpIncluded",
        "boardDumpIncluded",
        "modelPathIncluded",
    ]
    rows = require_object_array(
        require_field(manifest, "$.sampleManifest", "evidenceRows"),
        "$.sampleManifest.evidenceRows",
        min_items=2,
    )
    for row in rows:
        path = "$.sampleManifest.evidenceRows[]"
        require_string_fields(row, path, ["rowId", "evidenceKind", "sourceRef", "state", "summary"])
        require_bool_fields(row, path, ["summaryOnly"] + row_false_fields)
        if row["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleManifest.evidenceRows[].summaryOnly: expected true")
        for field in row_false_fields:
            if row[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleManifest.evidenceRows[].{field}: expected false")

    validation_rows = require_object_array(
        require_field(manifest, "$.sampleManifest", "validationRows"),
        "$.sampleManifest.validationRows",
        min_items=1,
    )
    for row in validation_rows:
        path = "$.sampleManifest.validationRows[]"
        require_string_fields(row, path, ["rowId", "state", "summary"])
        require_bool_fields(
            row,
            path,
            [
                "summaryOnly",
                "commandIncluded",
                "pathIncluded",
                "stdoutIncluded",
                "stderrIncluded",
                "rawLogsIncluded",
                "artifactPathIncluded",
            ],
        )
        if row["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleManifest.validationRows[].summaryOnly: expected true")
        for field in [
            "commandIncluded",
            "pathIncluded",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogsIncluded",
            "artifactPathIncluded",
        ]:
            if row[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleManifest.validationRows[].{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "evidenceArtifactWriteAllowed",
        "repositoryMutationAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "tool-invocation",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "raw-log-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "evidence-artifact-write",
        "repository-write-back",
        "public-text-publish",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "evidenceManifestFixtureOnly",
        "summaryOnly",
    ]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "evidenceArtifactWriterImplemented",
        "auditLoggerImplemented",
        "auditPersistence",
        "diagnosticsProduced",
        "reportProduced",
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
        "artifactPathsIncluded",
        "hardwareDumpIncluded",
        "boardDumpIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
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


def validate_mcp_evidence_detail(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-evidence-detail.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "evidenceDetailId",
            "detailState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["detailState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.detailState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    if not any(
        ref["refId"] == "mcp_evidence_manifest"
        and ref.get("evidenceManifestAvailable") is True
        and ref.get("evidenceDetailAvailable") is True
        and ref.get("summaryOnly") is True
        and ref.get("fileReaderAllowed") is False
        and ref.get("artifactReaderAllowed") is False
        and ref.get("reportReaderAllowed") is False
        and ref.get("reportWriterAllowed") is False
        and ref.get("toolInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_evidence_manifest disabled source reference")
    if not any(
        ref["refId"] == "mcp_review_packet"
        and ref.get("summaryOnly") is True
        and ref.get("toolInvocationAllowed") is False
        and ref.get("reportWriterAllowed") is False
        and ref.get("artifactWriteAllowed") is False
        and ref.get("repositoryMutationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_review_packet summary-only source reference")
    if not any(
        ref["refId"] == "mcp_audit_event"
        and ref.get("summaryOnly") is True
        and ref.get("auditLoggerAllowed") is False
        and ref.get("pathEchoAllowed") is False
        and ref.get("artifactWriteAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing mcp_audit_event redacted source reference")

    request = expect_object(
        require_field(root, "$", "evidenceDetailRequest"),
        "$.evidenceDetailRequest",
    )
    require_string_fields(
        request,
        "$.evidenceDetailRequest",
        [
            "requestKind",
            "commandKind",
            "selectedEvidenceId",
            "sourceReferenceKind",
            "outputBoundary",
            "summary",
        ],
    )
    if request["requestKind"] != "planned_mcp_evidence_detail":
        raise ShapeError(
            "unexpected value at $.evidenceDetailRequest.requestKind: expected planned_mcp_evidence_detail"
        )
    if request["selectedEvidenceId"] != "lab_status_evidence_summary":
        raise ShapeError(
            "unexpected value at $.evidenceDetailRequest.selectedEvidenceId: "
            "expected lab_status_evidence_summary"
        )
    require_string_array(
        require_field(request, "$.evidenceDetailRequest", "fixedArgsPreview"),
        "$.evidenceDetailRequest.fixedArgsPreview",
        min_items=1,
    )
    request_true_flags = ["summaryOnly", "inputRefOnly"]
    request_false_flags = [
        "approvalRequired",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "evidenceArtifactReadAllowed",
        "evidenceArtifactWriteAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "mcpServerAllowed",
        "mcpClientAllowed",
        "mcpRuntimeAllowed",
        "mcpTransportAllowed",
        "permissionExecutorAllowed",
        "approvalExecutorAllowed",
        "auditLoggerAllowed",
        "toolInvocationAllowed",
        "publicTextPublicationAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
        "stableApiAbiClaim",
        "marketplaceClaim",
        "runtimeClaim",
        "hardwareClaim",
    ]
    require_bool_fields(request, "$.evidenceDetailRequest", request_true_flags + request_false_flags)
    for flag in request_true_flags:
        if request[flag] is not True:
            raise ShapeError(f"unexpected value at $.evidenceDetailRequest.{flag}: expected true")
    for flag in request_false_flags:
        if request[flag] is not False:
            raise ShapeError(f"unexpected value at $.evidenceDetailRequest.{flag}: expected false")

    selected = expect_object(require_field(root, "$", "selectedEvidence"), "$.selectedEvidence")
    require_string_fields(
        selected,
        "$.selectedEvidence",
        [
            "evidenceId",
            "displayName",
            "evidenceKind",
            "evidenceState",
            "detailState",
            "manifestState",
            "sourceRef",
            "reviewSource",
            "commandPreviewKind",
            "summary",
            "evidencePolicy",
        ],
    )
    if selected["evidenceId"] != request["selectedEvidenceId"]:
        raise ShapeError("selected evidence id must match $.evidenceDetailRequest.selectedEvidenceId")
    if selected["evidenceState"] != "approved_summary_only":
        raise ShapeError("unexpected value at $.selectedEvidence.evidenceState: expected approved_summary_only")
    if selected["detailState"] != "visible_descriptor":
        raise ShapeError("unexpected value at $.selectedEvidence.detailState: expected visible_descriptor")

    input_descriptor = expect_object(
        require_field(selected, "$.selectedEvidence", "inputDescriptor"),
        "$.selectedEvidence.inputDescriptor",
    )
    require_string_fields(
        input_descriptor,
        "$.selectedEvidence.inputDescriptor",
        ["descriptorState", "acceptedInputKind", "acceptedInputSummary"],
    )
    input_false_flags = [
        "userPathAccepted",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "reportReadAllowed",
        "evidenceArtifactReadAllowed",
        "providerConfigReadAllowed",
        "environmentReadAllowed",
        "secretsReadAllowed",
        "tokensReadAllowed",
        "hardwareDumpReadAllowed",
        "boardDumpReadAllowed",
        "modelWeightPathReadAllowed",
    ]
    require_bool_fields(input_descriptor, "$.selectedEvidence.inputDescriptor", input_false_flags)
    for flag in input_false_flags:
        if input_descriptor[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedEvidence.inputDescriptor.{flag}: expected false")

    output_descriptor = expect_object(
        require_field(selected, "$.selectedEvidence", "outputDescriptor"),
        "$.selectedEvidence.outputDescriptor",
    )
    require_string_fields(output_descriptor, "$.selectedEvidence.outputDescriptor", ["descriptorState", "boundaryRef"])
    output_true_flags = ["summaryOnly"]
    output_false_flags = [
        "payloadIncluded",
        "responseBodyIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
        "hardwareDumpIncluded",
        "boardDumpIncluded",
        "modelPathsIncluded",
    ]
    require_bool_fields(output_descriptor, "$.selectedEvidence.outputDescriptor", output_true_flags + output_false_flags)
    if output_descriptor["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.selectedEvidence.outputDescriptor.summaryOnly: expected true")
    for flag in output_false_flags:
        if output_descriptor[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedEvidence.outputDescriptor.{flag}: expected false")

    field_descriptors = require_object_array(
        require_field(selected, "$.selectedEvidence", "fieldDescriptors"),
        "$.selectedEvidence.fieldDescriptors",
        min_items=1,
    )
    for descriptor in field_descriptors:
        path = "$.selectedEvidence.fieldDescriptors[]"
        require_string_fields(descriptor, path, ["fieldName", "valueKind", "policy"])
        require_bool_fields(descriptor, path, ["detailIncluded", "rawValueIncluded"])
        if descriptor["detailIncluded"] is not True:
            raise ShapeError("unexpected value at $.selectedEvidence.fieldDescriptors[].detailIncluded: expected true")
        if descriptor["rawValueIncluded"] is not False:
            raise ShapeError("unexpected value at $.selectedEvidence.fieldDescriptors[].rawValueIncluded: expected false")

    access = expect_object(
        require_field(selected, "$.selectedEvidence", "accessPolicy"),
        "$.selectedEvidence.accessPolicy",
    )
    access_true_flags = [
        "requiresSeparateArtifactReadBoundary",
        "requiresSeparateReportReadBoundary",
        "approvalRequiredBeforeArtifactRead",
        "approvedForManifest",
        "approvedForDetail",
    ]
    access_false_flags = [
        "approvedForArtifactRead",
        "approvedForReportRead",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "evidenceArtifactReadAllowed",
        "evidenceArtifactWriteAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "repositoryMutationAllowed",
    ]
    require_bool_fields(access, "$.selectedEvidence.accessPolicy", access_true_flags + access_false_flags)
    for flag in access_true_flags:
        if access[flag] is not True:
            raise ShapeError(f"unexpected value at $.selectedEvidence.accessPolicy.{flag}: expected true")
    for flag in access_false_flags:
        if access[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedEvidence.accessPolicy.{flag}: expected false")

    related = require_object_array(
        require_field(root, "$", "relatedEvidenceRefs"),
        "$.relatedEvidenceRefs",
        min_items=1,
    )
    for evidence in related:
        path = "$.relatedEvidenceRefs[]"
        require_string_fields(evidence, path, ["evidenceId", "relationship"])
        require_bool_fields(
            evidence,
            path,
            ["detailIncluded", "approvedForDetail", "artifactReadAllowed", "reportReadAllowed"],
        )
        for flag in ["detailIncluded", "approvedForDetail", "artifactReadAllowed", "reportReadAllowed"]:
            if evidence[flag] is not False:
                raise ShapeError(f"unexpected value at $.relatedEvidenceRefs[].{flag}: expected false")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(
        require_field(display, "$.displayPolicy", "allowedFields"),
        "$.displayPolicy.allowedFields",
        min_items=1,
    )
    require_string_array(
        require_field(display, "$.displayPolicy", "blockedFields"),
        "$.displayPolicy.blockedFields",
        min_items=1,
    )
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "privatePathsIncluded",
        "payloadIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
        "artifactPathsIncluded",
        "reportContentIncluded",
        "hardwareDumpIncluded",
        "boardDumpIncluded",
        "modelPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    if display["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.displayPolicy.summaryOnly: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "evidenceArtifactReadAllowed",
        "evidenceArtifactWriteAllowed",
        "auditLogWriteAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "repositoryMutationAllowed",
        "publicTextPublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-start",
        "mcp-client-session",
        "mcp-client-runtime",
        "mcp-transport-start",
        "tool-invocation",
        "permission-executor",
        "approval-executor",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "raw-log-read",
        "artifact-read",
        "artifact-write",
        "report-read",
        "report-write",
        "evidence-artifact-read",
        "evidence-artifact-write",
        "audit-log-write",
        "repository-write-back",
        "public-text-publish",
        "marketplace-flow",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "summaryOnly", "evidenceDetailFixtureOnly"]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpTransportImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "permissionExecutorImplemented",
        "approvalExecutorImplemented",
        "auditLoggerImplemented",
        "auditPersistence",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "evidenceArtifactReaderImplemented",
        "evidenceArtifactWriterImplemented",
        "diagnosticsProduced",
        "reportProduced",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
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
        "rawTraceIncluded",
        "rawReportIncluded",
        "artifactPathsIncluded",
        "hardwareDumpIncluded",
        "boardDumpIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_mcp_invocation_request(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-invocation-request.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "invocationRequestId",
            "requestId",
            "decisionId",
            "reviewPacketId",
            "requestState",
            "adapterState",
            "defaultMode",
            "automationPath",
        ],
    )
    if root["requestState"] != "blocked_by_policy":
        raise ShapeError("unexpected value at $.requestState: expected blocked_by_policy")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "approvalExecutorAllowed",
            "permissionExecutorAllowed",
            "toolInvocationAllowed",
            "commandExecutionAllowed",
            "pathEchoAllowed",
            "loggerAllowed",
            "artifactWriteAllowed",
            "repositoryMutationAllowed",
            "writeActionAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")
        if "approved" in ref and expect_bool(require_field(ref, path, "approved"), child(path, "approved")) is not False:
            raise ShapeError("unexpected value at $.sourceBoundaryRefs[].approved: expected false")

    request = expect_object(require_field(root, "$", "invocationRequest"), "$.invocationRequest")
    require_string_fields(
        request,
        "$.invocationRequest",
        [
            "requestKind",
            "toolId",
            "commandKind",
            "permissionProfile",
            "approvedInputReferenceKind",
            "outputBoundary",
            "summary",
        ],
    )
    if request["requestKind"] != "planned_mcp_tool_invocation_gate":
        raise ShapeError(
            "unexpected value at $.invocationRequest.requestKind: "
            "expected planned_mcp_tool_invocation_gate"
        )
    require_string_array(
        require_field(request, "$.invocationRequest", "fixedArgsPreview"),
        "$.invocationRequest.fixedArgsPreview",
        min_items=1,
    )
    request_true_fields = ["summaryOnly", "approvalRequired", "inputRefOnly"]
    request_false_fields = [
        "approved",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "toolInvocationAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
    ]
    require_bool_fields(request, "$.invocationRequest", request_true_fields + request_false_fields)
    for field in request_true_fields:
        if request[field] is not True:
            raise ShapeError(f"unexpected value at $.invocationRequest.{field}: expected true")
    for field in request_false_fields:
        if request[field] is not False:
            raise ShapeError(f"unexpected value at $.invocationRequest.{field}: expected false")

    decision = expect_object(require_field(root, "$", "invocationDecision"), "$.invocationDecision")
    require_string_fields(decision, "$.invocationDecision", ["state", "reason"])
    if decision["state"] != "not_invoked":
        raise ShapeError("unexpected value at $.invocationDecision.state: expected not_invoked")
    decision_true_fields = ["denied"]
    decision_false_fields = [
        "approved",
        "mcpServerStarted",
        "mcpClientSessionStarted",
        "toolInvocationStarted",
        "approvalExecutorCalled",
        "permissionExecutorCalled",
        "commandExecutionAttempted",
        "shellExecutionAttempted",
        "runtimeExecutionAttempted",
        "localFileReadAttempted",
        "artifactReadAttempted",
        "artifactWriteAttempted",
        "repositoryMutationAttempted",
        "providerCallAttempted",
        "networkCallAttempted",
        "hardwareAccessAttempted",
        "modelLoadAttempted",
    ]
    require_bool_fields(decision, "$.invocationDecision", decision_true_fields + decision_false_fields)
    if decision["denied"] is not True:
        raise ShapeError("unexpected value at $.invocationDecision.denied: expected true")
    for field in decision_false_fields:
        if decision[field] is not False:
            raise ShapeError(f"unexpected value at $.invocationDecision.{field}: expected false")

    context = expect_object(require_field(root, "$", "plannedToolContext"), "$.plannedToolContext")
    require_string_fields(context, "$.plannedToolContext", ["contextKind", "contextState"])
    if context["contextKind"] != "summary_only_mcp_tool_context":
        raise ShapeError(
            "unexpected value at $.plannedToolContext.contextKind: "
            "expected summary_only_mcp_tool_context"
        )
    context_true_fields = ["summaryOnly", "approvedInputReferenceOnly"]
    context_false_fields = [
        "privatePathsIncluded",
        "localFileRead",
        "repositoryRead",
        "artifactRead",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "modelWeightPathsIncluded",
    ]
    require_bool_fields(context, "$.plannedToolContext", context_true_fields + context_false_fields)
    for field in context_true_fields:
        if context[field] is not True:
            raise ShapeError(f"unexpected value at $.plannedToolContext.{field}: expected true")
    for field in context_false_fields:
        if context[field] is not False:
            raise ShapeError(f"unexpected value at $.plannedToolContext.{field}: expected false")
    require_string_array(
        require_field(context, "$.plannedToolContext", "allowedSourceKinds"),
        "$.plannedToolContext.allowedSourceKinds",
        min_items=1,
    )

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

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
        "tool-invocation",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "invocationRequestFixtureOnly",
        "summaryOnly",
    ]
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
        "repositoryRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "diagnosticsProduced",
        "reportProduced",
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
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
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


def validate_mcp_client_session_state(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.mcp-client-session-state.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "clientSessionStateId",
            "adapterState",
            "defaultMode",
            "automationPath",
            "sessionState",
            "connectionState",
            "transportState",
        ],
    )
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["sessionState"] != "not_started":
        raise ShapeError("unexpected value at $.sessionState: expected not_started")
    if root["connectionState"] != "not_configured":
        raise ShapeError("unexpected value at $.connectionState: expected not_configured")
    if root["transportState"] != "not_open":
        raise ShapeError("unexpected value at $.transportState: expected not_open")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "clientRuntimeAllowed",
            "serverRuntimeAllowed",
            "approvalExecutorAllowed",
            "permissionExecutorAllowed",
            "sessionStartAllowed",
            "toolInvocationAllowed",
            "commandExecutionAllowed",
            "pathEchoAllowed",
            "loggerAllowed",
            "artifactWriteAllowed",
            "repositoryMutationAllowed",
            "writeActionAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")
        if "approved" in ref and expect_bool(require_field(ref, path, "approved"), child(path, "approved")) is not False:
            raise ShapeError("unexpected value at $.sourceBoundaryRefs[].approved: expected false")
        if "toolCatalogAvailableAsData" in ref and expect_bool(
            require_field(ref, path, "toolCatalogAvailableAsData"),
            child(path, "toolCatalogAvailableAsData"),
        ) is not True:
            raise ShapeError(
                "unexpected value at $.sourceBoundaryRefs[].toolCatalogAvailableAsData: "
                "expected true"
            )

    session = expect_object(require_field(root, "$", "clientSession"), "$.clientSession")
    require_string_fields(
        session,
        "$.clientSession",
        [
            "sessionKind",
            "lifecycleState",
            "connectionPolicy",
            "toolCatalogState",
            "approvalState",
            "invocationState",
            "summary",
        ],
    )
    if session["sessionKind"] != "planned_mcp_client_session_state":
        raise ShapeError(
            "unexpected value at $.clientSession.sessionKind: "
            "expected planned_mcp_client_session_state"
        )
    if session["lifecycleState"] != "not_started":
        raise ShapeError("unexpected value at $.clientSession.lifecycleState: expected not_started")
    if session["approvalState"] != "not_approved":
        raise ShapeError("unexpected value at $.clientSession.approvalState: expected not_approved")
    if session["invocationState"] != "not_invoked":
        raise ShapeError("unexpected value at $.clientSession.invocationState: expected not_invoked")
    session_true_fields = ["summaryOnly"]
    session_false_fields = [
        "sessionOpen",
        "transportOpen",
        "handshakeComplete",
        "clientRuntimeStarted",
        "serverRuntimeStarted",
        "toolCatalogFetched",
        "toolInvocationStarted",
        "approvalExecutorCalled",
        "permissionExecutorCalled",
        "commandExecutionAttempted",
        "shellExecutionAttempted",
        "runtimeExecutionAttempted",
        "localFileReadAttempted",
        "repositoryReadAttempted",
        "artifactReadAttempted",
        "artifactWriteAttempted",
        "repositoryMutationAttempted",
        "providerCallAttempted",
        "networkCallAttempted",
        "hardwareAccessAttempted",
        "modelLoadAttempted",
    ]
    require_bool_fields(session, "$.clientSession", session_true_fields + session_false_fields)
    if session["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.clientSession.summaryOnly: expected true")
    for field in session_false_fields:
        if session[field] is not False:
            raise ShapeError(f"unexpected value at $.clientSession.{field}: expected false")

    rows = require_object_array(require_field(root, "$", "sessionRows"), "$.sessionRows", min_items=1)
    for row in rows:
        require_string_fields(
            row,
            "$.sessionRows[]",
            ["rowId", "state", "sourceRef", "summary", "blockedReason"],
        )

    transport = expect_object(require_field(root, "$", "transportPolicy"), "$.transportPolicy")
    require_string_fields(transport, "$.transportPolicy", ["state"])
    if transport["state"] != "not_open":
        raise ShapeError("unexpected value at $.transportPolicy.state: expected not_open")
    require_string_array(
        require_field(transport, "$.transportPolicy", "allowedTransportKinds"),
        "$.transportPolicy.allowedTransportKinds",
        min_items=1,
    )
    transport_false_fields = [
        "transportOpenAllowed",
        "stdioProcessAllowed",
        "socketAllowed",
        "networkAllowed",
        "browserAllowed",
        "ipcAllowed",
        "serverStartAllowed",
        "clientStartAllowed",
        "handshakeAllowed",
        "toolListRequestAllowed",
    ]
    require_bool_fields(transport, "$.transportPolicy", transport_false_fields)
    for field in transport_false_fields:
        if transport[field] is not False:
            raise ShapeError(f"unexpected value at $.transportPolicy.{field}: expected false")

    audit = expect_object(require_field(root, "$", "auditPolicy"), "$.auditPolicy")
    require_string_fields(audit, "$.auditPolicy", ["state", "eventSchema", "storageState"])
    audit_true_fields = ["summaryOnly"]
    audit_false_fields = [
        "auditLoggerAllowed",
        "auditPersistenceAllowed",
        "pathEchoAllowed",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
    ]
    require_bool_fields(audit, "$.auditPolicy", audit_true_fields + audit_false_fields)
    if audit["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.auditPolicy.summaryOnly: expected true")
    for field in audit_false_fields:
        if audit[field] is not False:
            raise ShapeError(f"unexpected value at $.auditPolicy.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "toolInvocationAllowed",
        "commandExecutionAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "mcp-server-start",
        "mcp-client-session",
        "mcp-client-runtime",
        "mcp-handshake",
        "transport-open",
        "tool-list-request",
        "approval-executor",
        "permission-executor",
        "tool-invocation",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "repository-write-back",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "clientSessionStateFixtureOnly",
        "summaryOnly",
    ]
    false_flags = [
        "mcpRuntimeImplemented",
        "mcpServerImplemented",
        "mcpClientImplemented",
        "mcpClientSessionStarted",
        "transportOpened",
        "handshakeAttempted",
        "toolListRequested",
        "approvalExecutorImplemented",
        "permissionExecutorImplemented",
        "toolInvocationPathImplemented",
        "toolInvocationAttempted",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "auditLoggerImplemented",
        "auditPersistence",
        "diagnosticsProduced",
        "reportProduced",
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
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "marketplaceClaim",
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


def validate_plugin_manifest_validation_result(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-manifest-validation-result.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "resultId",
            "pluginId",
            "capabilityId",
            "permissionProfile",
            "resultState",
            "pluginRuntimeState",
            "loaderState",
            "sandboxState",
            "defaultMode",
            "hostMode",
        ],
    )
    expected_values = {
        "resultState": "example_only",
        "pluginRuntimeState": "not_implemented",
        "loaderState": "not_implemented",
        "sandboxState": "not_implemented",
        "defaultMode": "disabled",
        "hostMode": "cli_first_gui_second",
    }
    for field, expected in expected_values.items():
        if root[field] != expected:
            raise ShapeError(f"unexpected value at $.{field}: expected {expected}")

    manifest = expect_object(require_field(root, "$", "sourceManifestRef"), "$.sourceManifestRef")
    require_string_fields(
        manifest,
        "$.sourceManifestRef",
        ["schemaVersion", "sourceState"],
    )
    manifest_false_flags = ["pathEchoAllowed", "manifestContentIncluded", "localFileRead"]
    require_bool_fields(manifest, "$.sourceManifestRef", manifest_false_flags)
    for flag in manifest_false_flags:
        if manifest[flag] is not False:
            raise ShapeError(f"unexpected value at $.sourceManifestRef.{flag}: expected false")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(
            ref,
            "$.sourceBoundaryRefs[]",
            ["schemaVersion", "examplePath", "refKind"],
        )

    request = expect_object(
        require_field(root, "$", "validationRequest"),
        "$.validationRequest",
    )
    require_string_fields(
        request,
        "$.validationRequest",
        ["commandKind", "approvedInputReferenceKind"],
    )
    require_string_array(
        require_field(request, "$.validationRequest", "fixedArgsPreview"),
        "$.validationRequest.fixedArgsPreview",
        min_items=1,
    )
    request_false_flags = [
        "pathEchoAllowed",
        "rawShellCommandAllowed",
        "manifestReaderImplemented",
        "pluginCodeLoadAllowed",
        "packageInstallAllowed",
    ]
    require_bool_fields(request, "$.validationRequest", request_false_flags)
    for flag in request_false_flags:
        if request[flag] is not False:
            raise ShapeError(f"unexpected value at $.validationRequest.{flag}: expected false")

    result = expect_object(require_field(root, "$", "validationResult"), "$.validationResult")
    require_string_fields(result, "$.validationResult", ["state", "summary"])
    if result["state"] != "planned_result_shape":
        raise ShapeError("unexpected value at $.validationResult.state: expected planned_result_shape")
    expect_integer(
        require_field(result, "$.validationResult", "requiredFieldCount"),
        "$.validationResult.requiredFieldCount",
    )
    require_string_array(
        require_field(result, "$.validationResult", "missingRequiredFields"),
        "$.validationResult.missingRequiredFields",
    )
    require_string_array(
        require_field(result, "$.validationResult", "acceptedCapabilityIds"),
        "$.validationResult.acceptedCapabilityIds",
        min_items=1,
    )
    require_string_array(
        require_field(result, "$.validationResult", "blockedCapabilityIds"),
        "$.validationResult.blockedCapabilityIds",
        min_items=1,
    )
    result_true_flags = ["summaryOnly"]
    result_false_flags = [
        "manifestReaderAttempted",
        "pluginCodeLoaded",
        "commandExecutionAttempted",
        "packageInstalled",
        "dynamicLibrariesLoaded",
    ]
    require_bool_fields(result, "$.validationResult", result_true_flags + result_false_flags)
    if result["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.validationResult.summaryOnly: expected true")
    for flag in result_false_flags:
        if result[flag] is not False:
            raise ShapeError(f"unexpected value at $.validationResult.{flag}: expected false")
    warnings = require_object_array(require_field(result, "$.validationResult", "warnings"), "$.validationResult.warnings")
    for warning in warnings:
        require_string_fields(warning, "$.validationResult.warnings[]", ["code", "summary"])
        if expect_bool(require_field(warning, "$.validationResult.warnings[]", "pathIncluded"), "$.validationResult.warnings[].pathIncluded") is not False:
            raise ShapeError("unexpected value at $.validationResult.warnings[].pathIncluded: expected false")

    redaction = expect_object(require_field(root, "$", "redactionState"), "$.redactionState")
    require_string_field(redaction, "$.redactionState", "state")
    redaction_false_flags = [
        "privatePathsIncluded",
        "manifestContentIncluded",
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

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_field(mutation, "$.noMutationEvidence", "state")
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    require_string_array(require_field(root, "$", "blockedActions"), "$.blockedActions", min_items=1)
    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "validationResultFixtureOnly",
        "summaryOnly",
    ]
    false_flags = [
        "pluginManifestValidatorImplemented",
        "manifestReaderImplemented",
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
        "localFileRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
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


def validate_plugin_sample_plan(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-sample-plan.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "samplePlanId",
            "planState",
            "sampleState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["planState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.planState: expected descriptor_only")
    if root["sampleState"] != "plan_only":
        raise ShapeError("unexpected value at $.sampleState: expected plan_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "plugin_boundary_plan",
        "plugin_capability_detail",
        "plugin_input_contract",
        "plugin_output_contract",
        "plugin_permission_model",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "plugin_boundary_plan"
        and ref.get("samplePlanMentioned") is True
        and ref.get("manifestReaderAllowed") is False
        and ref.get("packageReaderAllowed") is False
        and ref.get("pluginLoaderAllowed") is False
        and ref.get("pluginRuntimeAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_boundary_plan disabled source reference")
    if not any(
        ref["refId"] == "plugin_capability_detail"
        and ref.get("capabilityDetailAvailable") is True
        and ref.get("capabilityDispatchAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_capability_detail disabled source reference")
    if not any(
        ref["refId"] == "plugin_input_contract"
        and ref.get("inputShapeAvailable") is True
        and ref.get("inputReaderAllowed") is False
        and ref.get("rawTraceReadAllowed") is False
        and ref.get("rawReportReadAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_input_contract summary-only source reference")
    if not any(
        ref["refId"] == "plugin_output_contract"
        and ref.get("outputShapeAvailable") is True
        and ref.get("payloadIncluded") is False
        and ref.get("reportWriteAllowed") is False
        and ref.get("artifactWriteAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_output_contract summary-only source reference")
    if not any(
        ref["refId"] == "plugin_permission_model"
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("sandboxStartAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_permission_model disabled source reference")

    sample = expect_object(require_field(root, "$", "samplePlugin"), "$.samplePlugin")
    require_string_fields(
        sample,
        "$.samplePlugin",
        [
            "pluginId",
            "displayName",
            "sampleKind",
            "sampleState",
            "entryKind",
            "manifestState",
            "capabilityId",
            "capabilityState",
            "permissionProfile",
            "inputContractRef",
            "outputContractRef",
            "executionState",
            "summary",
        ],
    )
    if sample["pluginId"] != "example.diagnostics.summary":
        raise ShapeError("unexpected value at $.samplePlugin.pluginId: expected example.diagnostics.summary")
    if sample["sampleState"] != "plan_only":
        raise ShapeError("unexpected value at $.samplePlugin.sampleState: expected plan_only")
    if sample["entryKind"] != "manifest_only":
        raise ShapeError("unexpected value at $.samplePlugin.entryKind: expected manifest_only")
    if sample["executionState"] != "not_implemented":
        raise ShapeError("unexpected value at $.samplePlugin.executionState: expected not_implemented")
    sample_false_flags = [
        "manifestPathIncluded",
        "manifestContentIncluded",
        "packagePathIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "sampleSourceIncluded",
        "sampleBinaryIncluded",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
    ]
    require_bool_fields(sample, "$.samplePlugin", sample_false_flags)
    for flag in sample_false_flags:
        if sample[flag] is not False:
            raise ShapeError(f"unexpected value at $.samplePlugin.{flag}: expected false")

    flow = expect_object(require_field(root, "$", "sampleFlow"), "$.sampleFlow")
    require_string_fields(
        flow,
        "$.sampleFlow",
        [
            "flowId",
            "flowState",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.sampleFlow.flowState: expected blocked")
    require_string_array(
        require_field(flow, "$.sampleFlow", "fixedArgsPreview"),
        "$.sampleFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.sampleFlow", "steps"), "$.sampleFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.sampleFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "manifest_shape_review",
        "input_contract_review",
        "output_contract_review",
        "sample_load_gate",
        "sample_dispatch_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing sample flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.sampleFlow", "blockedReasonRefs"),
        "$.sampleFlow.blockedReasonRefs",
        min_items=1,
    )

    io_boundary = expect_object(require_field(root, "$", "inputOutputBoundary"), "$.inputOutputBoundary")
    require_string_fields(
        io_boundary,
        "$.inputOutputBoundary",
        ["state", "acceptedInputKind", "inputContractSchema", "outputContractSchema"],
    )
    if io_boundary["state"] != "summary_only":
        raise ShapeError("unexpected value at $.inputOutputBoundary.state: expected summary_only")
    io_false_flags = [
        "diagnosticsEnvelopeContentIncluded",
        "workflowResultContentIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "promptContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "inputReaderAllowed",
        "traceImporterAllowed",
        "reportReaderAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
    ]
    require_bool_fields(io_boundary, "$.inputOutputBoundary", io_false_flags)
    for flag in io_false_flags:
        if io_boundary[flag] is not False:
            raise ShapeError(f"unexpected value at $.inputOutputBoundary.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForPlan"]
    review_false_flags = [
        "approvedForManifestMaterialization",
        "approvedForCodeGeneration",
        "approvedForPackageBuild",
        "approvedForLoad",
        "approvedForDispatch",
        "approvedForInvocation",
        "approvedForReportWrite",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    require_string_array(require_field(root, "$", "blockedActions"), "$.blockedActions", min_items=1)
    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "manifestWriteAllowed",
        "packageBuildAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginLoadAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "samplePlanFixtureOnly",
    ]
    false_flags = [
        "samplePluginImplemented",
        "samplePluginExecuted",
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "manifestReaderImplemented",
        "packageReaderImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "capabilityDispatchImplemented",
        "pluginInvocationImplemented",
        "stablePluginAbiPromised",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
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


def validate_plugin_sample_result(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-sample-result.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "sampleResultId",
            "resultState",
            "sampleState",
            "adapterState",
            "defaultMode",
            "hostMode",
            "automationPath",
        ],
    )
    if root["resultState"] != "blocked_summary":
        raise ShapeError("unexpected value at $.resultState: expected blocked_summary")
    if root["sampleState"] != "not_executed":
        raise ShapeError("unexpected value at $.sampleState: expected not_executed")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")
    if root["automationPath"] != "cli-core-first-gui-independent":
        raise ShapeError("unexpected value at $.automationPath: expected cli-core-first-gui-independent")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "plugin_sample_plan",
        "plugin_capability_detail",
        "plugin_output_contract",
        "plugin_review_packet",
        "plugin_blocked_invocation_result",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "plugin_sample_plan"
        and ref.get("samplePlanAvailable") is True
        and ref.get("sampleExecuted") is False
        and ref.get("pluginLoadAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_sample_plan disabled source reference")
    if not any(
        ref["refId"] == "plugin_capability_detail"
        and ref.get("capabilityDetailAvailable") is True
        and ref.get("capabilityId") == "plugin.diagnostics.summary"
        and ref.get("capabilityDispatchAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_capability_detail disabled source reference")
    if not any(
        ref["refId"] == "plugin_output_contract"
        and ref.get("outputShapeAvailable") is True
        and ref.get("payloadIncluded") is False
        and ref.get("reportWriteAllowed") is False
        and ref.get("artifactWriteAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_output_contract summary-only source reference")
    if not any(
        ref["refId"] == "plugin_review_packet"
        and ref.get("reviewPacketAvailable") is True
        and ref.get("summaryOnly") is True
        and ref.get("packageReaderAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_review_packet summary-only source reference")
    if not any(
        ref["refId"] == "plugin_blocked_invocation_result"
        and ref.get("blockedResultAvailable") is True
        and ref.get("invocationExecuted") is False
        and ref.get("pluginLoadAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_blocked_invocation_result disabled source reference")

    sample = expect_object(require_field(root, "$", "sampleResult"), "$.sampleResult")
    require_string_fields(
        sample,
        "$.sampleResult",
        [
            "samplePluginId",
            "displayName",
            "resultKind",
            "resultState",
            "sampleState",
            "invocationState",
            "outputBoundaryRef",
            "samplePlanRef",
            "summary",
        ],
    )
    if sample["samplePluginId"] != "example.diagnostics.summary":
        raise ShapeError("unexpected value at $.sampleResult.samplePluginId: expected example.diagnostics.summary")
    if sample["resultState"] != "blocked_summary":
        raise ShapeError("unexpected value at $.sampleResult.resultState: expected blocked_summary")
    if sample["sampleState"] != "not_executed":
        raise ShapeError("unexpected value at $.sampleResult.sampleState: expected not_executed")
    if sample["invocationState"] != "not_invoked":
        raise ShapeError("unexpected value at $.sampleResult.invocationState: expected not_invoked")
    sample_true_flags = ["summaryOnly", "resultDescriptorOnly"]
    sample_false_flags = [
        "payloadIncluded",
        "diagnosticsPayloadIncluded",
        "workflowResultContentIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "samplePluginImplemented",
        "samplePluginExecuted",
        "sampleResultProduced",
        "pluginInvocationAttempted",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "permissionExecutorAllowed",
        "inputReaderAllowed",
        "traceImporterAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
    ]
    require_bool_fields(sample, "$.sampleResult", sample_true_flags + sample_false_flags)
    for flag in sample_true_flags:
        if sample[flag] is not True:
            raise ShapeError(f"unexpected value at $.sampleResult.{flag}: expected true")
    for flag in sample_false_flags:
        if sample[flag] is not False:
            raise ShapeError(f"unexpected value at $.sampleResult.{flag}: expected false")

    flow = expect_object(require_field(root, "$", "resultFlow"), "$.resultFlow")
    require_string_fields(
        flow,
        "$.resultFlow",
        [
            "flowId",
            "flowState",
            "resultKind",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.resultFlow.flowState: expected blocked")
    if flow["commandKind"] != "planned-cli-fixed-args":
        raise ShapeError("unexpected value at $.resultFlow.commandKind: expected planned-cli-fixed-args")
    require_string_array(
        require_field(flow, "$.resultFlow", "fixedArgsPreview"),
        "$.resultFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.resultFlow", "steps"), "$.resultFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.resultFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "sample_plan_review",
        "selected_capability_review",
        "blocked_result_reference",
        "result_envelope_gate",
        "sample_invocation_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing plugin sample result flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.resultFlow", "blockedReasonRefs"),
        "$.resultFlow.blockedReasonRefs",
        min_items=1,
    )

    envelope = expect_object(require_field(root, "$", "resultEnvelope"), "$.resultEnvelope")
    require_string_fields(
        envelope,
        "$.resultEnvelope",
        ["state", "acceptedInputKind", "resultContractSchema", "outputContractSchema", "payloadPolicy"],
    )
    if envelope["state"] != "summary_only":
        raise ShapeError("unexpected value at $.resultEnvelope.state: expected summary_only")
    envelope_false_flags = [
        "payloadIncluded",
        "diagnosticsEnvelopeContentIncluded",
        "workflowResultContentIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "promptContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "inputReaderAllowed",
        "resultPayloadReaderAllowed",
        "traceImporterAllowed",
        "reportReaderAllowed",
        "reportWriteAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
    ]
    require_bool_fields(envelope, "$.resultEnvelope", envelope_false_flags)
    for flag in envelope_false_flags:
        if envelope[flag] is not False:
            raise ShapeError(f"unexpected value at $.resultEnvelope.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForDescriptorResult"]
    review_false_flags = [
        "approvedForManifestMaterialization",
        "approvedForCodeGeneration",
        "approvedForPackageBuild",
        "approvedForLoad",
        "approvedForSandbox",
        "approvedForDispatch",
        "approvedForInvocation",
        "approvedForPermissionExecution",
        "approvedForInputRead",
        "approvedForReportRead",
        "approvedForReportWrite",
        "approvedForArtifactRead",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "rawCommandIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "diagnosticsPayloadIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "payloadIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "manifestWriteAllowed",
        "packageBuildAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginLoadAllowed",
        "pluginInvocationAllowed",
        "capabilityDispatchAllowed",
        "permissionExecutionAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "manifest-reader",
        "package-reader",
        "plugin-loader-start",
        "plugin-runtime-start",
        "sandbox-start",
        "plugin-capability-dispatch",
        "plugin-invocation",
        "permission-executor",
        "input-reader",
        "trace-importer",
        "result-payload-read",
        "report-read",
        "report-write",
        "artifact-read",
        "artifact-write",
        "command-execution",
        "dynamic-code-load",
        "package-distribution",
        "marketplace-flow",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "model-load",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "sampleResultFixtureOnly",
    ]
    false_flags = [
        "samplePluginImplemented",
        "samplePluginExecuted",
        "sampleResultProduced",
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "manifestReaderImplemented",
        "packageReaderImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "resultPayloadReaderImplemented",
        "capabilityDispatchImplemented",
        "pluginInvocationImplemented",
        "stablePluginAbiPromised",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_plugin_sample_catalog(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-sample-catalog.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "sampleCatalogId",
            "catalogState",
            "sampleState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["catalogState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.catalogState: expected descriptor_only")
    if root["sampleState"] != "listed_not_executed":
        raise ShapeError("unexpected value at $.sampleState: expected listed_not_executed")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "plugin_sample_plan",
        "plugin_sample_result",
        "plugin_capability_detail",
        "plugin_permission_model",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "plugin_sample_plan"
        and ref.get("samplePlanAvailable") is True
        and ref.get("sampleExecuted") is False
        and ref.get("manifestReaderAllowed") is False
        and ref.get("pluginLoadAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_sample_plan disabled source reference")
    if not any(
        ref["refId"] == "plugin_sample_result"
        and ref.get("sampleResultAvailable") is True
        and ref.get("sampleResultProduced") is False
        and ref.get("resultPayloadReaderAllowed") is False
        and ref.get("reportReaderAllowed") is False
        and ref.get("artifactReaderAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_sample_result disabled source reference")
    if not any(
        ref["refId"] == "plugin_capability_detail"
        and ref.get("capabilityDetailAvailable") is True
        and ref.get("capabilityId") == "plugin.diagnostics.summary"
        and ref.get("capabilityDispatchAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_capability_detail disabled source reference")
    if not any(
        ref["refId"] == "plugin_permission_model"
        and ref.get("permissionModelAvailable") is True
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("sandboxStartAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_permission_model disabled source reference")

    summary = expect_object(require_field(root, "$", "catalogSummary"), "$.catalogSummary")
    require_string_fields(
        summary,
        "$.catalogSummary",
        ["catalogKind", "sourceReferenceKind", "summary"],
    )
    entry_count = expect_integer(require_field(summary, "$.catalogSummary", "entryCount"), "$.catalogSummary.entryCount")
    if entry_count < 1:
        raise ShapeError("expected at least 1 entry at $.catalogSummary.entryCount")
    summary_true_flags = ["summaryOnly", "descriptorOnly", "generatedFromApprovedSummaries"]
    summary_false_flags = [
        "sampleDiscoveryImplemented",
        "manifestReaderAllowed",
        "packageReaderAllowed",
        "sourceReaderAllowed",
        "sampleExecutionAllowed",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
    ]
    require_bool_fields(summary, "$.catalogSummary", summary_true_flags + summary_false_flags)
    for flag in summary_true_flags:
        if summary[flag] is not True:
            raise ShapeError(f"unexpected value at $.catalogSummary.{flag}: expected true")
    for flag in summary_false_flags:
        if summary[flag] is not False:
            raise ShapeError(f"unexpected value at $.catalogSummary.{flag}: expected false")

    entries = require_object_array(require_field(root, "$", "sampleEntries"), "$.sampleEntries", min_items=1)
    for entry in entries:
        path = "$.sampleEntries[]"
        require_string_fields(
            entry,
            path,
            [
                "samplePluginId",
                "displayName",
                "sampleKind",
                "catalogEntryState",
                "planState",
                "resultState",
                "sampleState",
                "invocationState",
                "samplePlanRef",
                "sampleResultRef",
                "capabilityId",
                "permissionProfile",
                "summary",
            ],
        )
        if entry["samplePluginId"] != "example.diagnostics.summary":
            raise ShapeError("unexpected value at $.sampleEntries[].samplePluginId: expected example.diagnostics.summary")
        if entry["catalogEntryState"] != "listed_descriptor_only":
            raise ShapeError("unexpected value at $.sampleEntries[].catalogEntryState: expected listed_descriptor_only")
        if entry["planState"] != "descriptor_only":
            raise ShapeError("unexpected value at $.sampleEntries[].planState: expected descriptor_only")
        if entry["resultState"] != "blocked_summary":
            raise ShapeError("unexpected value at $.sampleEntries[].resultState: expected blocked_summary")
        if entry["sampleState"] != "not_executed":
            raise ShapeError("unexpected value at $.sampleEntries[].sampleState: expected not_executed")
        if entry["invocationState"] != "not_invoked":
            raise ShapeError("unexpected value at $.sampleEntries[].invocationState: expected not_invoked")
        entry_true_flags = [
            "summaryOnly",
            "descriptorOnly",
            "samplePlanAvailable",
            "sampleResultAvailable",
        ]
        entry_false_flags = [
            "samplePluginImplemented",
            "samplePluginExecuted",
            "sampleResultProduced",
            "pluginInvocationAttempted",
            "manifestPathIncluded",
            "manifestContentIncluded",
            "packagePathIncluded",
            "packageContentIncluded",
            "sourceCodeIncluded",
            "sampleSourceIncluded",
            "diagnosticsPayloadIncluded",
            "traceContentIncluded",
            "reportContentIncluded",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogsIncluded",
            "artifactPathsIncluded",
            "privatePathsIncluded",
            "pluginLoaderAllowed",
            "pluginRuntimeAllowed",
            "sandboxStartAllowed",
            "hostApiBindAllowed",
            "capabilityDispatchAllowed",
            "pluginInvocationAllowed",
            "permissionExecutorAllowed",
            "inputReaderAllowed",
            "resultPayloadReaderAllowed",
            "reportReaderAllowed",
            "reportWriteAllowed",
            "artifactReaderAllowed",
            "artifactWriteAllowed",
            "commandExecutionAllowed",
            "shellExecutionAllowed",
            "runtimeExecutionAllowed",
        ]
        require_bool_fields(entry, path, entry_true_flags + entry_false_flags)
        for flag in entry_true_flags:
            if entry[flag] is not True:
                raise ShapeError(f"unexpected value at {child(path, flag)}: expected true")
        for flag in entry_false_flags:
            if entry[flag] is not False:
                raise ShapeError(f"unexpected value at {child(path, flag)}: expected false")

    flow = expect_object(require_field(root, "$", "catalogFlow"), "$.catalogFlow")
    require_string_fields(
        flow,
        "$.catalogFlow",
        [
            "flowId",
            "flowState",
            "catalogKind",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.catalogFlow.flowState: expected blocked")
    if flow["commandKind"] != "planned-cli-fixed-args":
        raise ShapeError("unexpected value at $.catalogFlow.commandKind: expected planned-cli-fixed-args")
    require_string_array(
        require_field(flow, "$.catalogFlow", "fixedArgsPreview"),
        "$.catalogFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.catalogFlow", "steps"), "$.catalogFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.catalogFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "sample_plan_reference",
        "sample_result_reference",
        "catalog_listing_gate",
        "sample_execution_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing plugin sample catalog flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.catalogFlow", "blockedReasonRefs"),
        "$.catalogFlow.blockedReasonRefs",
        min_items=1,
    )

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "diagnosticsPayloadIncluded",
        "resultPayloadIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForCatalogDescriptor"]
    review_false_flags = [
        "approvedForSampleDiscovery",
        "approvedForManifestRead",
        "approvedForPackageRead",
        "approvedForSourceRead",
        "approvedForCodeGeneration",
        "approvedForPackageBuild",
        "approvedForLoad",
        "approvedForSandbox",
        "approvedForDispatch",
        "approvedForInvocation",
        "approvedForPermissionExecution",
        "approvedForInputRead",
        "approvedForPayloadRead",
        "approvedForReportRead",
        "approvedForReportWrite",
        "approvedForArtifactRead",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "manifestReadAllowed",
        "manifestWriteAllowed",
        "packageReadAllowed",
        "packageBuildAllowed",
        "sourceReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginLoadAllowed",
        "pluginInvocationAllowed",
        "capabilityDispatchAllowed",
        "permissionExecutionAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "sample-discovery",
        "manifest-reader",
        "package-reader",
        "source-reader",
        "plugin-loader-start",
        "plugin-runtime-start",
        "sandbox-start",
        "plugin-capability-dispatch",
        "plugin-invocation",
        "permission-executor",
        "input-reader",
        "result-payload-read",
        "report-read",
        "report-write",
        "artifact-read",
        "artifact-write",
        "command-execution",
        "dynamic-code-load",
        "package-distribution",
        "marketplace-flow",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "model-load",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "sampleCatalogFixtureOnly",
    ]
    false_flags = [
        "sampleDiscoveryImplemented",
        "samplePluginImplemented",
        "samplePluginExecuted",
        "sampleResultProduced",
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "manifestReaderImplemented",
        "packageReaderImplemented",
        "sourceReaderImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "resultPayloadReaderImplemented",
        "capabilityDispatchImplemented",
        "pluginInvocationImplemented",
        "stablePluginAbiPromised",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestPathIncluded",
        "manifestContentIncluded",
        "packagePathIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_plugin_sample_detail(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-sample-detail.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "sampleDetailId",
            "detailState",
            "sampleState",
            "resultState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["detailState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.detailState: expected descriptor_only")
    if root["sampleState"] != "listed_not_executed":
        raise ShapeError("unexpected value at $.sampleState: expected listed_not_executed")
    if root["resultState"] != "blocked_summary":
        raise ShapeError("unexpected value at $.resultState: expected blocked_summary")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    required_refs = {
        "plugin_sample_catalog",
        "plugin_sample_result",
        "plugin_sample_plan",
        "plugin_capability_detail",
        "plugin_permission_model",
    }
    actual_refs = {ref["refId"] for ref in refs}
    missing_refs = sorted(required_refs - actual_refs)
    if missing_refs:
        raise ShapeError(f"missing source boundary refs: {', '.join(missing_refs)}")
    if not any(
        ref["refId"] == "plugin_sample_catalog"
        and ref.get("sampleCatalogAvailable") is True
        and ref.get("sampleDiscoveryAllowed") is False
        and ref.get("manifestReaderAllowed") is False
        and ref.get("packageReaderAllowed") is False
        and ref.get("sourceReaderAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_sample_catalog disabled source reference")
    if not any(
        ref["refId"] == "plugin_sample_result"
        and ref.get("sampleResultAvailable") is True
        and ref.get("sampleResultProduced") is False
        and ref.get("resultPayloadReaderAllowed") is False
        and ref.get("reportReaderAllowed") is False
        and ref.get("artifactReaderAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_sample_result disabled source reference")
    if not any(
        ref["refId"] == "plugin_sample_plan"
        and ref.get("samplePlanAvailable") is True
        and ref.get("sampleExecuted") is False
        and ref.get("manifestReaderAllowed") is False
        and ref.get("pluginLoadAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_sample_plan disabled source reference")
    if not any(
        ref["refId"] == "plugin_capability_detail"
        and ref.get("capabilityDetailAvailable") is True
        and ref.get("capabilityId") == "plugin.diagnostics.summary"
        and ref.get("capabilityDispatchAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_capability_detail disabled source reference")
    if not any(
        ref["refId"] == "plugin_permission_model"
        and ref.get("permissionModelAvailable") is True
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("sandboxStartAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_permission_model disabled source reference")

    sample = expect_object(require_field(root, "$", "selectedSample"), "$.selectedSample")
    require_string_fields(
        sample,
        "$.selectedSample",
        [
            "samplePluginId",
            "displayName",
            "sampleKind",
            "detailState",
            "catalogEntryState",
            "planState",
            "resultState",
            "sampleState",
            "invocationState",
            "sampleCatalogRef",
            "samplePlanRef",
            "sampleResultRef",
            "capabilityId",
            "permissionProfile",
            "summary",
        ],
    )
    expected_sample_values = {
        "samplePluginId": "example.diagnostics.summary",
        "detailState": "selected_descriptor_only",
        "catalogEntryState": "listed_descriptor_only",
        "planState": "descriptor_only",
        "resultState": "blocked_summary",
        "sampleState": "not_executed",
        "invocationState": "not_invoked",
        "capabilityId": "plugin.diagnostics.summary",
    }
    for field, expected in expected_sample_values.items():
        if sample[field] != expected:
            raise ShapeError(f"unexpected value at $.selectedSample.{field}: expected {expected}")
    sample_true_flags = [
        "summaryOnly",
        "descriptorOnly",
        "sampleCatalogAvailable",
        "samplePlanAvailable",
        "sampleResultAvailable",
    ]
    sample_false_flags = [
        "samplePluginImplemented",
        "samplePluginExecuted",
        "sampleResultProduced",
        "pluginInvocationAttempted",
        "manifestPathIncluded",
        "manifestContentIncluded",
        "packagePathIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "sampleSourceIncluded",
        "diagnosticsPayloadIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "resultPayloadIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "permissionExecutorAllowed",
        "inputReaderAllowed",
        "resultPayloadReaderAllowed",
        "reportReaderAllowed",
        "reportWriteAllowed",
        "artifactReaderAllowed",
        "artifactWriteAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
    ]
    require_bool_fields(sample, "$.selectedSample", sample_true_flags + sample_false_flags)
    for flag in sample_true_flags:
        if sample[flag] is not True:
            raise ShapeError(f"unexpected value at $.selectedSample.{flag}: expected true")
    for flag in sample_false_flags:
        if sample[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedSample.{flag}: expected false")

    sections = require_object_array(require_field(root, "$", "detailSections"), "$.detailSections", min_items=1)
    section_ids = set()
    for section in sections:
        path = "$.detailSections[]"
        require_string_fields(section, path, ["sectionId", "sectionState", "summary"])
        require_string_array(require_field(section, path, "allowedFieldRefs"), child(path, "allowedFieldRefs"), min_items=1)
        require_string_array(require_field(section, path, "blockedFieldRefs"), child(path, "blockedFieldRefs"), min_items=1)
        require_bool_fields(section, path, ["summaryOnly", "contentIncluded", "pathEchoAllowed"])
        section_ids.add(section["sectionId"])
        if section["summaryOnly"] is not True:
            raise ShapeError(f"unexpected value at {child(path, 'summaryOnly')}: expected true")
        if section["contentIncluded"] is not False:
            raise ShapeError(f"unexpected value at {child(path, 'contentIncluded')}: expected false")
        if section["pathEchoAllowed"] is not False:
            raise ShapeError(f"unexpected value at {child(path, 'pathEchoAllowed')}: expected false")
    for section_id in ["sample_identity", "boundary_references", "execution_status"]:
        if section_id not in section_ids:
            raise ShapeError(f"missing plugin sample detail section: {section_id}")

    flow = expect_object(require_field(root, "$", "detailFlow"), "$.detailFlow")
    require_string_fields(
        flow,
        "$.detailFlow",
        [
            "flowId",
            "flowState",
            "detailKind",
            "commandKind",
            "sourceReferenceKind",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if flow["flowState"] != "blocked":
        raise ShapeError("unexpected value at $.detailFlow.flowState: expected blocked")
    if flow["commandKind"] != "planned-cli-fixed-args":
        raise ShapeError("unexpected value at $.detailFlow.commandKind: expected planned-cli-fixed-args")
    require_string_array(
        require_field(flow, "$.detailFlow", "fixedArgsPreview"),
        "$.detailFlow.fixedArgsPreview",
        min_items=1,
    )
    steps = require_object_array(require_field(flow, "$.detailFlow", "steps"), "$.detailFlow.steps", min_items=1)
    step_ids = set()
    for step in steps:
        path = "$.detailFlow.steps[]"
        require_string_fields(step, path, ["stepId", "state", "summary", "requiredBefore", "sideEffectPolicy"])
        step_ids.add(step["stepId"])
    for step_id in [
        "sample_catalog_reference",
        "sample_result_reference",
        "detail_display_gate",
        "sample_execution_gate",
    ]:
        if step_id not in step_ids:
            raise ShapeError(f"missing plugin sample detail flow step: {step_id}")
    require_string_array(
        require_field(flow, "$.detailFlow", "blockedReasonRefs"),
        "$.detailFlow.blockedReasonRefs",
        min_items=1,
    )

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(require_field(display, "$.displayPolicy", "allowedFields"), "$.displayPolicy.allowedFields", min_items=1)
    require_string_array(require_field(display, "$.displayPolicy", "blockedFields"), "$.displayPolicy.blockedFields", min_items=1)
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "diagnosticsPayloadIncluded",
        "resultPayloadIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForSampleDetailDescriptor"]
    review_false_flags = [
        "approvedForSampleDiscovery",
        "approvedForManifestRead",
        "approvedForPackageRead",
        "approvedForSourceRead",
        "approvedForCodeGeneration",
        "approvedForPackageBuild",
        "approvedForLoad",
        "approvedForSandbox",
        "approvedForDispatch",
        "approvedForInvocation",
        "approvedForPermissionExecution",
        "approvedForInputRead",
        "approvedForPayloadRead",
        "approvedForReportRead",
        "approvedForReportWrite",
        "approvedForArtifactRead",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "manifestReadAllowed",
        "manifestWriteAllowed",
        "packageReadAllowed",
        "packageBuildAllowed",
        "sourceReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportReadAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginLoadAllowed",
        "pluginInvocationAllowed",
        "capabilityDispatchAllowed",
        "permissionExecutionAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "sample-discovery",
        "manifest-reader",
        "package-reader",
        "source-reader",
        "plugin-loader-start",
        "plugin-runtime-start",
        "sandbox-start",
        "host-api-bind",
        "plugin-capability-dispatch",
        "plugin-invocation",
        "permission-executor",
        "input-reader",
        "result-payload-read",
        "report-read",
        "report-write",
        "artifact-read",
        "artifact-write",
        "command-execution",
        "dynamic-code-load",
        "package-build",
        "package-distribution",
        "marketplace-flow",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "model-load",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked_actions:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "sampleDetailFixtureOnly",
    ]
    false_flags = [
        "sampleDiscoveryImplemented",
        "samplePluginImplemented",
        "samplePluginExecuted",
        "sampleResultProduced",
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "manifestReaderImplemented",
        "packageReaderImplemented",
        "sourceReaderImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "reportReaderImplemented",
        "reportWriterImplemented",
        "resultPayloadReaderImplemented",
        "capabilityDispatchImplemented",
        "pluginInvocationImplemented",
        "stablePluginAbiPromised",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestPathIncluded",
        "manifestContentIncluded",
        "packagePathIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_plugin_capability_list(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-capability-list.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "capabilityListId",
            "listState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["listState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.listState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    if not any(
        ref["refId"] == "plugin_boundary_plan"
        and ref.get("manifestReaderAllowed") is False
        and ref.get("packageReaderAllowed") is False
        and ref.get("pluginLoaderAllowed") is False
        and ref.get("pluginRuntimeAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_boundary_plan disabled source reference")
    if not any(
        ref["refId"] == "plugin_manifest_validation_result"
        and ref.get("summaryOnly") is True
        and ref.get("manifestReaderAllowed") is False
        and ref.get("validatorCommandAllowed") is False
        and ref.get("pluginCodeLoadAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_manifest_validation_result summary-only source reference")
    if not any(
        ref["refId"] == "plugin_permission_model"
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("sandboxStartAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_permission_model disabled source reference")

    request = expect_object(
        require_field(root, "$", "capabilityListRequest"),
        "$.capabilityListRequest",
    )
    require_string_fields(
        request,
        "$.capabilityListRequest",
        [
            "requestKind",
            "commandKind",
            "sourceReferenceKind",
            "outputBoundary",
            "summary",
        ],
    )
    require_string_array(
        require_field(request, "$.capabilityListRequest", "fixedArgsPreview"),
        "$.capabilityListRequest.fixedArgsPreview",
        min_items=1,
    )
    request_true_flags = ["summaryOnly", "inputRefOnly"]
    request_false_flags = [
        "approvalRequired",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "artifactReadAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplaceFlowAllowed",
        "dynamicCodeLoadAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
    ]
    require_bool_fields(request, "$.capabilityListRequest", request_true_flags + request_false_flags)
    for flag in request_true_flags:
        if request[flag] is not True:
            raise ShapeError(f"unexpected value at $.capabilityListRequest.{flag}: expected true")
    for flag in request_false_flags:
        if request[flag] is not False:
            raise ShapeError(f"unexpected value at $.capabilityListRequest.{flag}: expected false")

    capabilities = require_object_array(
        require_field(root, "$", "capabilities"),
        "$.capabilities",
        min_items=1,
    )
    capability_ids = set()
    for capability in capabilities:
        path = "$.capabilities[]"
        require_string_fields(
            capability,
            path,
            [
                "capabilityId",
                "displayName",
                "capabilityState",
                "listState",
                "permissionProfile",
                "inputPolicy",
                "outputPolicy",
                "reviewSource",
            ],
        )
        capability_ids.add(capability["capabilityId"])
        capability_true_flags = ["approvedForListing"]
        capability_false_flags = [
            "approvedForLoad",
            "approvedForDispatch",
            "pluginLoaderAllowed",
            "pluginRuntimeAllowed",
            "sandboxStartAllowed",
            "capabilityDispatchAllowed",
            "pluginInvocationAllowed",
            "inputReaderAllowed",
            "traceImporterAllowed",
            "reportWriteAllowed",
            "artifactWriteAllowed",
            "stableAbiRequired",
        ]
        require_bool_fields(capability, path, capability_true_flags + capability_false_flags)
        for flag in capability_true_flags:
            if capability[flag] is not True:
                raise ShapeError(f"unexpected value at {path}.{flag}: expected true")
        for flag in capability_false_flags:
            if capability[flag] is not False:
                raise ShapeError(f"unexpected value at {path}.{flag}: expected false")
    for capability_id in [
        "plugin.diagnostics.summary",
        "plugin.report.panel",
        "plugin.trace.importer",
    ]:
        if capability_id not in capability_ids:
            raise ShapeError(f"missing capability id in $.capabilities: {capability_id}")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(
        require_field(display, "$.displayPolicy", "allowedFields"),
        "$.displayPolicy.allowedFields",
        min_items=1,
    )
    require_string_array(
        require_field(display, "$.displayPolicy", "blockedFields"),
        "$.displayPolicy.blockedFields",
        min_items=1,
    )
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    for flag in display_true_flags:
        if display[flag] is not True:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginLoadAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    require_string_array(require_field(root, "$", "blockedActions"), "$.blockedActions", min_items=1)
    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "summaryOnly",
        "capabilityListFixtureOnly",
    ]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "manifestReaderImplemented",
        "packageReaderImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "capabilityDispatchImplemented",
        "pluginInvocationImplemented",
        "stablePluginAbiPromised",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
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


def validate_plugin_capability_detail(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-capability-detail.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "capabilityDetailId",
            "detailState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["detailState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.detailState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    if not any(
        ref["refId"] == "plugin_capability_list"
        and ref.get("capabilityListAvailable") is True
        and ref.get("capabilityDetailAvailable") is True
        and ref.get("pluginLoaderAllowed") is False
        and ref.get("capabilityDispatchAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_capability_list disabled source reference")
    if not any(
        ref["refId"] == "plugin_manifest_validation_result"
        and ref.get("summaryOnly") is True
        and ref.get("manifestReaderAllowed") is False
        and ref.get("validatorCommandAllowed") is False
        and ref.get("pluginCodeLoadAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_manifest_validation_result summary-only source reference")
    if not any(
        ref["refId"] == "plugin_permission_model"
        and ref.get("permissionExecutorAllowed") is False
        and ref.get("sandboxStartAllowed") is False
        and ref.get("pluginInvocationAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing plugin_permission_model disabled source reference")

    request = expect_object(
        require_field(root, "$", "capabilityDetailRequest"),
        "$.capabilityDetailRequest",
    )
    require_string_fields(
        request,
        "$.capabilityDetailRequest",
        [
            "requestKind",
            "commandKind",
            "selectedCapabilityId",
            "sourceReferenceKind",
            "outputBoundary",
            "summary",
        ],
    )
    if request["requestKind"] != "planned_plugin_capability_detail":
        raise ShapeError(
            "unexpected value at $.capabilityDetailRequest.requestKind: expected planned_plugin_capability_detail"
        )
    if request["selectedCapabilityId"] != "plugin.diagnostics.summary":
        raise ShapeError(
            "unexpected value at $.capabilityDetailRequest.selectedCapabilityId: "
            "expected plugin.diagnostics.summary"
        )
    require_string_array(
        require_field(request, "$.capabilityDetailRequest", "fixedArgsPreview"),
        "$.capabilityDetailRequest.fixedArgsPreview",
        min_items=1,
    )
    request_true_flags = ["summaryOnly", "inputRefOnly"]
    request_false_flags = [
        "approvalRequired",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "permissionExecutorAllowed",
        "auditLoggerAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplaceFlowAllowed",
        "dynamicCodeLoadAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
    ]
    require_bool_fields(request, "$.capabilityDetailRequest", request_true_flags + request_false_flags)
    for flag in request_true_flags:
        if request[flag] is not True:
            raise ShapeError(f"unexpected value at $.capabilityDetailRequest.{flag}: expected true")
    for flag in request_false_flags:
        if request[flag] is not False:
            raise ShapeError(f"unexpected value at $.capabilityDetailRequest.{flag}: expected false")

    selected = expect_object(require_field(root, "$", "selectedCapability"), "$.selectedCapability")
    require_string_fields(
        selected,
        "$.selectedCapability",
        [
            "capabilityId",
            "displayName",
            "category",
            "capabilityState",
            "detailState",
            "listState",
            "permissionProfile",
            "reviewSource",
            "commandPreviewKind",
            "summary",
            "inputPolicy",
            "outputPolicy",
        ],
    )
    if selected["capabilityId"] != request["selectedCapabilityId"]:
        raise ShapeError("selected capability id must match $.capabilityDetailRequest.selectedCapabilityId")
    if selected["detailState"] != "visible_descriptor":
        raise ShapeError("unexpected value at $.selectedCapability.detailState: expected visible_descriptor")

    input_descriptor = expect_object(
        require_field(selected, "$.selectedCapability", "inputDescriptor"),
        "$.selectedCapability.inputDescriptor",
    )
    require_string_fields(
        input_descriptor,
        "$.selectedCapability.inputDescriptor",
        ["descriptorState", "acceptedInputKind", "acceptedInputSummary"],
    )
    input_false_flags = [
        "userPathAccepted",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "rawLogReadAllowed",
        "artifactReadAllowed",
        "providerConfigReadAllowed",
        "environmentReadAllowed",
        "secretsReadAllowed",
        "tokensReadAllowed",
    ]
    require_bool_fields(input_descriptor, "$.selectedCapability.inputDescriptor", input_false_flags)
    for flag in input_false_flags:
        if input_descriptor[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedCapability.inputDescriptor.{flag}: expected false")

    output_descriptor = expect_object(
        require_field(selected, "$.selectedCapability", "outputDescriptor"),
        "$.selectedCapability.outputDescriptor",
    )
    require_string_fields(output_descriptor, "$.selectedCapability.outputDescriptor", ["descriptorState", "boundaryRef"])
    output_false_flags = [
        "payloadIncluded",
        "responseBodyIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
    ]
    require_bool_fields(output_descriptor, "$.selectedCapability.outputDescriptor", output_false_flags)
    for flag in output_false_flags:
        if output_descriptor[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedCapability.outputDescriptor.{flag}: expected false")

    dispatch = expect_object(
        require_field(selected, "$.selectedCapability", "dispatchPolicy"),
        "$.selectedCapability.dispatchPolicy",
    )
    dispatch_true_flags = [
        "requiresSeparateLoadBoundary",
        "requiresSeparateDispatchBoundary",
        "approvalRequiredBeforeDispatch",
        "approvedForListing",
        "approvedForDetail",
    ]
    dispatch_false_flags = [
        "approvedForLoad",
        "approvedForDispatch",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "permissionExecutorAllowed",
        "inputReaderAllowed",
        "traceImporterAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "packageDistributionAllowed",
    ]
    require_bool_fields(dispatch, "$.selectedCapability.dispatchPolicy", dispatch_true_flags + dispatch_false_flags)
    for flag in dispatch_true_flags:
        if dispatch[flag] is not True:
            raise ShapeError(f"unexpected value at $.selectedCapability.dispatchPolicy.{flag}: expected true")
    for flag in dispatch_false_flags:
        if dispatch[flag] is not False:
            raise ShapeError(f"unexpected value at $.selectedCapability.dispatchPolicy.{flag}: expected false")

    related = require_object_array(
        require_field(root, "$", "relatedCapabilityRefs"),
        "$.relatedCapabilityRefs",
        min_items=1,
    )
    for capability in related:
        path = "$.relatedCapabilityRefs[]"
        require_string_fields(capability, path, ["capabilityId", "relationship"])
        require_bool_fields(
            capability,
            path,
            ["detailIncluded", "approvedForDetail", "capabilityDispatchAllowed", "pluginInvocationAllowed"],
        )
        for flag in ["detailIncluded", "approvedForDetail", "capabilityDispatchAllowed", "pluginInvocationAllowed"]:
            if capability[flag] is not False:
                raise ShapeError(f"unexpected value at $.relatedCapabilityRefs[].{flag}: expected false")

    display = expect_object(require_field(root, "$", "displayPolicy"), "$.displayPolicy")
    require_string_fields(display, "$.displayPolicy", ["surface", "guiPolicy"])
    require_string_array(
        require_field(display, "$.displayPolicy", "allowedFields"),
        "$.displayPolicy.allowedFields",
        min_items=1,
    )
    require_string_array(
        require_field(display, "$.displayPolicy", "blockedFields"),
        "$.displayPolicy.blockedFields",
        min_items=1,
    )
    display_true_flags = ["summaryOnly"]
    display_false_flags = [
        "pathEchoAllowed",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "reportContentIncluded",
    ]
    require_bool_fields(display, "$.displayPolicy", display_true_flags + display_false_flags)
    if display["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.displayPolicy.summaryOnly: expected true")
    for flag in display_false_flags:
        if display[flag] is not False:
            raise ShapeError(f"unexpected value at $.displayPolicy.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "auditLogWriteAllowed",
        "pluginLoadAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "manifest-reader",
        "package-reader",
        "plugin-loader-start",
        "plugin-runtime-start",
        "plugin-sandbox-start",
        "plugin-host-api-bind",
        "plugin-capability-dispatch",
        "plugin-invocation",
        "permission-executor",
        "input-reader",
        "trace-importer",
        "validator-command",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "raw-log-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "audit-log-write",
        "repository-write-back",
        "package-install",
        "package-distribution",
        "marketplace-flow",
        "dynamic-code-load",
        "untrusted-execution",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "summaryOnly", "capabilityDetailFixtureOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "hostApiBindingImplemented",
        "permissionExecutorImplemented",
        "manifestReaderImplemented",
        "packageReaderImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "capabilityDispatchImplemented",
        "pluginInvocationImplemented",
        "reportWriterImplemented",
        "auditLoggerImplemented",
        "stablePluginAbiPromised",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "rawLogRead",
        "readsArtifacts",
        "writesArtifacts",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
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


def validate_plugin_load_request(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-load-request.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "loadRequestId",
            "pluginId",
            "capabilityId",
            "permissionProfile",
            "requestState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["requestState"] != "blocked_by_policy":
        raise ShapeError("unexpected value at $.requestState: expected blocked_by_policy")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "manifestReaderAllowed",
            "pluginLoaderAllowed",
            "dynamicCodeLoadAllowed",
            "permissionExecutorAllowed",
            "sandboxStartAllowed",
            "pluginInvocationAllowed",
            "validatorCommandAllowed",
            "artifactWriteAllowed",
            "loggerAllowed",
            "pathEchoAllowed",
            "packageInstallAllowed",
            "repositoryMutationAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")

    request = expect_object(require_field(root, "$", "loadRequest"), "$.loadRequest")
    require_string_fields(
        request,
        "$.loadRequest",
        [
            "requestKind",
            "approvedManifestReferenceKind",
            "approvedPermissionReferenceKind",
            "summary",
        ],
    )
    if request["requestKind"] != "planned_plugin_load_gate":
        raise ShapeError("unexpected value at $.loadRequest.requestKind: expected planned_plugin_load_gate")
    request_true_fields = ["summaryOnly", "approvalRequired"]
    request_false_fields = [
        "manifestContentIncluded",
        "manifestPathIncluded",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "packageInstallAllowed",
        "dynamicCodeLoadAllowed",
        "untrustedExecutionAllowed",
        "sandboxStartAllowed",
        "pluginRuntimeStartAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
    ]
    require_bool_fields(request, "$.loadRequest", request_true_fields + request_false_fields)
    for field in request_true_fields:
        if request[field] is not True:
            raise ShapeError(f"unexpected value at $.loadRequest.{field}: expected true")
    for field in request_false_fields:
        if request[field] is not False:
            raise ShapeError(f"unexpected value at $.loadRequest.{field}: expected false")

    decision = expect_object(require_field(root, "$", "loadDecision"), "$.loadDecision")
    require_string_fields(decision, "$.loadDecision", ["state", "reason"])
    if decision["state"] != "not_loaded":
        raise ShapeError("unexpected value at $.loadDecision.state: expected not_loaded")
    decision_false_fields = [
        "approved",
        "loaderStarted",
        "runtimeStarted",
        "sandboxStarted",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "packageInstalled",
        "permissionExecutorCalled",
        "manifestReaderCalled",
        "validatorCommandCalled",
        "commandExecutionAttempted",
        "pluginInvocationAttempted",
    ]
    require_bool_fields(decision, "$.loadDecision", decision_false_fields)
    for field in decision_false_fields:
        if decision[field] is not False:
            raise ShapeError(f"unexpected value at $.loadDecision.{field}: expected false")

    context = expect_object(require_field(root, "$", "plannedHostContext"), "$.plannedHostContext")
    require_string_fields(context, "$.plannedHostContext", ["contextKind", "contextState"])
    if context["contextKind"] != "summary_only_plugin_host_context":
        raise ShapeError(
            "unexpected value at $.plannedHostContext.contextKind: "
            "expected summary_only_plugin_host_context"
        )
    expect_bool(require_field(context, "$.plannedHostContext", "summaryOnly"), "$.plannedHostContext.summaryOnly")
    if context["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.plannedHostContext.summaryOnly: expected true")
    require_string_array(
        require_field(context, "$.plannedHostContext", "allowedSourceKinds"),
        "$.plannedHostContext.allowedSourceKinds",
        min_items=1,
    )
    context_false_fields = [
        "manifestContentIncluded",
        "manifestPathIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "localFileRead",
        "repositoryRead",
        "artifactRead",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
    ]
    require_bool_fields(context, "$.plannedHostContext", context_false_fields)
    for field in context_false_fields:
        if context[field] is not False:
            raise ShapeError(f"unexpected value at $.plannedHostContext.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "plugin-loader-start",
        "plugin-runtime-start",
        "plugin-sandbox-start",
        "plugin-invocation",
        "permission-executor",
        "manifest-reader",
        "validator-command",
        "command-execution",
        "package-install",
        "package-distribution",
        "marketplace-flow",
        "dynamic-code-load",
        "untrusted-execution",
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
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "pluginLoadRequestFixtureOnly",
        "summaryOnly",
    ]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginSandboxImplemented",
        "permissionExecutorImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "manifestReaderImplemented",
        "validatorCommandImplemented",
        "pluginInvocationPathImplemented",
        "pluginInvocationAttempted",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "packageInstall",
        "packageDistribution",
        "marketplaceFlow",
        "dynamicCodeLoad",
        "untrustedExecution",
        "networkCalls",
        "providerCalls",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
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


def validate_plugin_host_session_state(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-host-session-state.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "pluginHostSessionStateId",
            "pluginId",
            "capabilityId",
            "permissionProfile",
            "adapterState",
            "defaultMode",
            "hostMode",
            "sessionState",
            "loadState",
            "sandboxState",
            "runtimeState",
        ],
    )
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")
    if root["sessionState"] != "not_started":
        raise ShapeError("unexpected value at $.sessionState: expected not_started")
    if root["loadState"] != "not_loaded":
        raise ShapeError("unexpected value at $.loadState: expected not_loaded")
    if root["sandboxState"] != "not_started":
        raise ShapeError("unexpected value at $.sandboxState: expected not_started")
    if root["runtimeState"] != "not_started":
        raise ShapeError("unexpected value at $.runtimeState: expected not_started")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "pluginLoaderAllowed",
            "dynamicCodeLoadAllowed",
            "hostApiStable",
            "permissionExecutorAllowed",
            "sandboxStartAllowed",
            "pluginInvocationAllowed",
            "manifestReaderAllowed",
            "validatorCommandAllowed",
            "artifactWriteAllowed",
            "packageInstallAllowed",
            "repositoryMutationAllowed",
            "pluginRuntimeStartAllowed",
            "loggerAllowed",
            "pathEchoAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")
        if "approved" in ref and expect_bool(require_field(ref, path, "approved"), child(path, "approved")) is not False:
            raise ShapeError("unexpected value at $.sourceBoundaryRefs[].approved: expected false")

    session = expect_object(require_field(root, "$", "pluginHostSession"), "$.pluginHostSession")
    require_string_fields(
        session,
        "$.pluginHostSession",
        [
            "sessionKind",
            "lifecycleState",
            "loadState",
            "sandboxState",
            "runtimeState",
            "invocationState",
            "summary",
        ],
    )
    if session["sessionKind"] != "planned_plugin_host_session_state":
        raise ShapeError(
            "unexpected value at $.pluginHostSession.sessionKind: "
            "expected planned_plugin_host_session_state"
        )
    if session["lifecycleState"] != "not_started":
        raise ShapeError("unexpected value at $.pluginHostSession.lifecycleState: expected not_started")
    if session["loadState"] != "not_loaded":
        raise ShapeError("unexpected value at $.pluginHostSession.loadState: expected not_loaded")
    if session["sandboxState"] != "not_started":
        raise ShapeError("unexpected value at $.pluginHostSession.sandboxState: expected not_started")
    if session["runtimeState"] != "not_started":
        raise ShapeError("unexpected value at $.pluginHostSession.runtimeState: expected not_started")
    if session["invocationState"] != "not_invoked":
        raise ShapeError("unexpected value at $.pluginHostSession.invocationState: expected not_invoked")
    session_true_fields = ["summaryOnly", "approvalRequired"]
    session_false_fields = [
        "hostSessionOpen",
        "loaderStarted",
        "runtimeStarted",
        "sandboxStarted",
        "hostApiBound",
        "capabilityDispatchStarted",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "packageInstalled",
        "manifestReaderCalled",
        "validatorCommandCalled",
        "permissionExecutorCalled",
        "inputReaderCalled",
        "traceImporterCalled",
        "pluginInvocationStarted",
        "commandExecutionAttempted",
        "localFileReadAttempted",
        "repositoryReadAttempted",
        "artifactReadAttempted",
        "artifactWriteAttempted",
        "reportWriteAttempted",
        "providerCallAttempted",
        "networkCallAttempted",
        "hardwareAccessAttempted",
        "modelLoadAttempted",
    ]
    require_bool_fields(session, "$.pluginHostSession", session_true_fields + session_false_fields)
    for field in session_true_fields:
        if session[field] is not True:
            raise ShapeError(f"unexpected value at $.pluginHostSession.{field}: expected true")
    for field in session_false_fields:
        if session[field] is not False:
            raise ShapeError(f"unexpected value at $.pluginHostSession.{field}: expected false")

    rows = require_object_array(require_field(root, "$", "hostRows"), "$.hostRows", min_items=1)
    for row in rows:
        require_string_fields(
            row,
            "$.hostRows[]",
            ["rowId", "state", "sourceRef", "summary", "blockedReason"],
        )

    sandbox = expect_object(require_field(root, "$", "sandboxPolicy"), "$.sandboxPolicy")
    require_string_fields(sandbox, "$.sandboxPolicy", ["state"])
    if sandbox["state"] != "not_started":
        raise ShapeError("unexpected value at $.sandboxPolicy.state: expected not_started")
    sandbox_true_fields = ["sandboxRequired"]
    sandbox_false_fields = [
        "sandboxStartAllowed",
        "processIsolationStarted",
        "filesystemMountAllowed",
        "networkAllowed",
        "environmentPassed",
        "ipcAllowed",
        "permissionProfileApplied",
    ]
    require_bool_fields(sandbox, "$.sandboxPolicy", sandbox_true_fields + sandbox_false_fields)
    if sandbox["sandboxRequired"] is not True:
        raise ShapeError("unexpected value at $.sandboxPolicy.sandboxRequired: expected true")
    for field in sandbox_false_fields:
        if sandbox[field] is not False:
            raise ShapeError(f"unexpected value at $.sandboxPolicy.{field}: expected false")

    runtime = expect_object(require_field(root, "$", "runtimePolicy"), "$.runtimePolicy")
    require_string_fields(runtime, "$.runtimePolicy", ["state"])
    if runtime["state"] != "not_started":
        raise ShapeError("unexpected value at $.runtimePolicy.state: expected not_started")
    runtime_false_fields = [
        "pluginRuntimeStartAllowed",
        "dynamicCodeLoadAllowed",
        "packageInstallAllowed",
        "untrustedExecutionAllowed",
        "commandExecutionAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
    ]
    require_bool_fields(runtime, "$.runtimePolicy", runtime_false_fields)
    for field in runtime_false_fields:
        if runtime[field] is not False:
            raise ShapeError(f"unexpected value at $.runtimePolicy.{field}: expected false")

    audit = expect_object(require_field(root, "$", "auditPolicy"), "$.auditPolicy")
    require_string_fields(audit, "$.auditPolicy", ["state", "eventSchema", "storageState"])
    audit_true_fields = ["summaryOnly"]
    audit_false_fields = [
        "auditLoggerAllowed",
        "auditPersistenceAllowed",
        "pathEchoAllowed",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
    ]
    require_bool_fields(audit, "$.auditPolicy", audit_true_fields + audit_false_fields)
    if audit["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.auditPolicy.summaryOnly: expected true")
    for field in audit_false_fields:
        if audit[field] is not False:
            raise ShapeError(f"unexpected value at $.auditPolicy.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "plugin-host-session",
        "plugin-loader-start",
        "plugin-runtime-start",
        "plugin-sandbox-start",
        "plugin-host-api-bind",
        "plugin-capability-dispatch",
        "plugin-invocation",
        "permission-executor",
        "input-reader",
        "trace-importer",
        "manifest-reader",
        "validator-command",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "repository-write-back",
        "package-install",
        "package-distribution",
        "marketplace-flow",
        "dynamic-code-load",
        "untrusted-execution",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "pluginHostSessionStateFixtureOnly",
        "summaryOnly",
    ]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginSandboxImplemented",
        "pluginHostSessionStarted",
        "pluginHostApiBound",
        "capabilityDispatchImplemented",
        "permissionExecutorImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "manifestReaderImplemented",
        "validatorCommandImplemented",
        "pluginInvocationPathImplemented",
        "pluginInvocationAttempted",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "auditLoggerImplemented",
        "auditPersistence",
        "packageInstall",
        "packageDistribution",
        "marketplaceFlow",
        "dynamicCodeLoad",
        "untrustedExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
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


def validate_plugin_invocation_request(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-invocation-request.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "invocationRequestId",
            "pluginHostSessionStateId",
            "loadRequestId",
            "reviewPacketId",
            "pluginId",
            "capabilityId",
            "permissionProfile",
            "requestState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["requestState"] != "blocked_by_policy":
        raise ShapeError("unexpected value at $.requestState: expected blocked_by_policy")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "permissionExecutorAllowed",
            "sandboxStartAllowed",
            "pluginInvocationAllowed",
            "inputReaderAllowed",
            "rawTraceAllowed",
            "artifactReadAllowed",
            "commandExecutionAllowed",
            "artifactWriteAllowed",
            "pluginLoaderAllowed",
            "pluginRuntimeStartAllowed",
            "hostSessionOpen",
            "hostApiBindAllowed",
            "capabilityDispatchAllowed",
            "loggerAllowed",
            "pathEchoAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")
        if "approved" in ref and expect_bool(require_field(ref, path, "approved"), child(path, "approved")) is not False:
            raise ShapeError("unexpected value at $.sourceBoundaryRefs[].approved: expected false")

    request = expect_object(require_field(root, "$", "invocationRequest"), "$.invocationRequest")
    require_string_fields(
        request,
        "$.invocationRequest",
        [
            "requestKind",
            "commandKind",
            "approvedInputReferenceKind",
            "outputBoundary",
            "summary",
        ],
    )
    if request["requestKind"] != "planned_plugin_invocation_gate":
        raise ShapeError(
            "unexpected value at $.invocationRequest.requestKind: "
            "expected planned_plugin_invocation_gate"
        )
    require_string_array(
        require_field(request, "$.invocationRequest", "fixedArgsPreview"),
        "$.invocationRequest.fixedArgsPreview",
        min_items=1,
    )
    request_true_fields = ["summaryOnly", "approvalRequired", "inputRefOnly"]
    request_false_fields = [
        "approved",
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "artifactReadAllowed",
        "commandExecutionAllowed",
        "shellExecutionAllowed",
        "runtimeExecutionAllowed",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "hostApiBindAllowed",
        "capabilityDispatchAllowed",
        "pluginInvocationAllowed",
        "packageInstallAllowed",
        "dynamicCodeLoadAllowed",
        "providerCallAllowed",
        "networkCallAllowed",
        "launcherExecutionAllowed",
        "editorExecutionAllowed",
        "hardwareAccessAllowed",
        "modelLoadAllowed",
    ]
    require_bool_fields(request, "$.invocationRequest", request_true_fields + request_false_fields)
    for field in request_true_fields:
        if request[field] is not True:
            raise ShapeError(f"unexpected value at $.invocationRequest.{field}: expected true")
    for field in request_false_fields:
        if request[field] is not False:
            raise ShapeError(f"unexpected value at $.invocationRequest.{field}: expected false")

    decision = expect_object(require_field(root, "$", "invocationDecision"), "$.invocationDecision")
    require_string_fields(decision, "$.invocationDecision", ["state", "reason"])
    if decision["state"] != "not_invoked":
        raise ShapeError("unexpected value at $.invocationDecision.state: expected not_invoked")
    decision_true_fields = ["denied"]
    decision_false_fields = [
        "approved",
        "pluginHostSessionStarted",
        "pluginLoaded",
        "sandboxStarted",
        "runtimeStarted",
        "hostApiBound",
        "capabilityDispatchStarted",
        "pluginInvocationStarted",
        "permissionExecutorCalled",
        "inputReaderCalled",
        "traceImporterCalled",
        "manifestReaderCalled",
        "validatorCommandCalled",
        "commandExecutionAttempted",
        "shellExecutionAttempted",
        "runtimeExecutionAttempted",
        "localFileReadAttempted",
        "repositoryReadAttempted",
        "rawTraceReadAttempted",
        "rawReportReadAttempted",
        "artifactReadAttempted",
        "artifactWriteAttempted",
        "reportWriteAttempted",
        "repositoryMutationAttempted",
        "providerCallAttempted",
        "networkCallAttempted",
        "hardwareAccessAttempted",
        "modelLoadAttempted",
    ]
    require_bool_fields(decision, "$.invocationDecision", decision_true_fields + decision_false_fields)
    if decision["denied"] is not True:
        raise ShapeError("unexpected value at $.invocationDecision.denied: expected true")
    for field in decision_false_fields:
        if decision[field] is not False:
            raise ShapeError(f"unexpected value at $.invocationDecision.{field}: expected false")

    context = expect_object(require_field(root, "$", "plannedPluginContext"), "$.plannedPluginContext")
    require_string_fields(context, "$.plannedPluginContext", ["contextKind", "contextState"])
    if context["contextKind"] != "summary_only_plugin_invocation_context":
        raise ShapeError(
            "unexpected value at $.plannedPluginContext.contextKind: "
            "expected summary_only_plugin_invocation_context"
        )
    context_true_fields = ["summaryOnly", "approvedInputReferenceOnly"]
    context_false_fields = [
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "artifactRead",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "modelWeightPathsIncluded",
    ]
    require_string_array(
        require_field(context, "$.plannedPluginContext", "allowedSourceKinds"),
        "$.plannedPluginContext.allowedSourceKinds",
        min_items=1,
    )
    require_bool_fields(context, "$.plannedPluginContext", context_true_fields + context_false_fields)
    for field in context_true_fields:
        if context[field] is not True:
            raise ShapeError(f"unexpected value at $.plannedPluginContext.{field}: expected true")
    for field in context_false_fields:
        if context[field] is not False:
            raise ShapeError(f"unexpected value at $.plannedPluginContext.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplacePublicationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    audit = expect_object(require_field(root, "$", "auditEventRef"), "$.auditEventRef")
    require_string_fields(audit, "$.auditEventRef", ["schemaVersion", "examplePath", "eventState", "storageState"])

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "plugin-host-session",
        "plugin-loader-start",
        "plugin-runtime-start",
        "plugin-sandbox-start",
        "plugin-host-api-bind",
        "plugin-capability-dispatch",
        "plugin-invocation",
        "permission-executor",
        "input-reader",
        "trace-importer",
        "manifest-reader",
        "validator-command",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "repository-write-back",
        "package-install",
        "package-distribution",
        "marketplace-flow",
        "dynamic-code-load",
        "untrusted-execution",
        "provider-call",
        "network-call",
        "launcher-execution",
        "editor-execution",
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
    true_flags = [
        "dataOnly",
        "descriptorOnly",
        "readOnly",
        "pluginInvocationRequestFixtureOnly",
        "summaryOnly",
    ]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginSandboxImplemented",
        "pluginHostSessionStarted",
        "pluginHostApiBound",
        "capabilityDispatchImplemented",
        "permissionExecutorImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "manifestReaderImplemented",
        "validatorCommandImplemented",
        "pluginInvocationPathImplemented",
        "pluginInvocationAttempted",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "auditLoggerImplemented",
        "auditPersistence",
        "packageInstall",
        "packageDistribution",
        "marketplaceFlow",
        "dynamicCodeLoad",
        "untrustedExecution",
        "networkCalls",
        "providerCalls",
        "launcherExecution",
        "editorExecution",
        "hardwareAccess",
        "kv260Access",
        "fpgaRepoAccess",
        "modelExecution",
        "privatePathsIncluded",
        "manifestContentIncluded",
        "packageContentIncluded",
        "sourceCodeIncluded",
        "secretsIncluded",
        "tokensIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "diagnosticsProduced",
        "panelProduced",
        "reportItemsProduced",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
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


def validate_plugin_review_packet(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-review-packet.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "reviewPacketId",
            "reviewState",
            "adapterState",
            "defaultMode",
            "packetKind",
            "automationPath",
        ],
    )
    if root["reviewState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.reviewState: expected descriptor_only")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["packetKind"] != "summary_only_plugin_review_packet":
        raise ShapeError("unexpected value at $.packetKind: expected summary_only_plugin_review_packet")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        path = "$.sourceBoundaryRefs[]"
        require_string_fields(ref, path, ["refId", "schemaVersion", "examplePath", "state"])
        for field in [
            "capabilityGrantAllowed",
            "sandboxStartAllowed",
            "artifactWriteAllowed",
            "pluginInvocationAllowed",
            "inputReaderAllowed",
            "rawTraceAllowed",
            "artifactReadAllowed",
            "traceImporterAllowed",
            "reportWriteAllowed",
            "pathEchoAllowed",
            "commandExecutionAllowed",
            "manifestReaderAllowed",
            "validatorCommandAllowed",
            "loggerAllowed",
        ]:
            if field in ref and expect_bool(require_field(ref, path, field), child(path, field)) is not False:
                raise ShapeError(f"unexpected value at $.sourceBoundaryRefs[].{field}: expected false")

    inputs = require_object_array(
        require_field(root, "$", "reviewInputs"),
        "$.reviewInputs",
        min_items=5,
    )
    input_ids = set()
    allowed_input_kinds = {
        "permission_summary",
        "input_summary",
        "output_summary",
        "blocked_result_summary",
        "manifest_validation_summary",
        "audit_summary",
    }
    for input_item in inputs:
        path = "$.reviewInputs[]"
        require_string_fields(
            input_item,
            path,
            [
                "inputId",
                "inputKind",
                "inputState",
                "sourceRef",
                "summary",
            ],
        )
        input_id = input_item["inputId"]
        if input_id in input_ids:
            raise ShapeError(f"duplicate value at $.reviewInputs[].inputId: {input_id}")
        input_ids.add(input_id)
        if input_item["inputKind"] not in allowed_input_kinds:
            raise ShapeError(
                "unexpected value at $.reviewInputs[].inputKind: "
                f"expected one of {sorted(allowed_input_kinds)}"
            )
        if input_item["inputState"] != "approved_summary_only":
            raise ShapeError("unexpected value at $.reviewInputs[].inputState: expected approved_summary_only")
        true_fields = ["summaryOnly", "approvalRequired"]
        false_fields = [
            "localFileRead",
            "repositoryRead",
            "rawTraceRead",
            "rawReportRead",
            "artifactRead",
            "privatePathEchoAllowed",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogIncluded",
            "artifactPathIncluded",
        ]
        require_bool_fields(input_item, path, true_fields + false_fields)
        for field in true_fields:
            if input_item[field] is not True:
                raise ShapeError(f"unexpected value at $.reviewInputs[].{field}: expected true")
        for field in false_fields:
            if input_item[field] is not False:
                raise ShapeError(f"unexpected value at $.reviewInputs[].{field}: expected false")
        fields = require_object_array(
            require_field(input_item, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.reviewInputs[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    policy = expect_object(require_field(root, "$", "reviewPolicy"), "$.reviewPolicy")
    require_string_fields(policy, "$.reviewPolicy", ["state", "packetKind", "redactionRule"])
    if policy["state"] != "planned":
        raise ShapeError("unexpected value at $.reviewPolicy.state: expected planned")
    if policy["packetKind"] != "summary_only_plugin_review_packet":
        raise ShapeError("unexpected value at $.reviewPolicy.packetKind: expected summary_only_plugin_review_packet")
    expect_integer(require_field(policy, "$.reviewPolicy", "maxSections"), "$.reviewPolicy.maxSections")
    true_policy_flags = ["summaryOnly", "approvalRequired", "auditRequired"]
    false_policy_flags = [
        "pluginInvocationAllowed",
        "pluginLoaderAllowed",
        "pluginRuntimeAllowed",
        "sandboxStartAllowed",
        "permissionExecutionAllowed",
        "inputReaderAllowed",
        "traceImporterAllowed",
        "manifestReaderAllowed",
        "validatorCommandAllowed",
        "commandExecutionAllowed",
        "localFileReadAllowed",
        "repositoryReadAllowed",
        "rawTraceReadAllowed",
        "rawReportReadAllowed",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
        "packageInstallAllowed",
        "packageDistributionAllowed",
        "marketplaceFlowAllowed",
        "dynamicCodeLoadAllowed",
        "untrustedExecutionAllowed",
        "pathEchoAllowed",
        "stdoutAllowed",
        "stderrAllowed",
        "rawLogAllowed",
        "privatePathsAllowed",
        "generatedArtifactsAllowed",
    ]
    require_bool_fields(policy, "$.reviewPolicy", true_policy_flags + false_policy_flags)
    for flag in true_policy_flags:
        if policy[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewPolicy.{flag}: expected true")
    for flag in false_policy_flags:
        if policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewPolicy.{flag}: expected false")

    packet = expect_object(require_field(root, "$", "sampleReviewPacket"), "$.sampleReviewPacket")
    require_string_fields(
        packet,
        "$.sampleReviewPacket",
        ["reviewPacketState", "targetRepository", "titlePreview"],
    )
    if packet["reviewPacketState"] != "summary_only_fixture":
        raise ShapeError("unexpected value at $.sampleReviewPacket.reviewPacketState: expected summary_only_fixture")

    section_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
    ]
    sections = require_object_array(
        require_field(packet, "$.sampleReviewPacket", "reviewSections"),
        "$.sampleReviewPacket.reviewSections",
        min_items=2,
    )
    for section in sections:
        path = "$.sampleReviewPacket.reviewSections[]"
        require_string_fields(section, path, ["sectionId", "sectionKind", "heading", "summary"])
        require_bool_fields(section, path, ["summaryOnly"] + section_false_fields)
        if section["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleReviewPacket.reviewSections[].summaryOnly: expected true")
        for field in section_false_fields:
            if section[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleReviewPacket.reviewSections[].{field}: expected false")

    for list_name in ["riskRows", "checklistItems"]:
        rows = require_object_array(
            require_field(packet, "$.sampleReviewPacket", list_name),
            f"$.sampleReviewPacket.{list_name}",
            min_items=1,
        )
        for row in rows:
            path = f"$.sampleReviewPacket.{list_name}[]"
            required = ["rowId", "severity", "sourceRef", "summary", "mitigation"] if list_name == "riskRows" else ["itemId", "state", "label"]
            require_string_fields(row, path, required)
            require_bool_fields(
                row,
                path,
                ["summaryOnly", "commandIncluded", "pathIncluded", "artifactPathIncluded"],
            )
            if row["summaryOnly"] is not True:
                raise ShapeError(f"unexpected value at {path}.summaryOnly: expected true")
            for field in ["commandIncluded", "pathIncluded", "artifactPathIncluded"]:
                if row[field] is not False:
                    raise ShapeError(f"unexpected value at {path}.{field}: expected false")

    validation_lines = require_object_array(
        require_field(packet, "$.sampleReviewPacket", "validationLines"),
        "$.sampleReviewPacket.validationLines",
        min_items=1,
    )
    for line in validation_lines:
        path = "$.sampleReviewPacket.validationLines[]"
        require_string_fields(line, path, ["lineId", "result", "summary"])
        require_bool_fields(
            line,
            path,
            [
                "summaryOnly",
                "commandIncluded",
                "stdoutIncluded",
                "stderrIncluded",
                "rawLogsIncluded",
                "artifactPathIncluded",
            ],
        )
        if line["summaryOnly"] is not True:
            raise ShapeError("unexpected value at $.sampleReviewPacket.validationLines[].summaryOnly: expected true")
        for field in [
            "commandIncluded",
            "stdoutIncluded",
            "stderrIncluded",
            "rawLogsIncluded",
            "artifactPathIncluded",
        ]:
            if line[field] is not False:
                raise ShapeError(f"unexpected value at $.sampleReviewPacket.validationLines[].{field}: expected false")

    packet_true_fields = ["summaryOnly"]
    packet_false_fields = [
        "pathIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "rawTraceIncluded",
        "rawReportIncluded",
        "pluginInvoked",
        "manifestRead",
        "packageInstalled",
        "marketplacePublished",
        "projectUpdated",
        "publicTextPublished",
    ]
    require_bool_fields(packet, "$.sampleReviewPacket", packet_true_fields + packet_false_fields)
    if packet["summaryOnly"] is not True:
        raise ShapeError("unexpected value at $.sampleReviewPacket.summaryOnly: expected true")
    for field in packet_false_fields:
        if packet[field] is not False:
            raise ShapeError(f"unexpected value at $.sampleReviewPacket.{field}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_fields = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "reportWriteAllowed",
        "repositoryMutationAllowed",
        "pluginInvocationAllowed",
        "commandExecutionAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
        "projectMutationAllowed",
        "marketplacePublicationAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_fields)
    for field in mutation_false_fields:
        if mutation[field] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{field}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "plugin-loader-start",
        "plugin-runtime-start",
        "plugin-sandbox-start",
        "plugin-invocation",
        "permission-executor",
        "input-reader",
        "trace-importer",
        "manifest-reader",
        "validator-command",
        "command-execution",
        "arbitrary-shell-command",
        "local-file-read",
        "repository-read",
        "raw-trace-read",
        "raw-report-read",
        "artifact-read",
        "artifact-write",
        "report-write",
        "repository-write-back",
        "package-install",
        "package-distribution",
        "marketplace-flow",
        "dynamic-code-load",
        "untrusted-execution",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "pluginReviewPacketFixtureOnly", "summaryOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginSandboxImplemented",
        "permissionExecutorImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
        "toolInvocationPathImplemented",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportWriterImplemented",
        "packageInstall",
        "packageDistribution",
        "marketplaceFlow",
        "dynamicCodeLoad",
        "untrustedExecution",
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
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "compatibilityClaim",
        "marketplaceClaim",
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


def validate_plugin_trace_summary_input(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-trace-summary-input.v0")
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

    inputs = require_object_array(
        require_field(root, "$", "traceSummaryInputs"),
        "$.traceSummaryInputs",
        min_items=1,
    )
    for input_item in inputs:
        path = "$.traceSummaryInputs[]"
        require_string_fields(
            input_item,
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
        if input_item["inputKind"] != "trace_summary":
            raise ShapeError("unexpected value at $.traceSummaryInputs[].inputKind: expected trace_summary")
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
            "rawTraceIncluded",
        ]
        require_bool_fields(input_item, path, true_fields + false_fields)
        for field in true_fields:
            if input_item[field] is not True:
                raise ShapeError(f"unexpected value at $.traceSummaryInputs[].{field}: expected true")
        for field in false_fields:
            if input_item[field] is not False:
                raise ShapeError(f"unexpected value at $.traceSummaryInputs[].{field}: expected false")
        fields = require_object_array(
            require_field(input_item, path, "fieldDescriptors"),
            child(path, "fieldDescriptors"),
            min_items=1,
        )
        for field in fields:
            require_string_fields(
                field,
                "$.traceSummaryInputs[].fieldDescriptors[]",
                ["fieldName", "valueKind", "policy"],
            )

    summary = expect_object(require_field(root, "$", "sampleTraceSummary"), "$.sampleTraceSummary")
    require_string_fields(summary, "$.sampleTraceSummary", ["sourceRef", "traceSummaryId"])
    for field in ["eventCount", "signalCount", "cycleStart", "cycleEnd"]:
        expect_integer(require_field(summary, "$.sampleTraceSummary", field), f"$.sampleTraceSummary.{field}")
    counts = expect_object(
        require_field(summary, "$.sampleTraceSummary", "eventKindCounts"),
        "$.sampleTraceSummary.eventKindCounts",
    )
    if not counts:
        raise ShapeError("expected at least 1 item(s) at $.sampleTraceSummary.eventKindCounts")
    for key, count in counts.items():
        expect_string(key, "$.sampleTraceSummary.eventKindCounts{}")
        expect_integer(count, "$.sampleTraceSummary.eventKindCounts{}")
    summary_false_fields = [
        "pathIncluded",
        "signalNamesIncluded",
        "rawTraceIncluded",
        "privatePathsIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "generatedArtifactsIncluded",
    ]
    require_bool_fields(summary, "$.sampleTraceSummary", summary_false_fields)
    for field in summary_false_fields:
        if summary[field] is not False:
            raise ShapeError(f"unexpected value at $.sampleTraceSummary.{field}: expected false")

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
        "sandbox-bypass",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "inputFixtureOnly", "summaryOnly", "traceSummaryOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "inputReaderImplemented",
        "traceImporterImplemented",
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
        "signalNamesIncluded",
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


def validate_plugin_blocked_invocation_result(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.plugin-blocked-invocation-result.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "resultId",
            "pluginId",
            "capabilityId",
            "permissionProfile",
            "resultState",
            "pluginRuntimeState",
            "loaderState",
            "sandboxState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["resultState"] != "blocked_by_policy":
        raise ShapeError("unexpected value at $.resultState: expected blocked_by_policy")
    if root["pluginRuntimeState"] != "not_implemented":
        raise ShapeError("unexpected value at $.pluginRuntimeState: expected not_implemented")
    if root["loaderState"] != "not_implemented":
        raise ShapeError("unexpected value at $.loaderState: expected not_implemented")
    if root["sandboxState"] != "not_implemented":
        raise ShapeError("unexpected value at $.sandboxState: expected not_implemented")
    if root["defaultMode"] != "disabled":
        raise ShapeError("unexpected value at $.defaultMode: expected disabled")
    if root["hostMode"] != "cli_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_first_gui_second")

    input_ref = expect_object(require_field(root, "$", "sourceInputRef"), "$.sourceInputRef")
    require_string_fields(
        input_ref,
        "$.sourceInputRef",
        ["schemaVersion", "examplePath", "inputState"],
    )
    if expect_bool(require_field(input_ref, "$.sourceInputRef", "pathEchoAllowed"), "$.sourceInputRef.pathEchoAllowed") is not False:
        raise ShapeError("unexpected value at $.sourceInputRef.pathEchoAllowed: expected false")

    output_ref = expect_object(require_field(root, "$", "sourceOutputRef"), "$.sourceOutputRef")
    require_string_fields(
        output_ref,
        "$.sourceOutputRef",
        ["schemaVersion", "examplePath", "outputState"],
    )
    if expect_bool(require_field(output_ref, "$.sourceOutputRef", "artifactWriteAllowed"), "$.sourceOutputRef.artifactWriteAllowed") is not False:
        raise ShapeError("unexpected value at $.sourceOutputRef.artifactWriteAllowed: expected false")

    audit_ref = expect_object(require_field(root, "$", "auditEventRef"), "$.auditEventRef")
    require_string_fields(
        audit_ref,
        "$.auditEventRef",
        ["schemaVersion", "examplePath", "eventState", "storageState"],
    )

    request = expect_object(require_field(root, "$", "pluginInvocationRequest"), "$.pluginInvocationRequest")
    require_string_fields(
        request,
        "$.pluginInvocationRequest",
        ["commandKind", "approvedInputReferenceKind"],
    )
    require_string_array(
        require_field(request, "$.pluginInvocationRequest", "fixedArgsPreview"),
        "$.pluginInvocationRequest.fixedArgsPreview",
        min_items=1,
    )
    request_false_flags = [
        "pathEchoAllowed",
        "rawShellCommandAllowed",
        "pluginCodeLoadAllowed",
        "packageInstallAllowed",
    ]
    require_bool_fields(request, "$.pluginInvocationRequest", request_false_flags)
    for flag in request_false_flags:
        if request[flag] is not False:
            raise ShapeError(f"unexpected value at $.pluginInvocationRequest.{flag}: expected false")

    blocked = expect_object(require_field(root, "$", "blockedResult"), "$.blockedResult")
    require_string_fields(blocked, "$.blockedResult", ["state", "reason", "summary"])
    if blocked["state"] != "not_executed":
        raise ShapeError("unexpected value at $.blockedResult.state: expected not_executed")
    expect_nullable_integer(require_field(blocked, "$.blockedResult", "exitCode"), "$.blockedResult.exitCode")
    blocked_true_flags = ["summaryOnly"]
    blocked_false_flags = [
        "pluginInvocationAttempted",
        "pluginCodeLoaded",
        "commandExecutionAttempted",
        "inputReaderAttempted",
        "artifactReadAttempted",
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
        "panelProduced",
        "reportItemsProduced",
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
        "artifactReadAllowed",
        "artifactWriteAllowed",
        "publicPushAllowed",
        "releaseOrTagAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked_actions = require_field(root, "$", "blockedActions")
    require_string_array(blocked_actions, "$.blockedActions", min_items=1)
    for required in [
        "plugin-loader-start",
        "plugin-runtime-start",
        "sandbox-bypass",
        "permission-executor",
        "input-reader",
        "output-writer",
        "dynamic-code-load",
        "untrusted-execution",
        "plugin-package-install",
        "marketplace-flow",
        "package-distribution",
        "arbitrary-shell-command",
        "command-execution",
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
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "blockedResultFixtureOnly", "summaryOnly"]
    false_flags = [
        "pluginRuntimeImplemented",
        "pluginLoaderImplemented",
        "pluginInvocationPathImplemented",
        "pluginInvocationAttempted",
        "pluginCodeLoaded",
        "dynamicLibrariesLoaded",
        "sandboxImplemented",
        "permissionExecutorImplemented",
        "inputReaderImplemented",
        "reportWriterImplemented",
        "stablePluginAbiPromised",
        "marketplaceFlow",
        "packageDistribution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
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
        "diagnosticsProduced",
        "panelProduced",
        "reportItemsProduced",
        "telemetry",
        "writeBack",
        "repositoryMutation",
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


def validate_sail_adoption_plan(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.sail-adoption-plan.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "adoptionPlanId",
            "planState",
            "modelState",
            "adapterState",
            "defaultMode",
            "hostMode",
        ],
    )
    if root["planState"] != "descriptor_only":
        raise ShapeError("unexpected value at $.planState: expected descriptor_only")
    if root["modelState"] != "not_implemented":
        raise ShapeError("unexpected value at $.modelState: expected not_implemented")
    if root["adapterState"] != "not_implemented":
        raise ShapeError("unexpected value at $.adapterState: expected not_implemented")
    if root["defaultMode"] != "read_only":
        raise ShapeError("unexpected value at $.defaultMode: expected read_only")
    if root["hostMode"] != "cli_core_first_gui_second":
        raise ShapeError("unexpected value at $.hostMode: expected cli_core_first_gui_second")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    if not any(
        ref["refId"] == "workflow_descriptors"
        and ref.get("sailWorkflowCandidate") is True
        and ref.get("commandExecutionAllowed") is False
        and ref.get("modelExecutionAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing workflow_descriptors Sail source reference")
    if not any(
        ref["refId"] == "workflow_results"
        and ref.get("resultSummaryAvailable") is True
        and ref.get("payloadIncluded") is False
        and ref.get("reportWriterAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing workflow_results summary-only source reference")
    if not any(
        ref["refId"] == "verification_gate"
        and ref.get("sailGateImplemented") is False
        and ref.get("refinementExecutionAllowed") is False
        and ref.get("formalProofAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing disabled verification_gate source reference")

    plan = expect_object(require_field(root, "$", "adoptionPlan"), "$.adoptionPlan")
    require_string_fields(
        plan,
        "$.adoptionPlan",
        ["planKind", "scope", "issueRef", "plannedModelRole"],
    )
    plan_true_flags = ["summaryOnly", "descriptorOnly", "cliCoreFirst", "guiSecond"]
    plan_false_flags = [
        "sailParserImplemented",
        "sailCompilerImplemented",
        "sailModelImplemented",
        "sailExecutionAllowed",
        "rtlRefinementAllowed",
        "formalProofAllowed",
    ]
    require_bool_fields(plan, "$.adoptionPlan", plan_true_flags + plan_false_flags)
    for flag in plan_true_flags:
        if plan[flag] is not True:
            raise ShapeError(f"unexpected value at $.adoptionPlan.{flag}: expected true")
    for flag in plan_false_flags:
        if plan[flag] is not False:
            raise ShapeError(f"unexpected value at $.adoptionPlan.{flag}: expected false")

    phases = require_object_array(require_field(root, "$", "plannedPhases"), "$.plannedPhases", min_items=1)
    phase_ids = set()
    for phase in phases:
        path = "$.plannedPhases[]"
        require_string_fields(
            phase,
            path,
            ["phaseId", "state", "summary", "requiredBefore", "sideEffectPolicy"],
        )
        phase_ids.add(phase["phaseId"])
        if phase["phaseId"] != "execution_gate_review":
            require_bool_fields(phase, path, ["fileReadAllowed", "commandExecutionAllowed"])
            if phase["fileReadAllowed"] is not False:
                raise ShapeError("unexpected value at $.plannedPhases[].fileReadAllowed: expected false")
            if phase["commandExecutionAllowed"] is not False:
                raise ShapeError("unexpected value at $.plannedPhases[].commandExecutionAllowed: expected false")
    for phase_id in ["model_scope_review", "boundary_shape_review", "execution_gate_review"]:
        if phase_id not in phase_ids:
            raise ShapeError(f"missing phase id in $.plannedPhases: {phase_id}")

    input_policy = expect_object(require_field(root, "$", "inputPolicy"), "$.inputPolicy")
    require_string_fields(input_policy, "$.inputPolicy", ["acceptedInputKind", "summary"])
    input_false_flags = [
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "sailSourceReadAllowed",
        "rtlSourceReadAllowed",
        "traceReadAllowed",
        "reportReadAllowed",
        "artifactReadAllowed",
        "repositoryReadAllowed",
        "environmentReadAllowed",
        "secretsReadAllowed",
        "tokensReadAllowed",
    ]
    require_bool_fields(input_policy, "$.inputPolicy", input_false_flags)
    for flag in input_false_flags:
        if input_policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.inputPolicy.{flag}: expected false")

    output_policy = expect_object(require_field(root, "$", "outputPolicy"), "$.outputPolicy")
    require_string_fields(output_policy, "$.outputPolicy", ["outputKind", "summary"])
    output_false_flags = [
        "sailSourceIncluded",
        "generatedModelIncluded",
        "compiledArtifactIncluded",
        "proofArtifactIncluded",
        "rtlContentIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
    ]
    require_bool_fields(output_policy, "$.outputPolicy", output_false_flags)
    for flag in output_false_flags:
        if output_policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.outputPolicy.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForDescriptor"]
    review_false_flags = [
        "approvedForSourceRead",
        "approvedForModelGeneration",
        "approvedForParser",
        "approvedForCompiler",
        "approvedForExecution",
        "approvedForRefinementCheck",
        "approvedForProof",
        "approvedForReportWrite",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "sailSourceReadAllowed",
        "rtlSourceReadAllowed",
        "reportWriteAllowed",
        "artifactWriteAllowed",
        "repositoryMutationAllowed",
        "commandExecutionAllowed",
        "runtimeExecutionAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked = require_field(root, "$", "blockedActions")
    require_string_array(blocked, "$.blockedActions", min_items=1)
    for required in [
        "sail-source-read",
        "sail-parser",
        "sail-compiler",
        "sail-model-generation",
        "sail-model-execution",
        "rtl-source-read",
        "rtl-refinement-check",
        "formal-proof",
        "command-execution",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "planOnly", "summaryOnly"]
    false_flags = [
        "sailParserImplemented",
        "sailCompilerImplemented",
        "sailModelImplemented",
        "sailExecution",
        "rtlRefinementExecution",
        "formalVerificationExecution",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportReaderImplemented",
        "reportWriterImplemented",
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
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "runtimeClaim",
        "hardwareClaim",
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


def validate_hybrid_strategy_plan(value: Any) -> None:
    root = expect_object(value, "$")
    require_schema(root, "$", "pccx.lab.hybrid-strategy-plan.v0")
    require_string_fields(
        root,
        "$",
        [
            "tool",
            "strategyPlanId",
            "strategyState",
            "lowLevelTrackState",
            "scriptTrackState",
            "controlRuntimeState",
            "defaultMode",
            "hostMode",
        ],
    )
    expected_states = {
        "strategyState": "descriptor_only",
        "lowLevelTrackState": "planned_descriptor",
        "scriptTrackState": "not_implemented",
        "controlRuntimeState": "not_implemented",
        "defaultMode": "descriptor_only",
        "hostMode": "cli_core_first_gui_second",
    }
    for field, expected in expected_states.items():
        if root[field] != expected:
            raise ShapeError(f"unexpected value at $.{field}: expected {expected}")

    refs = require_object_array(
        require_field(root, "$", "sourceBoundaryRefs"),
        "$.sourceBoundaryRefs",
        min_items=1,
    )
    for ref in refs:
        require_string_fields(ref, "$.sourceBoundaryRefs[]", ["refId", "schemaVersion", "examplePath", "state"])
    if not any(
        ref["refId"] == "workflow_descriptors"
        and ref.get("lowLevelTrackCandidate") is True
        and ref.get("scriptTrackCandidate") is True
        and ref.get("commandExecutionAllowed") is False
        and ref.get("runtimeExecutionAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing workflow_descriptors hybrid strategy source reference")
    if not any(
        ref["refId"] == "workflow_results"
        and ref.get("resultSummaryAvailable") is True
        and ref.get("payloadIncluded") is False
        and ref.get("reportWriterAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing workflow_results summary-only source reference")
    if not any(
        ref["refId"] == "verification_gate"
        and ref.get("verificationRunAllowed") is False
        and ref.get("simulatorExecutionAllowed") is False
        and ref.get("hardwareControlAllowed") is False
        for ref in refs
    ):
        raise ShapeError("missing disabled verification_gate source reference")

    strategy = expect_object(require_field(root, "$", "hybridStrategy"), "$.hybridStrategy")
    require_string_fields(strategy, "$.hybridStrategy", ["strategyKind", "scope", "issueRef"])
    strategy_true_flags = ["summaryOnly", "descriptorOnly", "cliCoreFirst", "guiSecond"]
    require_bool_fields(strategy, "$.hybridStrategy", strategy_true_flags)
    for flag in strategy_true_flags:
        if strategy[flag] is not True:
            raise ShapeError(f"unexpected value at $.hybridStrategy.{flag}: expected true")

    low_level = expect_object(
        require_field(strategy, "$.hybridStrategy", "lowLevelTrack"),
        "$.hybridStrategy.lowLevelTrack",
    )
    require_string_fields(
        low_level,
        "$.hybridStrategy.lowLevelTrack",
        ["trackId", "trackState", "audience", "purpose"],
    )
    if low_level["trackState"] != "planned_descriptor":
        raise ShapeError("unexpected value at $.hybridStrategy.lowLevelTrack.trackState: expected planned_descriptor")
    low_level_false_flags = [
        "sourceReadAllowed",
        "simulatorExecutionAllowed",
        "verificationRunAllowed",
        "hardwareControlAllowed",
    ]
    require_bool_fields(low_level, "$.hybridStrategy.lowLevelTrack", low_level_false_flags)
    for flag in low_level_false_flags:
        if low_level[flag] is not False:
            raise ShapeError(f"unexpected value at $.hybridStrategy.lowLevelTrack.{flag}: expected false")

    script = expect_object(
        require_field(strategy, "$.hybridStrategy", "scriptTrack"),
        "$.hybridStrategy.scriptTrack",
    )
    require_string_fields(
        script,
        "$.hybridStrategy.scriptTrack",
        ["trackId", "trackState", "audience", "purpose"],
    )
    if script["trackState"] != "not_implemented":
        raise ShapeError("unexpected value at $.hybridStrategy.scriptTrack.trackState: expected not_implemented")
    script_false_flags = [
        "grammarIncluded",
        "parserImplemented",
        "compilerImplemented",
        "runtimeImplemented",
        "scriptExecutionAllowed",
        "hardwareControlAllowed",
    ]
    require_bool_fields(script, "$.hybridStrategy.scriptTrack", script_false_flags)
    for flag in script_false_flags:
        if script[flag] is not False:
            raise ShapeError(f"unexpected value at $.hybridStrategy.scriptTrack.{flag}: expected false")

    phases = require_object_array(require_field(root, "$", "plannedPhases"), "$.plannedPhases", min_items=1)
    phase_ids = set()
    for phase in phases:
        path = "$.plannedPhases[]"
        require_string_fields(
            phase,
            path,
            ["phaseId", "state", "summary", "requiredBefore", "sideEffectPolicy"],
        )
        phase_ids.add(phase["phaseId"])
        if phase["phaseId"] != "execution_gate_review":
            require_bool_fields(phase, path, ["fileReadAllowed", "commandExecutionAllowed"])
            if phase["fileReadAllowed"] is not False:
                raise ShapeError("unexpected value at $.plannedPhases[].fileReadAllowed: expected false")
            if phase["commandExecutionAllowed"] is not False:
                raise ShapeError("unexpected value at $.plannedPhases[].commandExecutionAllowed: expected false")
    for phase_id in ["track_scope_review", "language_shape_review", "execution_gate_review"]:
        if phase_id not in phase_ids:
            raise ShapeError(f"missing phase id in $.plannedPhases: {phase_id}")

    input_policy = expect_object(require_field(root, "$", "inputPolicy"), "$.inputPolicy")
    require_string_fields(input_policy, "$.inputPolicy", ["acceptedInputKind", "summary"])
    input_false_flags = [
        "pathEchoAllowed",
        "privatePathEchoAllowed",
        "cppSourceReadAllowed",
        "systemVerilogSourceReadAllowed",
        "scriptSourceReadAllowed",
        "grammarReadAllowed",
        "traceReadAllowed",
        "reportReadAllowed",
        "artifactReadAllowed",
        "repositoryReadAllowed",
        "environmentReadAllowed",
        "secretsReadAllowed",
        "tokensReadAllowed",
    ]
    require_bool_fields(input_policy, "$.inputPolicy", input_false_flags)
    for flag in input_false_flags:
        if input_policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.inputPolicy.{flag}: expected false")

    output_policy = expect_object(require_field(root, "$", "outputPolicy"), "$.outputPolicy")
    require_string_fields(output_policy, "$.outputPolicy", ["outputKind", "summary"])
    output_false_flags = [
        "cppSourceIncluded",
        "systemVerilogSourceIncluded",
        "scriptSourceIncluded",
        "grammarIncluded",
        "generatedParserIncluded",
        "compiledArtifactIncluded",
        "runtimePlanIncluded",
        "traceContentIncluded",
        "reportContentIncluded",
        "stdoutIncluded",
        "stderrIncluded",
        "rawLogsIncluded",
        "artifactPathsIncluded",
        "privatePathsIncluded",
    ]
    require_bool_fields(output_policy, "$.outputPolicy", output_false_flags)
    for flag in output_false_flags:
        if output_policy[flag] is not False:
            raise ShapeError(f"unexpected value at $.outputPolicy.{flag}: expected false")

    review = expect_object(require_field(root, "$", "reviewGate"), "$.reviewGate")
    require_string_fields(review, "$.reviewGate", ["state", "summary"])
    review_true_flags = ["approvalRequiredBeforeImplementation", "approvedForDescriptor"]
    review_false_flags = [
        "approvedForSourceRead",
        "approvedForGrammar",
        "approvedForParser",
        "approvedForCompiler",
        "approvedForRuntime",
        "approvedForScriptExecution",
        "approvedForSimulatorExecution",
        "approvedForHardwareControl",
        "approvedForReportWrite",
        "approvedForArtifactWrite",
        "approvedForRepositoryMutation",
    ]
    require_bool_fields(review, "$.reviewGate", review_true_flags + review_false_flags)
    for flag in review_true_flags:
        if review[flag] is not True:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected true")
    for flag in review_false_flags:
        if review[flag] is not False:
            raise ShapeError(f"unexpected value at $.reviewGate.{flag}: expected false")

    mutation = expect_object(require_field(root, "$", "noMutationEvidence"), "$.noMutationEvidence")
    require_string_fields(mutation, "$.noMutationEvidence", ["state", "evidenceRule"])
    mutation_false_flags = [
        "trackedFileMutationAllowed",
        "trackedFileDiffCaptured",
        "cppSourceReadAllowed",
        "systemVerilogSourceReadAllowed",
        "scriptSourceReadAllowed",
        "grammarReadAllowed",
        "reportWriteAllowed",
        "artifactWriteAllowed",
        "repositoryMutationAllowed",
        "commandExecutionAllowed",
        "simulatorExecutionAllowed",
        "hardwareControlAllowed",
        "runtimeExecutionAllowed",
    ]
    require_bool_fields(mutation, "$.noMutationEvidence", mutation_false_flags)
    for flag in mutation_false_flags:
        if mutation[flag] is not False:
            raise ShapeError(f"unexpected value at $.noMutationEvidence.{flag}: expected false")

    blocked = require_field(root, "$", "blockedActions")
    require_string_array(blocked, "$.blockedActions", min_items=1)
    for required in [
        "cpp-source-read",
        "systemverilog-source-read",
        "custom-script-source-read",
        "custom-language-grammar-read",
        "custom-language-parser",
        "custom-language-compiler",
        "custom-script-runtime",
        "custom-script-execution",
        "verification-run",
        "simulator-execution",
        "hardware-control",
        "command-execution",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "public-push",
        "release-or-tag",
    ]:
        if required not in blocked:
            raise ShapeError(f"missing blocked action at $.blockedActions: {required}")

    safety = expect_object(require_field(root, "$", "safetyFlags"), "$.safetyFlags")
    true_flags = ["dataOnly", "descriptorOnly", "readOnly", "planOnly", "summaryOnly"]
    false_flags = [
        "cppSourceReaderImplemented",
        "systemVerilogSourceReaderImplemented",
        "scriptSourceReaderImplemented",
        "customLanguageGrammarIncluded",
        "customLanguageParserImplemented",
        "customLanguageCompilerImplemented",
        "customScriptRuntimeImplemented",
        "customScriptExecution",
        "simulatorExecution",
        "verificationExecution",
        "hardwareControl",
        "commandExecution",
        "shellExecution",
        "runtimeExecution",
        "localFileRead",
        "repositoryRead",
        "rawTraceRead",
        "rawReportRead",
        "readsArtifacts",
        "writesArtifacts",
        "reportReaderImplemented",
        "reportWriterImplemented",
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
        "rawLogsIncluded",
        "telemetry",
        "writeBack",
        "repositoryMutation",
        "publicPush",
        "releaseOrTag",
        "stableApiAbiClaim",
        "runtimeClaim",
        "hardwareClaim",
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
    BoundarySpec("sail-adoption-plan", "docs/examples/sail-adoption-plan.example.json", validate_sail_adoption_plan),
    BoundarySpec("hybrid-strategy-plan", "docs/examples/hybrid-strategy-plan.example.json", validate_hybrid_strategy_plan),
    BoundarySpec("launcher-diagnostics-handoff", "docs/examples/launcher-diagnostics-handoff.example.json", validate_launcher_handoff),
    BoundarySpec("launcher-device-session-status", "docs/examples/launcher-device-session-status.example.json", validate_launcher_device_session_status),
    BoundarySpec("mcp-read-only-tool-plan", "docs/examples/mcp-read-only-tool-plan.example.json", validate_mcp_read_only_tool_plan),
    BoundarySpec("mcp-tool-list", "docs/examples/mcp-tool-list.example.json", validate_mcp_tool_list),
    BoundarySpec("mcp-tool-detail", "docs/examples/mcp-tool-detail.example.json", validate_mcp_tool_detail),
    BoundarySpec("mcp-sample-plan", "docs/examples/mcp-sample-plan.example.json", validate_mcp_sample_plan),
    BoundarySpec("mcp-sample-result", "docs/examples/mcp-sample-result.example.json", validate_mcp_sample_result),
    BoundarySpec("mcp-sample-catalog", "docs/examples/mcp-sample-catalog.example.json", validate_mcp_sample_catalog),
    BoundarySpec("mcp-sample-detail", "docs/examples/mcp-sample-detail.example.json", validate_mcp_sample_detail),
    BoundarySpec("mcp-read-only-analysis-flow", "docs/examples/mcp-read-only-analysis-flow.example.json", validate_mcp_read_only_analysis_flow),
    BoundarySpec("mcp-read-only-report-contract", "docs/examples/mcp-read-only-report-contract.example.json", validate_mcp_read_only_report_contract),
    BoundarySpec("mcp-verification-run-comparison", "docs/examples/mcp-verification-run-comparison.example.json", validate_mcp_verification_run_comparison),
    BoundarySpec("mcp-pr-summary-handoff", "docs/examples/mcp-pr-summary-handoff.example.json", validate_mcp_pr_summary_handoff),
    BoundarySpec("mcp-review-packet", "docs/examples/mcp-review-packet.example.json", validate_mcp_review_packet),
    BoundarySpec("mcp-evidence-manifest", "docs/examples/mcp-evidence-manifest.example.json", validate_mcp_evidence_manifest),
    BoundarySpec("mcp-evidence-detail", "docs/examples/mcp-evidence-detail.example.json", validate_mcp_evidence_detail),
    BoundarySpec("mcp-permission-model", "docs/examples/mcp-permission-model.example.json", validate_mcp_permission_model),
    BoundarySpec("mcp-approval-request", "docs/examples/mcp-approval-request.example.json", validate_mcp_approval_request),
    BoundarySpec("mcp-approval-decision", "docs/examples/mcp-approval-decision.example.json", validate_mcp_approval_decision),
    BoundarySpec("mcp-invocation-request", "docs/examples/mcp-invocation-request.example.json", validate_mcp_invocation_request),
    BoundarySpec("mcp-client-session-state", "docs/examples/mcp-client-session-state.example.json", validate_mcp_client_session_state),
    BoundarySpec("mcp-blocked-invocation-result", "docs/examples/mcp-blocked-invocation-result.example.json", validate_mcp_blocked_invocation_result),
    BoundarySpec("mcp-audit-event", "docs/examples/mcp-audit-event.example.json", validate_mcp_audit_event),
    BoundarySpec("plugin-permission-model", "docs/examples/plugin-permission-model.example.json", validate_plugin_permission_model),
    BoundarySpec("plugin-audit-event", "docs/examples/plugin-audit-event.example.json", validate_plugin_audit_event),
    BoundarySpec("plugin-manifest-validation-result", "docs/examples/plugin-manifest-validation-result.example.json", validate_plugin_manifest_validation_result),
    BoundarySpec("plugin-sample-plan", "docs/examples/plugin-sample-plan.example.json", validate_plugin_sample_plan),
    BoundarySpec("plugin-sample-result", "docs/examples/plugin-sample-result.example.json", validate_plugin_sample_result),
    BoundarySpec("plugin-sample-catalog", "docs/examples/plugin-sample-catalog.example.json", validate_plugin_sample_catalog),
    BoundarySpec("plugin-sample-detail", "docs/examples/plugin-sample-detail.example.json", validate_plugin_sample_detail),
    BoundarySpec("plugin-capability-list", "docs/examples/plugin-capability-list.example.json", validate_plugin_capability_list),
    BoundarySpec("plugin-capability-detail", "docs/examples/plugin-capability-detail.example.json", validate_plugin_capability_detail),
    BoundarySpec("plugin-load-request", "docs/examples/plugin-load-request.example.json", validate_plugin_load_request),
    BoundarySpec("plugin-host-session-state", "docs/examples/plugin-host-session-state.example.json", validate_plugin_host_session_state),
    BoundarySpec("plugin-invocation-request", "docs/examples/plugin-invocation-request.example.json", validate_plugin_invocation_request),
    BoundarySpec("plugin-review-packet", "docs/examples/plugin-review-packet.example.json", validate_plugin_review_packet),
    BoundarySpec("plugin-boundary-plan", "docs/examples/plugin-boundary-plan.example.json", validate_plugin_boundary_plan),
    BoundarySpec("plugin-dry-run-flow", "docs/examples/plugin-dry-run-flow.example.json", validate_plugin_dry_run_flow),
    BoundarySpec("plugin-input-contract", "docs/examples/plugin-input-contract.example.json", validate_plugin_input_contract),
    BoundarySpec("plugin-trace-summary-input", "docs/examples/plugin-trace-summary-input.example.json", validate_plugin_trace_summary_input),
    BoundarySpec("plugin-output-contract", "docs/examples/plugin-output-contract.example.json", validate_plugin_output_contract),
    BoundarySpec("plugin-blocked-invocation-result", "docs/examples/plugin-blocked-invocation-result.example.json", validate_plugin_blocked_invocation_result),
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
