// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 pccxai
// Positive shape tests for documented CLI/core JSON boundary examples.

use std::path::{Path, PathBuf};

use serde::de::DeserializeOwned;

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn read_example(name: &str) -> String {
    let path = repo_root().join("docs/examples").join(name);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()))
}

fn parse_example<T: DeserializeOwned>(name: &str) -> T {
    let text = read_example(name);
    serde_json::from_str(&text)
        .unwrap_or_else(|error| panic!("{name} is not shaped as expected: {error}"))
}

#[test]
fn status_example_deserializes_into_core_contract() {
    let status: pccx_core::LabStatus = parse_example("run-status.example.json");

    assert_eq!(
        status.schema_version,
        pccx_core::status::STATUS_SCHEMA_VERSION
    );
    assert_eq!(status.tool, "pccx-lab");
    assert_eq!(status.workspace_state.trace_loaded, false);
    assert_eq!(status.plugin_state.stable_abi, false);
    assert!(!status.available_workflows.is_empty());
    assert!(!status.limitations.is_empty());
}

#[test]
fn theme_example_deserializes_into_core_contract() {
    let theme: pccx_core::ThemeTokenContract = parse_example("theme-tokens.example.json");

    assert_eq!(theme.schema_version, pccx_core::theme::THEME_SCHEMA_VERSION);
    assert!(!theme.token_slots.is_empty());
    assert!(!theme.presets.is_empty());
    for preset in theme.presets {
        assert!(!preset.name.is_empty());
        assert!(preset.tokens.background.starts_with('#'));
        assert!(preset.tokens.foreground.starts_with('#'));
    }
}

#[test]
fn workflow_descriptor_example_deserializes_into_core_contract() {
    let descriptors: pccx_core::WorkflowDescriptorSet =
        parse_example("workflow-descriptors.example.json");

    assert_eq!(
        descriptors.schema_version,
        pccx_core::workflows::WORKFLOW_DESCRIPTOR_SCHEMA_VERSION
    );
    assert_eq!(descriptors.tool, "pccx-lab");
    assert!(!descriptors.descriptors.is_empty());
    for descriptor in descriptors.descriptors {
        assert!(!descriptor.workflow_id.is_empty());
        assert_eq!(descriptor.execution_state, "descriptor_only");
        assert_eq!(descriptor.evidence_state, "metadata-only");
    }
}

#[test]
fn workflow_proposal_example_deserializes_into_core_contract() {
    let proposals: pccx_core::WorkflowProposalSet =
        parse_example("workflow-proposals.example.json");

    assert_eq!(
        proposals.schema_version,
        pccx_core::proposals::WORKFLOW_PROPOSAL_SCHEMA_VERSION
    );
    assert_eq!(proposals.tool, "pccx-lab");
    assert!(!proposals.proposals.is_empty());
    for proposal in proposals.proposals {
        assert!(!proposal.proposal_id.is_empty());
        assert_eq!(proposal.proposal_state, "proposal_only");
        assert!(proposal.expected_artifacts.is_empty());
    }
}

#[test]
fn workflow_results_example_deserializes_into_core_contract() {
    let results: pccx_core::WorkflowResultSummarySet =
        parse_example("workflow-results.example.json");

    assert_eq!(
        results.schema_version,
        pccx_core::results::WORKFLOW_RESULT_SUMMARY_SCHEMA_VERSION
    );
    assert_eq!(results.tool, "pccx-lab");
    assert!(results.summaries.len() <= results.max_entries);
    assert!(!results.summaries.is_empty());
    for summary in results.summaries {
        assert_eq!(
            summary.schema_version,
            pccx_core::results::WORKFLOW_RESULT_SUMMARY_SCHEMA_VERSION
        );
        assert_eq!(
            summary.output_policy,
            "summary-only; stdout and stderr lines are omitted"
        );
    }
}

#[test]
fn workflow_runner_example_deserializes_into_core_contract() {
    let result: pccx_core::WorkflowRunResult =
        parse_example("workflow-runner-blocked.example.json");

    assert_eq!(
        result.schema_version,
        pccx_core::runner::WORKFLOW_RUNNER_RESULT_SCHEMA_VERSION
    );
    assert_eq!(result.status, "blocked");
    assert_eq!(result.runner_enabled, false);
    assert!(result.stdout_lines.is_empty());
    assert!(result.stderr_lines.is_empty());
}

#[test]
fn diagnostics_envelope_example_keeps_expected_shape() {
    let value: serde_json::Value = parse_example("diagnostics-envelope.example.json");
    let root = value
        .as_object()
        .expect("diagnostics envelope must be an object");

    assert_eq!(root["envelope"], "0");
    assert_eq!(root["tool"], "pccx-lab");
    assert!(root["source"].as_str().is_some());

    let diagnostics = root["diagnostics"]
        .as_array()
        .expect("diagnostics must be an array");
    for item in diagnostics {
        assert!(item["line"].as_u64().is_some());
        assert!(item["column"].as_u64().is_some());
        assert!(item["severity"].as_str().is_some());
        assert!(item["code"].as_str().is_some());
        assert!(item["message"].as_str().is_some());
        assert!(item["source"].as_str().is_some());
    }
}

#[test]
fn launcher_handoff_example_validates_through_core_reader() {
    let text = read_example("launcher-diagnostics-handoff.example.json");
    let summary = pccx_core::validate_diagnostics_handoff_json(&text)
        .expect("launcher diagnostics handoff example must validate");

    assert_eq!(
        summary.schema_version,
        pccx_core::HANDOFF_VALIDATION_SCHEMA_VERSION
    );
    assert_eq!(
        summary.handoff_schema_version,
        pccx_core::LAUNCHER_HANDOFF_SCHEMA_VERSION
    );
    assert!(summary.valid);
    assert!(summary.read_only_flags.no_launcher_execution);
    assert!(summary.read_only_flags.no_pccx_lab_execution);
}

#[test]
fn launcher_device_session_status_example_validates_through_core_reader() {
    let text = read_example("launcher-device-session-status.example.json");
    let summary = pccx_core::validate_device_session_status_json(&text)
        .expect("launcher device/session status example must validate");

    assert_eq!(
        summary.schema_version,
        pccx_core::DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION
    );
    assert_eq!(
        summary.status_schema_version,
        pccx_core::LAUNCHER_DEVICE_SESSION_STATUS_SCHEMA_VERSION
    );
    assert!(summary.valid);
    assert_eq!(summary.target_device, "kv260");
    assert_eq!(
        summary.status_panel_rows["device_connection"],
        "not_configured"
    );
    assert_eq!(summary.status_panel_rows["runtime_readiness"], "blocked");
    assert!(summary.read_only_flags.no_runtime_execution);
    assert!(summary.read_only_flags.no_pccx_lab_execution);
}

#[test]
fn mcp_read_only_tool_plan_example_keeps_descriptor_only_safety_boundary() {
    let value: serde_json::Value = parse_example("mcp-read-only-tool-plan.example.json");
    let root = value
        .as_object()
        .expect("MCP read-only tool plan must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-read-only-tool-plan.v0");
    assert_eq!(root["planState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");

    let tools = root["toolList"]
        .as_array()
        .expect("tool list must be an array");
    assert!(!tools.is_empty());
    for tool in tools {
        assert_eq!(tool["readOnly"], true);
        assert!(tool["fixedArgsPreview"].as_array().is_some());
    }

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn mcp_read_only_analysis_flow_example_keeps_dry_run_boundary() {
    let value: serde_json::Value = parse_example("mcp-read-only-analysis-flow.example.json");
    let root = value
        .as_object()
        .expect("MCP read-only analysis flow must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.mcp-read-only-analysis-flow.v0"
    );
    assert_eq!(root["flowState"], "dry_run_contract");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let steps = root["flowSteps"]
        .as_array()
        .expect("flow steps must be an array");
    assert!(
        steps.len() >= 4,
        "read-only flow should cover status, descriptors, proposals, and results"
    );
    for step in steps {
        assert_eq!(step["approvalRequired"], false);
        assert!(step["fixedArgsPreview"].as_array().is_some());
        assert_ne!(
            step["sideEffectPolicy"], "artifact write",
            "flow step must not advertise artifact writes"
        );
    }

    let report = root["reportPrototype"]
        .as_object()
        .expect("report prototype must be an object");
    assert_eq!(report["reportState"], "summary_only_fixture");
    assert_eq!(report["trackedFileMutation"], false);
    assert_eq!(report["artifactWrite"], false);
    assert_eq!(report["pathEchoAllowed"], false);
    assert_eq!(report["stdoutIncluded"], false);
    assert_eq!(report["stderrIncluded"], false);
    assert_eq!(report["rawLogIncluded"], false);
    assert_eq!(report["privatePathsIncluded"], false);

    let validation = root["validationPolicy"]
        .as_object()
        .expect("validation policy must be an object");
    assert_eq!(validation["commandExecutionByFixture"], false);
    assert_eq!(validation["trackedFileMutationAllowed"], false);
    assert_eq!(validation["artifactWriteAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
        "mcp-server-start",
        "mcp-client-session",
        "arbitrary-shell-command",
        "artifact-write",
        "repository-write-back",
        "public-push",
        "release-or-tag",
        "provider-call",
        "network-call",
        "hardware-probe",
        "runtime-launch",
        "model-load",
    ] {
        assert!(
            blocked.iter().any(|item| item == action),
            "blockedActions must include {action}"
        );
    }

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["flowPrototypeOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn mcp_permission_model_example_keeps_permission_boundary_non_executing() {
    let value: serde_json::Value = parse_example("mcp-permission-model.example.json");
    let root = value
        .as_object()
        .expect("MCP permission model must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-permission-model.v0");
    assert_eq!(root["modelState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let approval = root["approvalPolicy"]
        .as_object()
        .expect("approval policy must be an object");
    assert_eq!(approval["userApprovalRequiredForPathInput"], true);
    assert_eq!(approval["userApprovalRequiredForWriteAction"], true);
    assert_eq!(approval["userApprovalRequiredForArtifactOutput"], true);
    assert_eq!(approval["rawShellCommandsAllowed"], false);
    assert_eq!(approval["silentFallbackAllowed"], false);
    assert_eq!(approval["backgroundMutationAllowed"], false);

    let profiles = root["permissionProfiles"]
        .as_array()
        .expect("permission profiles must be an array");
    assert!(profiles.iter().any(|profile| {
        profile["profileId"] == "read_only_no_input"
            && profile["requiresUserApproval"] == false
            && profile["auditRequired"] == true
    }));
    assert!(profiles.iter().any(|profile| {
        profile["profileId"] == "read_only_approved_local_file"
            && profile["requiresUserApproval"] == true
            && profile["auditRequired"] == true
    }));
    assert!(profiles.iter().any(|profile| {
        profile["profileId"] == "write_action_pending_review"
            && profile["profileState"] == "deferred"
            && profile["allowedCommandKinds"]
                .as_array()
                .unwrap()
                .is_empty()
    }));

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    ] {
        assert!(
            blocked.iter().any(|item| item == action),
            "blockedActions must include {action}"
        );
    }

    let audit = root["auditPolicy"]
        .as_object()
        .expect("audit policy must be an object");
    assert_eq!(audit["auditRequiredForAllowedProfiles"], true);
    assert_eq!(audit["redactionRequired"], true);
    assert_eq!(audit["pathEchoAllowed"], false);
    assert_eq!(audit["stdoutCaptureAllowed"], false);
    assert_eq!(audit["stderrCaptureAllowed"], false);

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn mcp_audit_event_example_keeps_redacted_read_only_boundary() {
    let value: serde_json::Value = parse_example("mcp-audit-event.example.json");
    let root = value
        .as_object()
        .expect("MCP audit event example must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-audit-event.v0");
    assert_eq!(root["eventState"], "example_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["outcomeState"], "not_executed");
    assert_eq!(root["toolId"], "lab.status.read");

    let args = root["fixedArgsPreview"]
        .as_array()
        .expect("fixed args preview must be an array");
    assert_eq!(args[0], "status");
    assert_eq!(args[1], "--format");
    assert_eq!(args[2], "json");

    let validation = root["validationSummary"]
        .as_object()
        .expect("validation summary must be an object");
    assert_eq!(validation["summaryOnly"], true);
    assert_eq!(validation["pathEchoed"], false);
    assert_eq!(validation["stdoutCaptured"], false);
    assert_eq!(validation["stderrCaptured"], false);
    assert_eq!(validation["artifactWritten"], false);

    let redaction = root["redactionState"]
        .as_object()
        .expect("redaction state must be an object");
    assert_eq!(redaction["privatePathsIncluded"], false);
    assert_eq!(redaction["secretsIncluded"], false);
    assert_eq!(redaction["tokensIncluded"], false);
    assert_eq!(redaction["modelWeightPathsIncluded"], false);
    assert_eq!(redaction["stdoutIncluded"], false);
    assert_eq!(redaction["stderrIncluded"], false);

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn plugin_boundary_plan_example_keeps_manifest_only_safety_boundary() {
    let value: serde_json::Value = parse_example("plugin-boundary-plan.example.json");
    let root = value
        .as_object()
        .expect("plugin boundary plan must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-boundary-plan.v0");
    assert_eq!(root["planState"], "descriptor_only");
    assert_eq!(root["hostMode"], "cli_first_gui_second");

    let manifest = root["manifestDraft"]
        .as_object()
        .expect("manifest draft must be an object");
    assert_eq!(manifest["manifestState"], "draft");

    let loading = root["loadingBoundary"]
        .as_object()
        .expect("loading boundary must be an object");
    assert_eq!(loading["state"], "not_implemented");
    assert_eq!(loading["pluginCodeLoaded"], false);
    assert_eq!(loading["dynamicLibrariesLoaded"], false);
    assert_eq!(loading["untrustedExecutionAllowed"], false);
    assert_eq!(loading["hostApiStable"], false);

    let sample = root["samplePluginPlan"]
        .as_object()
        .expect("sample plugin plan must be an object");
    assert_eq!(sample["executionState"], "not_implemented");

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["untrustedExecutionAllowed"], false);
    assert_eq!(safety["stablePluginAbiPromised"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn plugin_dry_run_flow_example_keeps_loader_disabled_boundary() {
    let value: serde_json::Value = parse_example("plugin-dry-run-flow.example.json");
    let root = value
        .as_object()
        .expect("plugin dry-run flow must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-dry-run-flow.v0");
    assert_eq!(root["flowState"], "dry_run_contract");
    assert_eq!(root["pluginRuntimeState"], "not_implemented");
    assert_eq!(root["loaderState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");
    assert_eq!(root["hostMode"], "cli_first_gui_second");

    let sample = root["samplePluginRef"]
        .as_object()
        .expect("sample plugin ref must be an object");
    assert_eq!(sample["manifestState"], "example_manifest_only");
    assert_eq!(sample["entryKind"], "manifest_only");
    assert_eq!(sample["codeLoaded"], false);
    assert_eq!(sample["packageInstalled"], false);
    assert_eq!(sample["dynamicLibrariesLoaded"], false);

    let steps = root["flowSteps"]
        .as_array()
        .expect("flow steps must be an array");
    assert!(
        steps.len() >= 4,
        "plugin dry-run flow should cover manifest, capability, diagnostics, and report-panel review"
    );
    for step in steps {
        assert_eq!(step["approvalRequired"], true);
        assert!(step["fixedArgsPreview"].as_array().is_some());
        assert_eq!(step["artifactWrite"], false);
        assert_eq!(step["repositoryMutation"], false);
    }

    let output = root["outputPrototype"]
        .as_object()
        .expect("output prototype must be an object");
    assert_eq!(output["outputState"], "summary_only_fixture");
    assert_eq!(output["trackedFileMutation"], false);
    assert_eq!(output["artifactWrite"], false);
    assert_eq!(output["pathEchoAllowed"], false);
    assert_eq!(output["stdoutIncluded"], false);
    assert_eq!(output["stderrIncluded"], false);
    assert_eq!(output["rawLogIncluded"], false);
    assert_eq!(output["privatePathsIncluded"], false);

    let validation = root["validationPolicy"]
        .as_object()
        .expect("validation policy must be an object");
    assert_eq!(validation["commandExecutionByFixture"], false);
    assert_eq!(validation["trackedFileMutationAllowed"], false);
    assert_eq!(validation["artifactWriteAllowed"], false);
    assert_eq!(validation["pluginCodeLoadAllowed"], false);
    assert_eq!(validation["localInputRequiresApproval"], true);
    assert_eq!(validation["manifestApprovalRequired"], true);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    ] {
        assert!(
            blocked.iter().any(|item| item == action),
            "blockedActions must include {action}"
        );
    }

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["dryRunOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["sandboxImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["stablePluginAbiPromised"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn plugin_output_contract_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("plugin-output-contract.example.json");
    let root = value
        .as_object()
        .expect("plugin output contract must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-output-contract.v0");
    assert_eq!(root["contractState"], "descriptor_only");
    assert_eq!(root["pluginRuntimeState"], "not_implemented");
    assert_eq!(root["loaderState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");

    let sample = root["samplePluginRef"]
        .as_object()
        .expect("sample plugin ref must be an object");
    assert_eq!(sample["entryKind"], "manifest_only");
    assert_eq!(sample["codeLoaded"], false);
    assert_eq!(sample["packageInstalled"], false);
    assert_eq!(sample["dynamicLibrariesLoaded"], false);

    let inputs = root["inputBoundaryRefs"]
        .as_array()
        .expect("input boundary refs must be an array");
    assert!(inputs.iter().any(|input| {
        input["refId"] == "diagnostics_envelope" && input["pathEchoAllowed"] == false
    }));
    assert!(inputs.iter().any(|input| {
        input["refId"] == "workflow_results" && input["pathEchoAllowed"] == false
    }));

    let outputs = root["outputContracts"]
        .as_array()
        .expect("output contracts must be an array");
    assert!(
        outputs.len() >= 3,
        "output contract should cover diagnostic, panel, and report item previews"
    );
    for output in outputs {
        assert_eq!(output["summaryOnly"], true);
        assert_eq!(output["artifactWrite"], false);
        assert_eq!(output["repositoryMutation"], false);
        assert_eq!(output["privatePathEchoAllowed"], false);
        assert_eq!(output["stdoutIncluded"], false);
        assert_eq!(output["stderrIncluded"], false);
        assert_eq!(output["rawLogIncluded"], false);
    }

    let sample_output = root["sampleOutput"]
        .as_object()
        .expect("sample output must be an object");
    let diagnostics = sample_output["diagnosticSummaryItems"]
        .as_array()
        .expect("diagnostic summary items must be an array");
    assert!(diagnostics.iter().all(|item| item["pathIncluded"] == false));
    let panels = sample_output["reportPanelItems"]
        .as_array()
        .expect("report panel items must be an array");
    assert!(panels
        .iter()
        .all(|item| item["artifactWrite"] == false && item["pathIncluded"] == false));
    let reports = sample_output["reportItems"]
        .as_array()
        .expect("report items must be an array");
    assert!(reports.iter().all(|item| {
        item["artifactWrite"] == false
            && item["generatedArtifact"] == false
            && item["pathIncluded"] == false
    }));

    let policy = root["outputPolicy"]
        .as_object()
        .expect("output policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequiredForInputs"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["trackedFileMutationAllowed"], false);
    assert_eq!(policy["artifactWriteAllowed"], false);
    assert_eq!(policy["pathEchoAllowed"], false);
    assert_eq!(policy["stdoutAllowed"], false);
    assert_eq!(policy["stderrAllowed"], false);
    assert_eq!(policy["rawLogAllowed"], false);
    assert_eq!(policy["privatePathsAllowed"], false);
    assert_eq!(policy["generatedArtifactsAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    ] {
        assert!(
            blocked.iter().any(|item| item == action),
            "blockedActions must include {action}"
        );
    }

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["outputFixtureOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["sandboxImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["stablePluginAbiPromised"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn plugin_permission_model_example_keeps_permission_boundary_non_executing() {
    let value: serde_json::Value = parse_example("plugin-permission-model.example.json");
    let root = value
        .as_object()
        .expect("plugin permission model must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-permission-model.v0");
    assert_eq!(root["modelState"], "descriptor_only");
    assert_eq!(root["pluginRuntimeState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");

    let approval = root["approvalPolicy"]
        .as_object()
        .expect("approval policy must be an object");
    assert_eq!(approval["manifestApprovalRequired"], true);
    assert_eq!(approval["localInputApprovalRequired"], true);
    assert_eq!(approval["capabilityEscalationRequiresReview"], true);
    assert_eq!(approval["artifactOutputRequiresReview"], true);
    assert_eq!(approval["rawShellCommandsAllowed"], false);
    assert_eq!(approval["silentFallbackAllowed"], false);
    assert_eq!(approval["backgroundMutationAllowed"], false);
    assert_eq!(approval["unreviewedCapabilityAllowed"], false);

    let sandbox = root["sandboxPolicy"]
        .as_object()
        .expect("sandbox policy must be an object");
    assert_eq!(sandbox["sandboxRequiredBeforeExecution"], true);
    assert_eq!(sandbox["processIsolationRequired"], true);
    assert_eq!(sandbox["networkDisabledByDefault"], true);
    assert_eq!(sandbox["filesystemWriteDisabledByDefault"], true);
    assert_eq!(sandbox["dynamicLibraryLoadAllowed"], false);
    assert_eq!(sandbox["untrustedExecutionAllowed"], false);

    let profiles = root["permissionProfiles"]
        .as_array()
        .expect("permission profiles must be an array");
    assert!(profiles.iter().any(|profile| {
        profile["profileId"] == "manifest_review_read_only"
            && profile["requiresUserApproval"] == true
            && profile["auditRequired"] == true
    }));
    assert!(profiles.iter().any(|profile| {
        profile["profileId"] == "diagnostics_summary_read_only"
            && profile["profileState"] == "planned"
            && profile["auditRequired"] == true
    }));
    assert!(profiles.iter().any(|profile| {
        profile["profileId"] == "trace_import_pending_review"
            && profile["profileState"] == "deferred"
            && profile["allowedCapabilityIds"]
                .as_array()
                .unwrap()
                .is_empty()
    }));
    assert!(profiles.iter().any(|profile| {
        profile["profileId"] == "write_action_pending_review"
            && profile["profileState"] == "deferred"
            && profile["allowedOutputContracts"]
                .as_array()
                .unwrap()
                .is_empty()
    }));

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    ] {
        assert!(
            blocked.iter().any(|item| item == action),
            "blockedActions must include {action}"
        );
    }

    let audit = root["auditPolicy"]
        .as_object()
        .expect("audit policy must be an object");
    assert_eq!(audit["auditRequiredForAllowedProfiles"], true);
    assert_eq!(audit["redactionRequired"], true);
    assert_eq!(audit["privatePathEchoAllowed"], false);
    assert_eq!(audit["stdoutCaptureAllowed"], false);
    assert_eq!(audit["stderrCaptureAllowed"], false);
    assert_eq!(audit["artifactPathEchoAllowed"], false);

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["untrustedExecutionAllowed"], false);
    assert_eq!(safety["sandboxImplemented"], false);
    assert_eq!(safety["stablePluginAbiPromised"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}
