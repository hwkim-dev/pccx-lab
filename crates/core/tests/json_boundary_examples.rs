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
fn mcp_tool_list_example_keeps_descriptor_only_listing_boundary() {
    let value: serde_json::Value = parse_example("mcp-tool-list.example.json");
    let root = value.as_object().expect("MCP tool list must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-tool-list.v0");
    assert_eq!(root["listState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "mcp_read_only_tool_plan"
            && source["toolPlanAvailable"] == true
            && source["commandExecutorAllowed"] == false
            && source["toolInvocationAllowed"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "mcp_permission_model"
            && source["permissionExecutorAllowed"] == false
            && source["approvalExecutorAllowed"] == false
            && source["toolInvocationAllowed"] == false
    }));

    let request = root["toolListRequest"]
        .as_object()
        .expect("tool-list request must be an object");
    assert_eq!(request["requestKind"], "planned_mcp_tool_listing");
    assert_eq!(request["summaryOnly"], true);
    assert_eq!(request["inputRefOnly"], true);
    assert_eq!(request["pathEchoAllowed"], false);
    assert_eq!(request["localFileReadAllowed"], false);
    assert_eq!(request["repositoryReadAllowed"], false);
    assert_eq!(request["artifactReadAllowed"], false);
    assert_eq!(request["artifactWriteAllowed"], false);
    assert_eq!(request["reportWriteAllowed"], false);
    assert_eq!(request["commandExecutionAllowed"], false);
    assert_eq!(request["runtimeExecutionAllowed"], false);
    assert_eq!(request["mcpServerAllowed"], false);
    assert_eq!(request["mcpClientAllowed"], false);
    assert_eq!(request["mcpRuntimeAllowed"], false);
    assert_eq!(request["mcpTransportAllowed"], false);
    assert_eq!(request["permissionExecutorAllowed"], false);
    assert_eq!(request["approvalExecutorAllowed"], false);
    assert_eq!(request["auditLoggerAllowed"], false);
    assert_eq!(request["toolInvocationAllowed"], false);
    assert_eq!(request["stableApiAbiClaim"], false);
    assert_eq!(request["marketplaceClaim"], false);

    let tools = root["tools"].as_array().expect("tools must be an array");
    assert!(tools.iter().any(|tool| {
        tool["toolId"] == "lab.status.read"
            && tool["approvedForListing"] == true
            && tool["requiresSeparateInvocationBoundary"] == true
            && tool["approvedForInvocation"] == false
            && tool["toolInvocationAllowed"] == false
    }));
    assert!(tools.iter().any(|tool| {
        tool["toolId"] == "lab.fileShapeDiagnostics.analyze"
            && tool["approvedForListing"] == true
            && tool["approvedForInvocation"] == false
            && tool["localFileReadAllowed"] == false
    }));

    let deferred = root["deferredTools"]
        .as_array()
        .expect("deferred tools must be an array");
    assert!(deferred.iter().any(|tool| {
        tool["toolId"] == "lab.report.generate"
            && tool["approvedForListing"] == true
            && tool["approvedForInvocation"] == false
            && tool["toolInvocationAllowed"] == false
    }));

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["localFileReadAllowed"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["toolInvocationAllowed"], false);
    assert_eq!(mutation["commandExecutionAllowed"], false);
    assert_eq!(mutation["repositoryMutationAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
        "mcp-server-start",
        "mcp-client-start",
        "mcp-transport-start",
        "tool-invocation",
        "command-execution",
        "local-file-read",
        "artifact-read",
        "report-write",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
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
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["toolListFixtureOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["mcpTransportImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["toolInvocationAttempted"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["approvalExecutorImplemented"], false);
    assert_eq!(safety["auditLoggerImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
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
fn mcp_read_only_report_contract_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("mcp-read-only-report-contract.example.json");
    let root = value
        .as_object()
        .expect("MCP read-only report contract must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.mcp-read-only-report-contract.v0"
    );
    assert_eq!(root["contractState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let sections = root["reportSections"]
        .as_array()
        .expect("report sections must be an array");
    assert!(
        sections.len() >= 4,
        "report contract should cover status, descriptors, proposals, and results"
    );
    for section in sections {
        assert_eq!(section["summaryOnly"], true);
        assert_eq!(section["artifactWrite"], false);
        assert_eq!(section["repositoryMutation"], false);
        assert_eq!(section["privatePathEchoAllowed"], false);
        assert_eq!(section["stdoutIncluded"], false);
        assert_eq!(section["stderrIncluded"], false);
        assert_eq!(section["rawLogIncluded"], false);
    }

    let report = root["sampleReport"]
        .as_object()
        .expect("sample report must be an object");
    assert_eq!(report["reportState"], "summary_only_fixture");
    assert_eq!(report["trackedFileMutation"], false);
    assert_eq!(report["artifactWrite"], false);
    assert_eq!(report["pathEchoAllowed"], false);
    assert_eq!(report["stdoutIncluded"], false);
    assert_eq!(report["stderrIncluded"], false);
    assert_eq!(report["rawLogIncluded"], false);
    assert_eq!(report["privatePathsIncluded"], false);
    assert_eq!(report["generatedArtifactsIncluded"], false);

    let sample_sections = report["sections"]
        .as_array()
        .expect("sample report sections must be an array");
    assert!(sample_sections
        .iter()
        .all(|section| section["pathIncluded"] == false && section["artifactWrite"] == false));

    let policy = root["outputPolicy"]
        .as_object()
        .expect("output policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequiredForPathInputs"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["commandExecutionByFixture"], false);
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
    assert_eq!(safety["reportFixtureOnly"], true);
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
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn mcp_verification_run_comparison_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("mcp-verification-run-comparison.example.json");
    let root = value
        .as_object()
        .expect("MCP verification-run comparison must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.mcp-verification-run-comparison.v0"
    );
    assert_eq!(root["comparisonState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let sources = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(sources.iter().any(|source| {
        source["refId"] == "workflow_results" && source["pathEchoAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "mcp_read_only_report_contract"
            && source["artifactWriteAllowed"] == false
    }));

    let inputs = root["comparisonInputs"]
        .as_array()
        .expect("comparison inputs must be an array");
    assert!(
        inputs.len() >= 2,
        "comparison boundary should include baseline and candidate summaries"
    );
    for input in inputs {
        assert_eq!(input["inputKind"], "workflow_result_summary");
        assert_eq!(input["inputState"], "approved_summary_only");
        assert_eq!(input["summaryOnly"], true);
        assert_eq!(input["approvalRequired"], true);
        assert_eq!(input["localFileRead"], false);
        assert_eq!(input["rawTraceRead"], false);
        assert_eq!(input["rawReportRead"], false);
        assert_eq!(input["artifactRead"], false);
        assert_eq!(input["privatePathEchoAllowed"], false);
        assert_eq!(input["stdoutIncluded"], false);
        assert_eq!(input["stderrIncluded"], false);
        assert_eq!(input["rawLogIncluded"], false);
        assert_eq!(input["artifactPathIncluded"], false);
    }

    let policy = root["comparisonPolicy"]
        .as_object()
        .expect("comparison policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequired"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["commandExecutionAllowed"], false);
    assert_eq!(policy["localFileReadAllowed"], false);
    assert_eq!(policy["rawTraceReadAllowed"], false);
    assert_eq!(policy["rawReportReadAllowed"], false);
    assert_eq!(policy["artifactReadAllowed"], false);
    assert_eq!(policy["artifactWriteAllowed"], false);
    assert_eq!(policy["reportWriteAllowed"], false);
    assert_eq!(policy["repositoryMutationAllowed"], false);
    assert_eq!(policy["pathEchoAllowed"], false);
    assert_eq!(policy["stdoutAllowed"], false);
    assert_eq!(policy["stderrAllowed"], false);
    assert_eq!(policy["rawLogAllowed"], false);
    assert_eq!(policy["privatePathsAllowed"], false);
    assert_eq!(policy["generatedArtifactsAllowed"], false);

    let comparison = root["sampleComparison"]
        .as_object()
        .expect("sample comparison must be an object");
    assert_eq!(comparison["comparisonState"], "summary_only_fixture");
    assert_eq!(comparison["summaryOnly"], true);
    assert_eq!(comparison["pathIncluded"], false);
    assert_eq!(comparison["privatePathsIncluded"], false);
    assert_eq!(comparison["stdoutIncluded"], false);
    assert_eq!(comparison["stderrIncluded"], false);
    assert_eq!(comparison["rawLogsIncluded"], false);
    assert_eq!(comparison["artifactPathsIncluded"], false);
    assert_eq!(comparison["generatedArtifactsIncluded"], false);
    assert_eq!(comparison["rawTraceIncluded"], false);
    assert_eq!(comparison["rawReportIncluded"], false);

    let runs = comparison["runs"]
        .as_array()
        .expect("sample comparison runs must be an array");
    assert!(runs.iter().all(|run| {
        run["pathIncluded"] == false
            && run["artifactPathIncluded"] == false
            && run["stdoutIncluded"] == false
            && run["stderrIncluded"] == false
            && run["rawLogsIncluded"] == false
    }));

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["trackedFileDiffCaptured"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["reportWriteAllowed"], false);
    assert_eq!(mutation["repositoryMutationAllowed"], false);
    assert_eq!(mutation["publicPushAllowed"], false);
    assert_eq!(mutation["releaseOrTagAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["comparisonFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["reportWriterImplemented"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["artifactPathsIncluded"], false);
    assert_eq!(safety["generatedArtifactsIncluded"], false);
    assert_eq!(safety["telemetry"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
}

#[test]
fn mcp_pr_summary_handoff_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("mcp-pr-summary-handoff.example.json");
    let root = value
        .as_object()
        .expect("MCP PR summary handoff must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-pr-summary-handoff.v0");
    assert_eq!(root["handoffState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");
    assert_eq!(root["handoffKind"], "pr_summary_packet");

    let sources = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(sources.iter().any(|source| {
        source["refId"] == "workflow_results"
            && source["pathEchoAllowed"] == false
            && source["artifactWriteAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "mcp_verification_run_comparison"
            && source["rawReportAllowed"] == false
            && source["artifactWriteAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "mcp_permission_model" && source["writeActionAllowed"] == false
    }));

    let inputs = root["handoffInputs"]
        .as_array()
        .expect("handoff inputs must be an array");
    assert!(
        inputs.len() >= 3,
        "PR handoff boundary should include issue, change, and validation summaries"
    );
    for input in inputs {
        assert_eq!(input["inputState"], "approved_summary_only");
        assert_eq!(input["summaryOnly"], true);
        assert_eq!(input["approvalRequired"], true);
        assert_eq!(input["localFileRead"], false);
        assert_eq!(input["repositoryRead"], false);
        assert_eq!(input["rawTraceRead"], false);
        assert_eq!(input["rawReportRead"], false);
        assert_eq!(input["artifactRead"], false);
        assert_eq!(input["privatePathEchoAllowed"], false);
        assert_eq!(input["stdoutIncluded"], false);
        assert_eq!(input["stderrIncluded"], false);
        assert_eq!(input["rawLogIncluded"], false);
        assert_eq!(input["artifactPathIncluded"], false);
        assert!(input["fieldDescriptors"].as_array().is_some());
    }

    let policy = root["handoffPolicy"]
        .as_object()
        .expect("handoff policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequired"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["commandExecutionAllowed"], false);
    assert_eq!(policy["localFileReadAllowed"], false);
    assert_eq!(policy["repositoryReadAllowed"], false);
    assert_eq!(policy["rawTraceReadAllowed"], false);
    assert_eq!(policy["rawReportReadAllowed"], false);
    assert_eq!(policy["artifactReadAllowed"], false);
    assert_eq!(policy["artifactWriteAllowed"], false);
    assert_eq!(policy["reportWriteAllowed"], false);
    assert_eq!(policy["repositoryMutationAllowed"], false);
    assert_eq!(policy["publicPushAllowed"], false);
    assert_eq!(policy["releaseOrTagAllowed"], false);
    assert_eq!(policy["prCreationAllowed"], false);
    assert_eq!(policy["prCommentAllowed"], false);
    assert_eq!(policy["issueCommentAllowed"], false);
    assert_eq!(policy["projectMutationAllowed"], false);
    assert_eq!(policy["publicTextPublicationAllowed"], false);
    assert_eq!(policy["pathEchoAllowed"], false);
    assert_eq!(policy["stdoutAllowed"], false);
    assert_eq!(policy["stderrAllowed"], false);
    assert_eq!(policy["rawLogAllowed"], false);
    assert_eq!(policy["privatePathsAllowed"], false);
    assert_eq!(policy["generatedArtifactsAllowed"], false);

    let handoff = root["sampleHandoff"]
        .as_object()
        .expect("sample handoff must be an object");
    assert_eq!(handoff["handoffState"], "summary_only_fixture");
    assert_eq!(handoff["summaryOnly"], true);
    assert_eq!(handoff["pathIncluded"], false);
    assert_eq!(handoff["privatePathsIncluded"], false);
    assert_eq!(handoff["stdoutIncluded"], false);
    assert_eq!(handoff["stderrIncluded"], false);
    assert_eq!(handoff["rawLogsIncluded"], false);
    assert_eq!(handoff["artifactPathsIncluded"], false);
    assert_eq!(handoff["generatedArtifactsIncluded"], false);
    assert_eq!(handoff["rawTraceIncluded"], false);
    assert_eq!(handoff["rawReportIncluded"], false);
    assert_eq!(handoff["prCreated"], false);
    assert_eq!(handoff["prCommentCreated"], false);
    assert_eq!(handoff["issueCommentCreated"], false);
    assert_eq!(handoff["projectUpdated"], false);
    assert_eq!(handoff["publicTextPublished"], false);

    let sections = handoff["bodySections"]
        .as_array()
        .expect("sample handoff body sections must be an array");
    assert!(sections.iter().all(|section| {
        section["summaryOnly"] == true
            && section["pathIncluded"] == false
            && section["stdoutIncluded"] == false
            && section["stderrIncluded"] == false
            && section["rawLogsIncluded"] == false
            && section["rawTraceIncluded"] == false
            && section["rawReportIncluded"] == false
    }));

    let checklist = handoff["checklistItems"]
        .as_array()
        .expect("sample handoff checklist items must be an array");
    assert!(checklist.iter().all(|item| {
        item["summaryOnly"] == true
            && item["commandIncluded"] == false
            && item["pathIncluded"] == false
            && item["artifactPathIncluded"] == false
    }));

    let validation_lines = handoff["validationLines"]
        .as_array()
        .expect("sample handoff validation lines must be an array");
    assert!(validation_lines.iter().all(|line| {
        line["summaryOnly"] == true
            && line["commandIncluded"] == false
            && line["stdoutIncluded"] == false
            && line["stderrIncluded"] == false
            && line["rawLogsIncluded"] == false
            && line["artifactPathIncluded"] == false
    }));

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["trackedFileDiffCaptured"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["reportWriteAllowed"], false);
    assert_eq!(mutation["repositoryMutationAllowed"], false);
    assert_eq!(mutation["publicPushAllowed"], false);
    assert_eq!(mutation["releaseOrTagAllowed"], false);
    assert_eq!(mutation["prCreationAllowed"], false);
    assert_eq!(mutation["prCommentAllowed"], false);
    assert_eq!(mutation["issueCommentAllowed"], false);
    assert_eq!(mutation["projectMutationAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["handoffFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["reportWriterImplemented"], false);
    assert_eq!(safety["prCreation"], false);
    assert_eq!(safety["prComment"], false);
    assert_eq!(safety["issueComment"], false);
    assert_eq!(safety["projectMutation"], false);
    assert_eq!(safety["publicTextPublication"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["artifactPathsIncluded"], false);
    assert_eq!(safety["generatedArtifactsIncluded"], false);
    assert_eq!(safety["telemetry"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
}

#[test]
fn mcp_review_packet_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("mcp-review-packet.example.json");
    let root = value
        .as_object()
        .expect("MCP review packet must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-review-packet.v0");
    assert_eq!(root["reviewState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");
    assert_eq!(root["packetKind"], "summary_only_review_packet");

    let sources = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(sources.iter().any(|source| {
        source["refId"] == "mcp_permission_model"
            && source["writeActionAllowed"] == false
            && source["toolInvocationAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "mcp_blocked_invocation_result"
            && source["commandExecutionAllowed"] == false
            && source["toolInvocationAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "mcp_pr_summary_handoff"
            && source["publicTextPublicationAllowed"] == false
            && source["artifactWriteAllowed"] == false
    }));

    let inputs = root["reviewInputs"]
        .as_array()
        .expect("review inputs must be an array");
    assert!(
        inputs.len() >= 5,
        "review packet boundary should include permission, approval, blocked result, validation, and handoff summaries"
    );
    for input in inputs {
        assert_eq!(input["inputState"], "approved_summary_only");
        assert_eq!(input["summaryOnly"], true);
        assert_eq!(input["approvalRequired"], true);
        assert_eq!(input["localFileRead"], false);
        assert_eq!(input["repositoryRead"], false);
        assert_eq!(input["rawTraceRead"], false);
        assert_eq!(input["rawReportRead"], false);
        assert_eq!(input["artifactRead"], false);
        assert_eq!(input["privatePathEchoAllowed"], false);
        assert_eq!(input["stdoutIncluded"], false);
        assert_eq!(input["stderrIncluded"], false);
        assert_eq!(input["rawLogIncluded"], false);
        assert_eq!(input["artifactPathIncluded"], false);
        assert!(input["fieldDescriptors"].as_array().is_some());
    }

    let policy = root["reviewPolicy"]
        .as_object()
        .expect("review policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequired"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["commandExecutionAllowed"], false);
    assert_eq!(policy["localFileReadAllowed"], false);
    assert_eq!(policy["repositoryReadAllowed"], false);
    assert_eq!(policy["rawTraceReadAllowed"], false);
    assert_eq!(policy["rawReportReadAllowed"], false);
    assert_eq!(policy["artifactReadAllowed"], false);
    assert_eq!(policy["artifactWriteAllowed"], false);
    assert_eq!(policy["reportWriteAllowed"], false);
    assert_eq!(policy["repositoryMutationAllowed"], false);
    assert_eq!(policy["publicPushAllowed"], false);
    assert_eq!(policy["releaseOrTagAllowed"], false);
    assert_eq!(policy["prCreationAllowed"], false);
    assert_eq!(policy["prCommentAllowed"], false);
    assert_eq!(policy["issueCommentAllowed"], false);
    assert_eq!(policy["projectMutationAllowed"], false);
    assert_eq!(policy["publicTextPublicationAllowed"], false);
    assert_eq!(policy["toolInvocationAllowed"], false);
    assert_eq!(policy["permissionExecutionAllowed"], false);
    assert_eq!(policy["approvalExecutionAllowed"], false);
    assert_eq!(policy["pathEchoAllowed"], false);
    assert_eq!(policy["stdoutAllowed"], false);
    assert_eq!(policy["stderrAllowed"], false);
    assert_eq!(policy["rawLogAllowed"], false);
    assert_eq!(policy["privatePathsAllowed"], false);
    assert_eq!(policy["generatedArtifactsAllowed"], false);

    let packet = root["sampleReviewPacket"]
        .as_object()
        .expect("sample review packet must be an object");
    assert_eq!(packet["reviewPacketState"], "summary_only_fixture");
    assert_eq!(packet["summaryOnly"], true);
    assert_eq!(packet["pathIncluded"], false);
    assert_eq!(packet["privatePathsIncluded"], false);
    assert_eq!(packet["stdoutIncluded"], false);
    assert_eq!(packet["stderrIncluded"], false);
    assert_eq!(packet["rawLogsIncluded"], false);
    assert_eq!(packet["artifactPathsIncluded"], false);
    assert_eq!(packet["generatedArtifactsIncluded"], false);
    assert_eq!(packet["rawTraceIncluded"], false);
    assert_eq!(packet["rawReportIncluded"], false);
    assert_eq!(packet["toolInvoked"], false);
    assert_eq!(packet["prCreated"], false);
    assert_eq!(packet["prCommentCreated"], false);
    assert_eq!(packet["issueCommentCreated"], false);
    assert_eq!(packet["projectUpdated"], false);
    assert_eq!(packet["publicTextPublished"], false);

    let sections = packet["reviewSections"]
        .as_array()
        .expect("sample review sections must be an array");
    assert!(sections.iter().all(|section| {
        section["summaryOnly"] == true
            && section["pathIncluded"] == false
            && section["stdoutIncluded"] == false
            && section["stderrIncluded"] == false
            && section["rawLogsIncluded"] == false
            && section["rawTraceIncluded"] == false
            && section["rawReportIncluded"] == false
    }));

    let risk_rows = packet["riskRows"]
        .as_array()
        .expect("sample risk rows must be an array");
    assert!(risk_rows.iter().all(|row| {
        row["summaryOnly"] == true
            && row["commandIncluded"] == false
            && row["pathIncluded"] == false
            && row["artifactPathIncluded"] == false
    }));

    let checklist = packet["checklistItems"]
        .as_array()
        .expect("sample review checklist items must be an array");
    assert!(checklist.iter().all(|item| {
        item["summaryOnly"] == true
            && item["commandIncluded"] == false
            && item["pathIncluded"] == false
            && item["artifactPathIncluded"] == false
    }));

    let validation_lines = packet["validationLines"]
        .as_array()
        .expect("sample review validation lines must be an array");
    assert!(validation_lines.iter().all(|line| {
        line["summaryOnly"] == true
            && line["commandIncluded"] == false
            && line["stdoutIncluded"] == false
            && line["stderrIncluded"] == false
            && line["rawLogsIncluded"] == false
            && line["artifactPathIncluded"] == false
    }));

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["trackedFileDiffCaptured"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["reportWriteAllowed"], false);
    assert_eq!(mutation["repositoryMutationAllowed"], false);
    assert_eq!(mutation["toolInvocationAllowed"], false);
    assert_eq!(mutation["commandExecutionAllowed"], false);
    assert_eq!(mutation["publicPushAllowed"], false);
    assert_eq!(mutation["releaseOrTagAllowed"], false);
    assert_eq!(mutation["prCreationAllowed"], false);
    assert_eq!(mutation["prCommentAllowed"], false);
    assert_eq!(mutation["issueCommentAllowed"], false);
    assert_eq!(mutation["projectMutationAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["reviewPacketFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["approvalExecutorImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["reportWriterImplemented"], false);
    assert_eq!(safety["prCreation"], false);
    assert_eq!(safety["prComment"], false);
    assert_eq!(safety["issueComment"], false);
    assert_eq!(safety["projectMutation"], false);
    assert_eq!(safety["publicTextPublication"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["artifactPathsIncluded"], false);
    assert_eq!(safety["generatedArtifactsIncluded"], false);
    assert_eq!(safety["telemetry"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
}

#[test]
fn mcp_evidence_manifest_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("mcp-evidence-manifest.example.json");
    let root = value
        .as_object()
        .expect("MCP evidence manifest must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-evidence-manifest.v0");
    assert_eq!(root["manifestState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");
    assert_eq!(root["manifestKind"], "approved_summary_evidence_refs");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "lab_status"
            && source["summaryOnly"] == true
            && source["pathEchoAllowed"] == false
            && source["artifactReadAllowed"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "mcp_review_packet"
            && source["toolInvocationAllowed"] == false
            && source["repositoryMutationAllowed"] == false
    }));

    let evidence_refs = root["approvedEvidenceRefs"]
        .as_array()
        .expect("approved evidence refs must be an array");
    assert!(
        evidence_refs.len() >= 3,
        "manifest should cover lab, launcher, and verification summaries"
    );
    for evidence in evidence_refs {
        assert_eq!(evidence["evidenceState"], "approved_summary_only");
        assert_eq!(evidence["summaryOnly"], true);
        assert_eq!(evidence["approvalRequired"], true);
        assert_eq!(evidence["approvedSummaryRef"], true);
        assert_eq!(evidence["localFileRead"], false);
        assert_eq!(evidence["repositoryRead"], false);
        assert_eq!(evidence["rawTraceRead"], false);
        assert_eq!(evidence["rawReportRead"], false);
        assert_eq!(evidence["rawLogRead"], false);
        assert_eq!(evidence["artifactRead"], false);
        assert_eq!(evidence["artifactWrite"], false);
        assert_eq!(evidence["privatePathEchoAllowed"], false);
        assert_eq!(evidence["stdoutIncluded"], false);
        assert_eq!(evidence["stderrIncluded"], false);
        assert_eq!(evidence["rawLogIncluded"], false);
        assert_eq!(evidence["artifactPathIncluded"], false);
        assert_eq!(evidence["hardwareDumpIncluded"], false);
        assert_eq!(evidence["boardDumpIncluded"], false);
        assert_eq!(evidence["modelWeightPathIncluded"], false);
        assert!(evidence["fieldDescriptors"].as_array().is_some());
    }

    let policy = root["manifestPolicy"]
        .as_object()
        .expect("manifest policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequired"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["mcpRuntimeAllowed"], false);
    assert_eq!(policy["toolInvocationAllowed"], false);
    assert_eq!(policy["commandExecutionAllowed"], false);
    assert_eq!(policy["localFileReadAllowed"], false);
    assert_eq!(policy["repositoryReadAllowed"], false);
    assert_eq!(policy["rawTraceReadAllowed"], false);
    assert_eq!(policy["rawReportReadAllowed"], false);
    assert_eq!(policy["rawLogReadAllowed"], false);
    assert_eq!(policy["artifactReadAllowed"], false);
    assert_eq!(policy["artifactWriteAllowed"], false);
    assert_eq!(policy["reportWriteAllowed"], false);
    assert_eq!(policy["evidenceArtifactWriteAllowed"], false);
    assert_eq!(policy["repositoryMutationAllowed"], false);
    assert_eq!(policy["publicTextPublicationAllowed"], false);
    assert_eq!(policy["hardwareAccessAllowed"], false);
    assert_eq!(policy["kv260AccessAllowed"], false);
    assert_eq!(policy["fpgaRepoAccessAllowed"], false);

    let manifest = root["sampleManifest"]
        .as_object()
        .expect("sample manifest must be an object");
    assert_eq!(manifest["manifestState"], "summary_only_fixture");
    assert_eq!(manifest["summaryOnly"], true);
    assert_eq!(manifest["pathIncluded"], false);
    assert_eq!(manifest["privatePathsIncluded"], false);
    assert_eq!(manifest["stdoutIncluded"], false);
    assert_eq!(manifest["stderrIncluded"], false);
    assert_eq!(manifest["rawLogsIncluded"], false);
    assert_eq!(manifest["artifactPathsIncluded"], false);
    assert_eq!(manifest["generatedArtifactsIncluded"], false);
    assert_eq!(manifest["rawTraceIncluded"], false);
    assert_eq!(manifest["rawReportIncluded"], false);
    assert_eq!(manifest["hardwareDumpIncluded"], false);
    assert_eq!(manifest["boardDumpIncluded"], false);
    assert_eq!(manifest["modelPathsIncluded"], false);
    assert_eq!(manifest["manifestPublished"], false);
    assert_eq!(manifest["evidenceArtifactWritten"], false);

    let rows = manifest["evidenceRows"]
        .as_array()
        .expect("sample manifest evidence rows must be an array");
    assert!(rows.iter().all(|row| {
        row["summaryOnly"] == true
            && row["pathIncluded"] == false
            && row["privatePathsIncluded"] == false
            && row["rawTraceIncluded"] == false
            && row["rawReportIncluded"] == false
            && row["rawLogsIncluded"] == false
            && row["artifactPathIncluded"] == false
            && row["hardwareDumpIncluded"] == false
            && row["boardDumpIncluded"] == false
            && row["modelPathIncluded"] == false
    }));

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["trackedFileDiffCaptured"], false);
    assert_eq!(mutation["localFileReadAllowed"], false);
    assert_eq!(mutation["repositoryReadAllowed"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["reportWriteAllowed"], false);
    assert_eq!(mutation["evidenceArtifactWriteAllowed"], false);
    assert_eq!(mutation["repositoryMutationAllowed"], false);
    assert_eq!(mutation["toolInvocationAllowed"], false);
    assert_eq!(mutation["commandExecutionAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["evidenceManifestFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["toolInvocationAttempted"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["rawLogRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["reportWriterImplemented"], false);
    assert_eq!(safety["evidenceArtifactWriterImplemented"], false);
    assert_eq!(safety["auditLoggerImplemented"], false);
    assert_eq!(safety["auditPersistence"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["launcherExecution"], false);
    assert_eq!(safety["editorExecution"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["modelWeightsIncluded"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["artifactPathsIncluded"], false);
    assert_eq!(safety["hardwareDumpIncluded"], false);
    assert_eq!(safety["boardDumpIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
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
fn mcp_approval_request_example_keeps_approval_boundary_non_executing() {
    let value: serde_json::Value = parse_example("mcp-approval-request.example.json");
    let root = value
        .as_object()
        .expect("MCP approval request must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-approval-request.v0");
    assert_eq!(root["requestState"], "approval_required");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let requested = root["requestedTool"]
        .as_object()
        .expect("requested tool must be an object");
    assert_eq!(requested["approvalRequired"], true);
    assert_eq!(requested["sideEffectPolicy"], "no_repository_mutation");
    assert!(requested["fixedArgsPreview"].as_array().is_some());

    let approval = root["approvalPolicy"]
        .as_object()
        .expect("approval policy must be an object");
    assert_eq!(approval["userApprovalRequired"], true);
    assert_eq!(approval["writeActionAllowed"], false);
    assert_eq!(approval["artifactWriteAllowed"], false);
    assert_eq!(approval["repositoryMutationAllowed"], false);
    assert_eq!(approval["pathEchoAllowed"], false);
    assert_eq!(approval["rawShellCommandsAllowed"], false);
    assert_eq!(approval["backgroundMutationAllowed"], false);
    assert_eq!(approval["publicPushAllowed"], false);
    assert_eq!(approval["releaseOrTagAllowed"], false);

    let mutation = root["repositoryMutationBoundary"]
        .as_object()
        .expect("repository mutation boundary must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["writeBackAllowed"], false);
    assert_eq!(mutation["publicPushAllowed"], false);
    assert_eq!(mutation["releaseOrTagAllowed"], false);

    let redaction = root["redactionPolicy"]
        .as_object()
        .expect("redaction policy must be an object");
    assert_eq!(redaction["approvedInputRefOnly"], true);
    assert_eq!(redaction["privatePathsIncluded"], false);
    assert_eq!(redaction["secretsIncluded"], false);
    assert_eq!(redaction["tokensIncluded"], false);
    assert_eq!(redaction["stdoutIncluded"], false);
    assert_eq!(redaction["stderrIncluded"], false);

    let checklist = root["approvalChecklist"]
        .as_array()
        .expect("approval checklist must be an array");
    assert!(checklist.iter().any(|item| {
        item["checkId"] == "approved_input_reference_required"
            && item["state"] == "approval_required"
    }));
    assert!(checklist
        .iter()
        .any(|item| { item["checkId"] == "no_mutation_guard" && item["state"] == "blocked" }));

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["approvalFixtureOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn mcp_approval_decision_example_keeps_denied_decision_non_executing() {
    let value: serde_json::Value = parse_example("mcp-approval-decision.example.json");
    let root = value
        .as_object()
        .expect("MCP approval decision must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-approval-decision.v0");
    assert_eq!(root["decisionState"], "denied");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let source = root["sourceRequestRef"]
        .as_object()
        .expect("source request ref must be an object");
    assert_eq!(source["schemaVersion"], "pccx.lab.mcp-approval-request.v0");
    assert_eq!(source["requestState"], "approval_required");

    let decision = root["decisionPolicy"]
        .as_object()
        .expect("decision policy must be an object");
    assert_eq!(decision["userDecisionRequired"], true);
    assert_eq!(decision["approved"], false);
    assert_eq!(decision["denied"], true);
    assert_eq!(decision["toolInvocationAllowed"], false);
    assert_eq!(decision["writeActionAllowed"], false);
    assert_eq!(decision["artifactWriteAllowed"], false);
    assert_eq!(decision["repositoryMutationAllowed"], false);
    assert_eq!(decision["pathEchoAllowed"], false);
    assert_eq!(decision["rawShellCommandsAllowed"], false);
    assert_eq!(decision["backgroundMutationAllowed"], false);
    assert_eq!(decision["publicPushAllowed"], false);
    assert_eq!(decision["releaseOrTagAllowed"], false);

    let gate = root["toolInvocationGate"]
        .as_object()
        .expect("tool invocation gate must be an object");
    assert_eq!(gate["toolInvocationAllowed"], false);
    assert_eq!(gate["commandExecutionAllowed"], false);
    assert_eq!(gate["shellExecutionAllowed"], false);
    assert_eq!(gate["runtimeExecutionAllowed"], false);
    assert_eq!(gate["networkCallAllowed"], false);
    assert_eq!(gate["providerCallAllowed"], false);
    assert_eq!(gate["hardwareAccessAllowed"], false);
    assert_eq!(gate["modelLoadAllowed"], false);

    let mutation = root["repositoryMutationBoundary"]
        .as_object()
        .expect("repository mutation boundary must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["writeBackAllowed"], false);
    assert_eq!(mutation["publicPushAllowed"], false);
    assert_eq!(mutation["releaseOrTagAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
        "approval-executor",
        "tool-invocation",
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
    assert_eq!(safety["approvalDecisionFixtureOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["approvalExecutorImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
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
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
}

#[test]
fn mcp_invocation_request_example_keeps_invocation_blocked_boundary() {
    let value: serde_json::Value = parse_example("mcp-invocation-request.example.json");
    let root = value
        .as_object()
        .expect("MCP invocation request must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.mcp-invocation-request.v0");
    assert_eq!(root["requestState"], "blocked_by_policy");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "mcp_approval_decision"
            && source["approved"] == false
            && source["toolInvocationAllowed"] == false
            && source["commandExecutionAllowed"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "mcp_review_packet"
            && source["toolInvocationAllowed"] == false
            && source["artifactWriteAllowed"] == false
            && source["repositoryMutationAllowed"] == false
    }));

    let request = root["invocationRequest"]
        .as_object()
        .expect("invocation request must be an object");
    assert_eq!(request["requestKind"], "planned_mcp_tool_invocation_gate");
    assert_eq!(request["toolId"], "pccx-lab.analyze");
    assert_eq!(request["summaryOnly"], true);
    assert_eq!(request["approvalRequired"], true);
    assert_eq!(request["approved"], false);
    assert_eq!(request["inputRefOnly"], true);
    assert_eq!(request["pathEchoAllowed"], false);
    assert_eq!(request["localFileReadAllowed"], false);
    assert_eq!(request["repositoryReadAllowed"], false);
    assert_eq!(request["artifactReadAllowed"], false);
    assert_eq!(request["commandExecutionAllowed"], false);
    assert_eq!(request["shellExecutionAllowed"], false);
    assert_eq!(request["runtimeExecutionAllowed"], false);
    assert_eq!(request["toolInvocationAllowed"], false);
    assert_eq!(request["providerCallAllowed"], false);
    assert_eq!(request["networkCallAllowed"], false);
    assert_eq!(request["hardwareAccessAllowed"], false);
    assert_eq!(request["modelLoadAllowed"], false);

    let decision = root["invocationDecision"]
        .as_object()
        .expect("invocation decision must be an object");
    assert_eq!(decision["state"], "not_invoked");
    assert_eq!(decision["approved"], false);
    assert_eq!(decision["denied"], true);
    assert_eq!(decision["mcpServerStarted"], false);
    assert_eq!(decision["mcpClientSessionStarted"], false);
    assert_eq!(decision["toolInvocationStarted"], false);
    assert_eq!(decision["approvalExecutorCalled"], false);
    assert_eq!(decision["permissionExecutorCalled"], false);
    assert_eq!(decision["commandExecutionAttempted"], false);
    assert_eq!(decision["localFileReadAttempted"], false);
    assert_eq!(decision["artifactWriteAttempted"], false);
    assert_eq!(decision["repositoryMutationAttempted"], false);

    let context = root["plannedToolContext"]
        .as_object()
        .expect("planned tool context must be an object");
    assert_eq!(context["summaryOnly"], true);
    assert_eq!(context["approvedInputReferenceOnly"], true);
    assert_eq!(context["privatePathsIncluded"], false);
    assert_eq!(context["localFileRead"], false);
    assert_eq!(context["repositoryRead"], false);
    assert_eq!(context["artifactRead"], false);
    assert_eq!(context["stdoutIncluded"], false);
    assert_eq!(context["stderrIncluded"], false);
    assert_eq!(context["rawLogsIncluded"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["invocationRequestFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["approvalExecutorImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["toolInvocationAttempted"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["diagnosticsProduced"], false);
    assert_eq!(safety["reportProduced"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["launcherExecution"], false);
    assert_eq!(safety["editorExecution"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
}

#[test]
fn mcp_client_session_state_example_keeps_client_session_blocked_boundary() {
    let value: serde_json::Value = parse_example("mcp-client-session-state.example.json");
    let root = value
        .as_object()
        .expect("MCP client/session state must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.mcp-client-session-state.v0"
    );
    assert_eq!(root["sessionState"], "not_started");
    assert_eq!(root["connectionState"], "not_configured");
    assert_eq!(root["transportState"], "not_open");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "mcp_read_only_tool_plan"
            && source["toolCatalogAvailableAsData"] == true
            && source["clientRuntimeAllowed"] == false
            && source["serverRuntimeAllowed"] == false
            && source["toolInvocationAllowed"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "mcp_invocation_request"
            && source["sessionStartAllowed"] == false
            && source["toolInvocationAllowed"] == false
            && source["commandExecutionAllowed"] == false
    }));

    let session = root["clientSession"]
        .as_object()
        .expect("client session must be an object");
    assert_eq!(session["sessionKind"], "planned_mcp_client_session_state");
    assert_eq!(session["lifecycleState"], "not_started");
    assert_eq!(session["approvalState"], "not_approved");
    assert_eq!(session["invocationState"], "not_invoked");
    assert_eq!(session["summaryOnly"], true);
    assert_eq!(session["sessionOpen"], false);
    assert_eq!(session["transportOpen"], false);
    assert_eq!(session["handshakeComplete"], false);
    assert_eq!(session["clientRuntimeStarted"], false);
    assert_eq!(session["serverRuntimeStarted"], false);
    assert_eq!(session["toolCatalogFetched"], false);
    assert_eq!(session["toolInvocationStarted"], false);
    assert_eq!(session["approvalExecutorCalled"], false);
    assert_eq!(session["permissionExecutorCalled"], false);
    assert_eq!(session["commandExecutionAttempted"], false);
    assert_eq!(session["localFileReadAttempted"], false);
    assert_eq!(session["repositoryMutationAttempted"], false);
    assert_eq!(session["networkCallAttempted"], false);
    assert_eq!(session["hardwareAccessAttempted"], false);

    let transport = root["transportPolicy"]
        .as_object()
        .expect("transport policy must be an object");
    assert_eq!(transport["state"], "not_open");
    assert_eq!(transport["transportOpenAllowed"], false);
    assert_eq!(transport["stdioProcessAllowed"], false);
    assert_eq!(transport["socketAllowed"], false);
    assert_eq!(transport["networkAllowed"], false);
    assert_eq!(transport["browserAllowed"], false);
    assert_eq!(transport["ipcAllowed"], false);
    assert_eq!(transport["serverStartAllowed"], false);
    assert_eq!(transport["clientStartAllowed"], false);
    assert_eq!(transport["handshakeAllowed"], false);
    assert_eq!(transport["toolListRequestAllowed"], false);

    let audit = root["auditPolicy"]
        .as_object()
        .expect("audit policy must be an object");
    assert_eq!(audit["summaryOnly"], true);
    assert_eq!(audit["auditLoggerAllowed"], false);
    assert_eq!(audit["auditPersistenceAllowed"], false);
    assert_eq!(audit["pathEchoAllowed"], false);
    assert_eq!(audit["stdoutIncluded"], false);
    assert_eq!(audit["stderrIncluded"], false);
    assert_eq!(audit["rawLogsIncluded"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["clientSessionStateFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["mcpClientSessionStarted"], false);
    assert_eq!(safety["transportOpened"], false);
    assert_eq!(safety["handshakeAttempted"], false);
    assert_eq!(safety["toolListRequested"], false);
    assert_eq!(safety["approvalExecutorImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["toolInvocationAttempted"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["auditLoggerImplemented"], false);
    assert_eq!(safety["auditPersistence"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["launcherExecution"], false);
    assert_eq!(safety["editorExecution"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
}

#[test]
fn mcp_blocked_invocation_result_example_keeps_non_executing_result_boundary() {
    let value: serde_json::Value = parse_example("mcp-blocked-invocation-result.example.json");
    let root = value
        .as_object()
        .expect("MCP blocked invocation result must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.mcp-blocked-invocation-result.v0"
    );
    assert_eq!(root["resultState"], "blocked_by_policy");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let request = root["sourceRequestRef"]
        .as_object()
        .expect("source request ref must be an object");
    assert_eq!(request["schemaVersion"], "pccx.lab.mcp-approval-request.v0");
    assert_eq!(request["requestState"], "approval_required");

    let decision = root["sourceDecisionRef"]
        .as_object()
        .expect("source decision ref must be an object");
    assert_eq!(
        decision["schemaVersion"],
        "pccx.lab.mcp-approval-decision.v0"
    );
    assert_eq!(decision["decisionState"], "denied");

    let tool_request = root["toolRequest"]
        .as_object()
        .expect("tool request must be an object");
    assert_eq!(tool_request["toolId"], "pccx-lab.analyze");
    assert_eq!(tool_request["commandKind"], "planned-cli-fixed-args");
    assert_eq!(tool_request["pathEchoAllowed"], false);
    assert_eq!(tool_request["rawShellCommandAllowed"], false);

    let result = root["blockedResult"]
        .as_object()
        .expect("blocked result must be an object");
    assert_eq!(result["state"], "not_executed");
    assert_eq!(result["reason"], "approval_decision_denied");
    assert_eq!(result["summaryOnly"], true);
    assert_eq!(result["toolInvocationAttempted"], false);
    assert_eq!(result["commandExecutionAttempted"], false);
    assert_eq!(result["localFileReadAttempted"], false);
    assert_eq!(result["artifactWriteAttempted"], false);
    assert_eq!(result["repositoryMutationAttempted"], false);
    assert!(result["exitCode"].is_null());

    let output = root["outputPreview"]
        .as_object()
        .expect("output preview must be an object");
    assert_eq!(output["diagnosticsProduced"], false);
    assert_eq!(output["reportProduced"], false);
    assert_eq!(output["stdoutIncluded"], false);
    assert_eq!(output["stderrIncluded"], false);
    assert_eq!(output["rawLogsIncluded"], false);
    assert_eq!(output["privatePathsIncluded"], false);
    assert_eq!(output["artifactPathsIncluded"], false);

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["trackedFileDiffCaptured"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["publicPushAllowed"], false);
    assert_eq!(mutation["releaseOrTagAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
        "approval-executor",
        "permission-executor",
        "tool-invocation",
        "command-execution",
        "local-file-read",
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
    assert_eq!(safety["blockedResultFixtureOnly"], true);
    assert_eq!(safety["mcpRuntimeImplemented"], false);
    assert_eq!(safety["mcpServerImplemented"], false);
    assert_eq!(safety["mcpClientImplemented"], false);
    assert_eq!(safety["approvalExecutorImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["toolInvocationPathImplemented"], false);
    assert_eq!(safety["toolInvocationAttempted"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["diagnosticsProduced"], false);
    assert_eq!(safety["reportProduced"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
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
fn plugin_input_contract_example_keeps_summary_input_boundary() {
    let value: serde_json::Value = parse_example("plugin-input-contract.example.json");
    let root = value
        .as_object()
        .expect("plugin input contract must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-input-contract.v0");
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

    let sources = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(sources.iter().any(|source| {
        source["refId"] == "diagnostics_envelope" && source["pathEchoAllowed"] == false
    }));
    assert!(sources
        .iter()
        .any(|source| source["refId"] == "workflow_results" && source["pathEchoAllowed"] == false));

    let inputs = root["inputContracts"]
        .as_array()
        .expect("input contracts must be an array");
    assert!(
        inputs.len() >= 2,
        "input contract should cover diagnostics and workflow-result summaries"
    );
    for input in inputs {
        assert_eq!(input["summaryOnly"], true);
        assert_eq!(input["approvalRequired"], true);
        assert_eq!(input["localFileRead"], false);
        assert_eq!(input["rawTraceRead"], false);
        assert_eq!(input["rawReportRead"], false);
        assert_eq!(input["artifactRead"], false);
        assert_eq!(input["privatePathEchoAllowed"], false);
        assert_eq!(input["stdoutIncluded"], false);
        assert_eq!(input["stderrIncluded"], false);
        assert_eq!(input["rawLogIncluded"], false);
    }

    let preview = root["sampleInputPreview"]
        .as_object()
        .expect("sample input preview must be an object");
    let diagnostics = preview["diagnosticEnvelopeSummary"]
        .as_object()
        .expect("diagnostics summary preview must be an object");
    assert_eq!(diagnostics["pathIncluded"], false);
    assert_eq!(diagnostics["privatePathsIncluded"], false);
    assert_eq!(diagnostics["stdoutIncluded"], false);
    assert_eq!(diagnostics["stderrIncluded"], false);
    assert_eq!(diagnostics["rawLogsIncluded"], false);
    let workflow = preview["workflowResultSummary"]
        .as_object()
        .expect("workflow result preview must be an object");
    assert_eq!(workflow["artifactPathIncluded"], false);
    assert_eq!(workflow["privatePathsIncluded"], false);
    assert_eq!(workflow["stdoutIncluded"], false);
    assert_eq!(workflow["stderrIncluded"], false);
    assert_eq!(workflow["rawLogsIncluded"], false);
    let trace_gate = preview["traceInputGate"]
        .as_object()
        .expect("trace input gate must be an object");
    assert_eq!(trace_gate["traceSummaryRequired"], true);
    assert_eq!(trace_gate["rawTraceInputAllowed"], false);
    assert_eq!(trace_gate["pathEchoAllowed"], false);

    let policy = root["inputPolicy"]
        .as_object()
        .expect("input policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequired"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["trackedFileMutationAllowed"], false);
    assert_eq!(policy["localFileReadAllowed"], false);
    assert_eq!(policy["rawTraceReadAllowed"], false);
    assert_eq!(policy["rawReportReadAllowed"], false);
    assert_eq!(policy["artifactReadAllowed"], false);
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
    assert_eq!(safety["inputFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["sandboxImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["inputReaderImplemented"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["localFileRead"], false);
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
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn plugin_trace_summary_input_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("plugin-trace-summary-input.example.json");
    let root = value
        .as_object()
        .expect("plugin trace-summary input must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.plugin-trace-summary-input.v0"
    );
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

    let sources = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(sources.iter().any(|source| {
        source["refId"] == "plugin_input_contract" && source["pathEchoAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "plugin_permission_model" && source["pathEchoAllowed"] == false
    }));

    let inputs = root["traceSummaryInputs"]
        .as_array()
        .expect("trace summary inputs must be an array");
    assert!(!inputs.is_empty());
    for input in inputs {
        assert_eq!(input["inputKind"], "trace_summary");
        assert_eq!(input["inputState"], "approved_summary_only");
        assert_eq!(input["summaryOnly"], true);
        assert_eq!(input["approvalRequired"], true);
        assert_eq!(input["localFileRead"], false);
        assert_eq!(input["rawTraceRead"], false);
        assert_eq!(input["rawReportRead"], false);
        assert_eq!(input["artifactRead"], false);
        assert_eq!(input["privatePathEchoAllowed"], false);
        assert_eq!(input["stdoutIncluded"], false);
        assert_eq!(input["stderrIncluded"], false);
        assert_eq!(input["rawLogIncluded"], false);
        assert_eq!(input["rawTraceIncluded"], false);
    }

    let summary = root["sampleTraceSummary"]
        .as_object()
        .expect("sample trace summary must be an object");
    assert!(summary["eventCount"].as_u64().is_some());
    assert!(summary["signalCount"].as_u64().is_some());
    assert!(summary["cycleStart"].as_u64().is_some());
    assert!(summary["cycleEnd"].as_u64().is_some());
    assert_eq!(summary["pathIncluded"], false);
    assert_eq!(summary["signalNamesIncluded"], false);
    assert_eq!(summary["rawTraceIncluded"], false);
    assert_eq!(summary["privatePathsIncluded"], false);
    assert_eq!(summary["stdoutIncluded"], false);
    assert_eq!(summary["stderrIncluded"], false);
    assert_eq!(summary["rawLogsIncluded"], false);
    assert_eq!(summary["artifactPathsIncluded"], false);
    assert_eq!(summary["generatedArtifactsIncluded"], false);

    let policy = root["inputPolicy"]
        .as_object()
        .expect("input policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequired"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["trackedFileMutationAllowed"], false);
    assert_eq!(policy["localFileReadAllowed"], false);
    assert_eq!(policy["rawTraceReadAllowed"], false);
    assert_eq!(policy["rawReportReadAllowed"], false);
    assert_eq!(policy["artifactReadAllowed"], false);
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
    assert_eq!(safety["inputFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["traceSummaryOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["sandboxImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["inputReaderImplemented"], false);
    assert_eq!(safety["traceImporterImplemented"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["localFileRead"], false);
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
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["signalNamesIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["readsArtifacts"], false);
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
fn plugin_blocked_invocation_result_example_keeps_non_executing_result_boundary() {
    let value: serde_json::Value = parse_example("plugin-blocked-invocation-result.example.json");
    let root = value
        .as_object()
        .expect("plugin blocked invocation result must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.plugin-blocked-invocation-result.v0"
    );
    assert_eq!(root["resultState"], "blocked_by_policy");
    assert_eq!(root["pluginRuntimeState"], "not_implemented");
    assert_eq!(root["loaderState"], "not_implemented");
    assert_eq!(root["sandboxState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");

    let input_ref = root["sourceInputRef"]
        .as_object()
        .expect("source input ref must be an object");
    assert_eq!(
        input_ref["schemaVersion"],
        "pccx.lab.plugin-input-contract.v0"
    );
    assert_eq!(input_ref["inputState"], "approved_summary_only");
    assert_eq!(input_ref["pathEchoAllowed"], false);

    let output_ref = root["sourceOutputRef"]
        .as_object()
        .expect("source output ref must be an object");
    assert_eq!(
        output_ref["schemaVersion"],
        "pccx.lab.plugin-output-contract.v0"
    );
    assert_eq!(output_ref["artifactWriteAllowed"], false);

    let request = root["pluginInvocationRequest"]
        .as_object()
        .expect("plugin invocation request must be an object");
    assert_eq!(request["commandKind"], "planned-cli-fixed-args");
    assert_eq!(
        request["approvedInputReferenceKind"],
        "approved-summary-reference"
    );
    assert_eq!(request["pathEchoAllowed"], false);
    assert_eq!(request["rawShellCommandAllowed"], false);
    assert_eq!(request["pluginCodeLoadAllowed"], false);
    assert_eq!(request["packageInstallAllowed"], false);

    let result = root["blockedResult"]
        .as_object()
        .expect("blocked result must be an object");
    assert_eq!(result["state"], "not_executed");
    assert_eq!(result["reason"], "plugin_runtime_not_implemented");
    assert_eq!(result["summaryOnly"], true);
    assert_eq!(result["pluginInvocationAttempted"], false);
    assert_eq!(result["pluginCodeLoaded"], false);
    assert_eq!(result["commandExecutionAttempted"], false);
    assert_eq!(result["inputReaderAttempted"], false);
    assert_eq!(result["artifactReadAttempted"], false);
    assert_eq!(result["artifactWriteAttempted"], false);
    assert_eq!(result["repositoryMutationAttempted"], false);
    assert!(result["exitCode"].is_null());

    let output = root["outputPreview"]
        .as_object()
        .expect("output preview must be an object");
    assert_eq!(output["diagnosticsProduced"], false);
    assert_eq!(output["panelProduced"], false);
    assert_eq!(output["reportItemsProduced"], false);
    assert_eq!(output["stdoutIncluded"], false);
    assert_eq!(output["stderrIncluded"], false);
    assert_eq!(output["rawLogsIncluded"], false);
    assert_eq!(output["privatePathsIncluded"], false);
    assert_eq!(output["artifactPathsIncluded"], false);

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["trackedFileDiffCaptured"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["publicPushAllowed"], false);
    assert_eq!(mutation["releaseOrTagAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["blockedResultFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginInvocationPathImplemented"], false);
    assert_eq!(safety["pluginInvocationAttempted"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["sandboxImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["inputReaderImplemented"], false);
    assert_eq!(safety["reportWriterImplemented"], false);
    assert_eq!(safety["stablePluginAbiPromised"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["diagnosticsProduced"], false);
    assert_eq!(safety["panelProduced"], false);
    assert_eq!(safety["reportItemsProduced"], false);
    assert_eq!(safety["telemetry"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
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

#[test]
fn plugin_audit_event_example_keeps_redacted_non_executing_boundary() {
    let value: serde_json::Value = parse_example("plugin-audit-event.example.json");
    let root = value
        .as_object()
        .expect("plugin audit event must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-audit-event.v0");
    assert_eq!(root["eventState"], "example_only");
    assert_eq!(root["pluginRuntimeState"], "not_implemented");
    assert_eq!(root["loaderState"], "not_implemented");
    assert_eq!(root["outcomeState"], "not_executed");
    assert_eq!(root["pluginId"], "example.diagnostics.summary");
    assert_eq!(root["capabilityId"], "plugin.manifest.validate");

    let args = root["fixedArgsPreview"]
        .as_array()
        .expect("fixed args preview must be an array");
    assert_eq!(args[0], "plugin-manifest");
    assert_eq!(args[1], "validate");
    assert_eq!(args[2], "--file");
    assert_eq!(args[3], "<approved-manifest-json>");

    let validation = root["validationSummary"]
        .as_object()
        .expect("validation summary must be an object");
    assert_eq!(validation["summaryOnly"], true);
    assert_eq!(validation["pathEchoed"], false);
    assert_eq!(validation["stdoutCaptured"], false);
    assert_eq!(validation["stderrCaptured"], false);
    assert_eq!(validation["artifactWritten"], false);
    assert_eq!(validation["pluginCodeLoaded"], false);
    assert_eq!(validation["packageInstalled"], false);
    assert_eq!(validation["dynamicLibrariesLoaded"], false);

    let redaction = root["redactionState"]
        .as_object()
        .expect("redaction state must be an object");
    assert_eq!(redaction["privatePathsIncluded"], false);
    assert_eq!(redaction["secretsIncluded"], false);
    assert_eq!(redaction["tokensIncluded"], false);
    assert_eq!(redaction["modelWeightPathsIncluded"], false);
    assert_eq!(redaction["stdoutIncluded"], false);
    assert_eq!(redaction["stderrIncluded"], false);
    assert_eq!(redaction["artifactPathsIncluded"], false);

    let safety = root["safetyFlags"]
        .as_object()
        .expect("safety flags must be an object");
    assert_eq!(safety["dataOnly"], true);
    assert_eq!(safety["descriptorOnly"], true);
    assert_eq!(safety["readOnly"], true);
    assert_eq!(safety["auditFixtureOnly"], true);
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
fn plugin_manifest_validation_result_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("plugin-manifest-validation-result.example.json");
    let root = value
        .as_object()
        .expect("plugin manifest validation result must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.plugin-manifest-validation-result.v0"
    );
    assert_eq!(root["resultState"], "example_only");
    assert_eq!(root["pluginRuntimeState"], "not_implemented");
    assert_eq!(root["loaderState"], "not_implemented");
    assert_eq!(root["sandboxState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");

    let manifest = root["sourceManifestRef"]
        .as_object()
        .expect("source manifest ref must be an object");
    assert_eq!(manifest["schemaVersion"], "pccx.lab.plugin-manifest.v0");
    assert_eq!(manifest["pathEchoAllowed"], false);
    assert_eq!(manifest["manifestContentIncluded"], false);
    assert_eq!(manifest["localFileRead"], false);

    let request = root["validationRequest"]
        .as_object()
        .expect("validation request must be an object");
    assert_eq!(request["commandKind"], "planned-cli-fixed-args");
    assert_eq!(
        request["approvedInputReferenceKind"],
        "approved-plugin-manifest-json"
    );
    assert_eq!(request["pathEchoAllowed"], false);
    assert_eq!(request["rawShellCommandAllowed"], false);
    assert_eq!(request["manifestReaderImplemented"], false);
    assert_eq!(request["pluginCodeLoadAllowed"], false);
    assert_eq!(request["packageInstallAllowed"], false);

    let result = root["validationResult"]
        .as_object()
        .expect("validation result must be an object");
    assert_eq!(result["state"], "planned_result_shape");
    assert_eq!(result["summaryOnly"], true);
    assert_eq!(result["manifestReaderAttempted"], false);
    assert_eq!(result["pluginCodeLoaded"], false);
    assert_eq!(result["commandExecutionAttempted"], false);
    assert_eq!(result["packageInstalled"], false);
    assert_eq!(result["dynamicLibrariesLoaded"], false);
    assert_eq!(result["requiredFieldCount"], 9);
    assert!(result["missingRequiredFields"]
        .as_array()
        .expect("missing required fields must be an array")
        .is_empty());
    assert!(result["acceptedCapabilityIds"]
        .as_array()
        .expect("accepted capability ids must be an array")
        .iter()
        .any(|capability| capability == "plugin.diagnostics.summary"));
    assert!(result["blockedCapabilityIds"]
        .as_array()
        .expect("blocked capability ids must be an array")
        .iter()
        .any(|capability| capability == "plugin.trace.importer"));

    let redaction = root["redactionState"]
        .as_object()
        .expect("redaction state must be an object");
    assert_eq!(redaction["privatePathsIncluded"], false);
    assert_eq!(redaction["manifestContentIncluded"], false);
    assert_eq!(redaction["secretsIncluded"], false);
    assert_eq!(redaction["tokensIncluded"], false);
    assert_eq!(redaction["stdoutIncluded"], false);
    assert_eq!(redaction["stderrIncluded"], false);
    assert_eq!(redaction["artifactPathsIncluded"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
        "plugin-loader-start",
        "plugin-runtime-start",
        "manifest-file-read",
        "dynamic-code-load",
        "plugin-package-install",
        "marketplace-flow",
        "package-distribution",
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
    assert_eq!(safety["validationResultFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["pluginManifestValidatorImplemented"], false);
    assert_eq!(safety["manifestReaderImplemented"], false);
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
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["manifestContentIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn plugin_capability_list_example_keeps_descriptor_only_boundary() {
    let value: serde_json::Value = parse_example("plugin-capability-list.example.json");
    let root = value
        .as_object()
        .expect("plugin capability list must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-capability-list.v0");
    assert_eq!(root["listState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_boundary_plan"
            && source["manifestReaderAllowed"] == false
            && source["packageReaderAllowed"] == false
            && source["pluginLoaderAllowed"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_manifest_validation_result"
            && source["summaryOnly"] == true
            && source["manifestReaderAllowed"] == false
            && source["validatorCommandAllowed"] == false
    }));

    let request = root["capabilityListRequest"]
        .as_object()
        .expect("capability-list request must be an object");
    assert_eq!(request["requestKind"], "planned_plugin_capability_listing");
    assert_eq!(request["summaryOnly"], true);
    assert_eq!(request["inputRefOnly"], true);
    assert_eq!(request["pathEchoAllowed"], false);
    assert_eq!(request["manifestContentIncluded"], false);
    assert_eq!(request["packageContentIncluded"], false);
    assert_eq!(request["sourceCodeIncluded"], false);
    assert_eq!(request["localFileReadAllowed"], false);
    assert_eq!(request["repositoryReadAllowed"], false);
    assert_eq!(request["artifactReadAllowed"], false);
    assert_eq!(request["commandExecutionAllowed"], false);
    assert_eq!(request["runtimeExecutionAllowed"], false);
    assert_eq!(request["pluginLoaderAllowed"], false);
    assert_eq!(request["pluginRuntimeAllowed"], false);
    assert_eq!(request["capabilityDispatchAllowed"], false);
    assert_eq!(request["pluginInvocationAllowed"], false);
    assert_eq!(request["marketplaceFlowAllowed"], false);
    assert_eq!(request["stableApiAbiClaim"], false);
    assert_eq!(request["compatibilityClaim"], false);
    assert_eq!(request["marketplaceClaim"], false);

    let capabilities = root["capabilities"]
        .as_array()
        .expect("capabilities must be an array");
    assert!(capabilities.iter().any(|capability| {
        capability["capabilityId"] == "plugin.diagnostics.summary"
            && capability["approvedForListing"] == true
            && capability["approvedForLoad"] == false
            && capability["approvedForDispatch"] == false
            && capability["pluginInvocationAllowed"] == false
    }));
    assert!(capabilities.iter().any(|capability| {
        capability["capabilityId"] == "plugin.trace.importer"
            && capability["capabilityState"] == "deferred"
            && capability["traceImporterAllowed"] == false
            && capability["stableAbiRequired"] == false
    }));

    let display = root["displayPolicy"]
        .as_object()
        .expect("display policy must be an object");
    assert_eq!(display["summaryOnly"], true);
    assert_eq!(display["pathEchoAllowed"], false);
    assert_eq!(display["manifestContentIncluded"], false);
    assert_eq!(display["packageContentIncluded"], false);
    assert_eq!(display["privatePathsIncluded"], false);
    assert_eq!(display["stdoutIncluded"], false);
    assert_eq!(display["stderrIncluded"], false);
    assert_eq!(display["rawLogsIncluded"], false);
    assert_eq!(display["artifactPathsIncluded"], false);

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["localFileReadAllowed"], false);
    assert_eq!(mutation["repositoryReadAllowed"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["repositoryMutationAllowed"], false);
    assert_eq!(mutation["pluginLoadAllowed"], false);
    assert_eq!(mutation["pluginInvocationAllowed"], false);
    assert_eq!(mutation["commandExecutionAllowed"], false);
    assert_eq!(mutation["marketplacePublicationAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
        "manifest-reader",
        "package-reader",
        "plugin-loader-start",
        "plugin-runtime-start",
        "plugin-capability-dispatch",
        "plugin-invocation",
        "command-execution",
        "local-file-read",
        "repository-read",
        "artifact-read",
        "artifact-write",
        "package-distribution",
        "marketplace-flow",
        "dynamic-code-load",
        "provider-call",
        "network-call",
        "hardware-probe",
        "kv260-access",
        "fpga-repo-access",
        "model-load",
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
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["capabilityListFixtureOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["manifestReaderImplemented"], false);
    assert_eq!(safety["packageReaderImplemented"], false);
    assert_eq!(safety["inputReaderImplemented"], false);
    assert_eq!(safety["traceImporterImplemented"], false);
    assert_eq!(safety["capabilityDispatchImplemented"], false);
    assert_eq!(safety["pluginInvocationImplemented"], false);
    assert_eq!(safety["stablePluginAbiPromised"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["compatibilityClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["manifestContentIncluded"], false);
    assert_eq!(safety["packageContentIncluded"], false);
    assert_eq!(safety["sourceCodeIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["artifactPathsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
}

#[test]
fn plugin_load_request_example_keeps_loader_disabled_boundary() {
    let value: serde_json::Value = parse_example("plugin-load-request.example.json");
    let root = value
        .as_object()
        .expect("plugin load request must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-load-request.v0");
    assert_eq!(root["requestState"], "blocked_by_policy");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_boundary_plan"
            && source["manifestReaderAllowed"] == false
            && source["pluginLoaderAllowed"] == false
            && source["dynamicCodeLoadAllowed"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_review_packet"
            && source["pluginInvocationAllowed"] == false
            && source["packageInstallAllowed"] == false
            && source["repositoryMutationAllowed"] == false
    }));

    let request = root["loadRequest"]
        .as_object()
        .expect("load request must be an object");
    assert_eq!(request["requestKind"], "planned_plugin_load_gate");
    assert_eq!(request["summaryOnly"], true);
    assert_eq!(request["approvalRequired"], true);
    assert_eq!(request["manifestContentIncluded"], false);
    assert_eq!(request["manifestPathIncluded"], false);
    assert_eq!(request["localFileReadAllowed"], false);
    assert_eq!(request["repositoryReadAllowed"], false);
    assert_eq!(request["packageInstallAllowed"], false);
    assert_eq!(request["dynamicCodeLoadAllowed"], false);
    assert_eq!(request["sandboxStartAllowed"], false);
    assert_eq!(request["pluginRuntimeStartAllowed"], false);
    assert_eq!(request["pluginInvocationAllowed"], false);
    assert_eq!(request["commandExecutionAllowed"], false);

    let decision = root["loadDecision"]
        .as_object()
        .expect("load decision must be an object");
    assert_eq!(decision["state"], "not_loaded");
    assert_eq!(decision["approved"], false);
    assert_eq!(decision["loaderStarted"], false);
    assert_eq!(decision["runtimeStarted"], false);
    assert_eq!(decision["sandboxStarted"], false);
    assert_eq!(decision["pluginCodeLoaded"], false);
    assert_eq!(decision["dynamicLibrariesLoaded"], false);
    assert_eq!(decision["packageInstalled"], false);
    assert_eq!(decision["permissionExecutorCalled"], false);
    assert_eq!(decision["manifestReaderCalled"], false);
    assert_eq!(decision["validatorCommandCalled"], false);
    assert_eq!(decision["commandExecutionAttempted"], false);
    assert_eq!(decision["pluginInvocationAttempted"], false);

    let context = root["plannedHostContext"]
        .as_object()
        .expect("planned host context must be an object");
    assert_eq!(context["summaryOnly"], true);
    assert_eq!(context["manifestContentIncluded"], false);
    assert_eq!(context["manifestPathIncluded"], false);
    assert_eq!(context["packageContentIncluded"], false);
    assert_eq!(context["sourceCodeIncluded"], false);
    assert_eq!(context["localFileRead"], false);
    assert_eq!(context["repositoryRead"], false);
    assert_eq!(context["artifactRead"], false);
    assert_eq!(context["stdoutIncluded"], false);
    assert_eq!(context["stderrIncluded"], false);
    assert_eq!(context["rawLogsIncluded"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["pluginLoadRequestFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginSandboxImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["manifestReaderImplemented"], false);
    assert_eq!(safety["validatorCommandImplemented"], false);
    assert_eq!(safety["pluginInvocationPathImplemented"], false);
    assert_eq!(safety["pluginInvocationAttempted"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["packageInstall"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["dynamicCodeLoad"], false);
    assert_eq!(safety["untrustedExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["manifestContentIncluded"], false);
    assert_eq!(safety["packageContentIncluded"], false);
    assert_eq!(safety["sourceCodeIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["compatibilityClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
}

#[test]
fn plugin_host_session_state_example_keeps_host_session_blocked_boundary() {
    let value: serde_json::Value = parse_example("plugin-host-session-state.example.json");
    let root = value
        .as_object()
        .expect("plugin host session state must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.plugin-host-session-state.v0"
    );
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");
    assert_eq!(root["sessionState"], "not_started");
    assert_eq!(root["loadState"], "not_loaded");
    assert_eq!(root["sandboxState"], "not_started");
    assert_eq!(root["runtimeState"], "not_started");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_boundary_plan"
            && source["pluginLoaderAllowed"] == false
            && source["dynamicCodeLoadAllowed"] == false
            && source["hostApiStable"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_load_request"
            && source["approved"] == false
            && source["pluginLoaderAllowed"] == false
            && source["sandboxStartAllowed"] == false
            && source["pluginInvocationAllowed"] == false
    }));

    let session = root["pluginHostSession"]
        .as_object()
        .expect("plugin host session must be an object");
    assert_eq!(session["sessionKind"], "planned_plugin_host_session_state");
    assert_eq!(session["lifecycleState"], "not_started");
    assert_eq!(session["loadState"], "not_loaded");
    assert_eq!(session["sandboxState"], "not_started");
    assert_eq!(session["runtimeState"], "not_started");
    assert_eq!(session["invocationState"], "not_invoked");
    assert_eq!(session["summaryOnly"], true);
    assert_eq!(session["approvalRequired"], true);
    assert_eq!(session["hostSessionOpen"], false);
    assert_eq!(session["loaderStarted"], false);
    assert_eq!(session["runtimeStarted"], false);
    assert_eq!(session["sandboxStarted"], false);
    assert_eq!(session["hostApiBound"], false);
    assert_eq!(session["capabilityDispatchStarted"], false);
    assert_eq!(session["pluginCodeLoaded"], false);
    assert_eq!(session["dynamicLibrariesLoaded"], false);
    assert_eq!(session["packageInstalled"], false);
    assert_eq!(session["manifestReaderCalled"], false);
    assert_eq!(session["validatorCommandCalled"], false);
    assert_eq!(session["permissionExecutorCalled"], false);
    assert_eq!(session["inputReaderCalled"], false);
    assert_eq!(session["traceImporterCalled"], false);
    assert_eq!(session["pluginInvocationStarted"], false);
    assert_eq!(session["commandExecutionAttempted"], false);
    assert_eq!(session["localFileReadAttempted"], false);
    assert_eq!(session["repositoryReadAttempted"], false);
    assert_eq!(session["artifactReadAttempted"], false);
    assert_eq!(session["artifactWriteAttempted"], false);
    assert_eq!(session["reportWriteAttempted"], false);
    assert_eq!(session["providerCallAttempted"], false);
    assert_eq!(session["networkCallAttempted"], false);
    assert_eq!(session["hardwareAccessAttempted"], false);
    assert_eq!(session["modelLoadAttempted"], false);

    let sandbox = root["sandboxPolicy"]
        .as_object()
        .expect("sandbox policy must be an object");
    assert_eq!(sandbox["state"], "not_started");
    assert_eq!(sandbox["sandboxRequired"], true);
    assert_eq!(sandbox["sandboxStartAllowed"], false);
    assert_eq!(sandbox["processIsolationStarted"], false);
    assert_eq!(sandbox["filesystemMountAllowed"], false);
    assert_eq!(sandbox["networkAllowed"], false);
    assert_eq!(sandbox["environmentPassed"], false);
    assert_eq!(sandbox["ipcAllowed"], false);
    assert_eq!(sandbox["permissionProfileApplied"], false);

    let runtime = root["runtimePolicy"]
        .as_object()
        .expect("runtime policy must be an object");
    assert_eq!(runtime["state"], "not_started");
    assert_eq!(runtime["pluginRuntimeStartAllowed"], false);
    assert_eq!(runtime["dynamicCodeLoadAllowed"], false);
    assert_eq!(runtime["packageInstallAllowed"], false);
    assert_eq!(runtime["untrustedExecutionAllowed"], false);
    assert_eq!(runtime["commandExecutionAllowed"], false);
    assert_eq!(runtime["hostApiBindAllowed"], false);
    assert_eq!(runtime["capabilityDispatchAllowed"], false);
    assert_eq!(runtime["pluginInvocationAllowed"], false);

    let audit = root["auditPolicy"]
        .as_object()
        .expect("audit policy must be an object");
    assert_eq!(audit["summaryOnly"], true);
    assert_eq!(audit["auditLoggerAllowed"], false);
    assert_eq!(audit["auditPersistenceAllowed"], false);
    assert_eq!(audit["pathEchoAllowed"], false);
    assert_eq!(audit["stdoutIncluded"], false);
    assert_eq!(audit["stderrIncluded"], false);
    assert_eq!(audit["rawLogsIncluded"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["pluginHostSessionStateFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginSandboxImplemented"], false);
    assert_eq!(safety["pluginHostSessionStarted"], false);
    assert_eq!(safety["pluginHostApiBound"], false);
    assert_eq!(safety["capabilityDispatchImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["inputReaderImplemented"], false);
    assert_eq!(safety["traceImporterImplemented"], false);
    assert_eq!(safety["manifestReaderImplemented"], false);
    assert_eq!(safety["validatorCommandImplemented"], false);
    assert_eq!(safety["pluginInvocationPathImplemented"], false);
    assert_eq!(safety["pluginInvocationAttempted"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["reportWriterImplemented"], false);
    assert_eq!(safety["auditLoggerImplemented"], false);
    assert_eq!(safety["auditPersistence"], false);
    assert_eq!(safety["packageInstall"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["dynamicCodeLoad"], false);
    assert_eq!(safety["untrustedExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["launcherExecution"], false);
    assert_eq!(safety["editorExecution"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["manifestContentIncluded"], false);
    assert_eq!(safety["packageContentIncluded"], false);
    assert_eq!(safety["sourceCodeIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["telemetry"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["compatibilityClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
}

#[test]
fn plugin_invocation_request_example_keeps_invocation_blocked_boundary() {
    let value: serde_json::Value = parse_example("plugin-invocation-request.example.json");
    let root = value
        .as_object()
        .expect("plugin invocation request must be an object");

    assert_eq!(
        root["schemaVersion"],
        "pccx.lab.plugin-invocation-request.v0"
    );
    assert_eq!(root["requestState"], "blocked_by_policy");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "disabled");

    let refs = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_load_request"
            && source["approved"] == false
            && source["pluginLoaderAllowed"] == false
            && source["pluginInvocationAllowed"] == false
    }));
    assert!(refs.iter().any(|source| {
        source["refId"] == "plugin_host_session_state"
            && source["hostSessionOpen"] == false
            && source["hostApiBindAllowed"] == false
            && source["capabilityDispatchAllowed"] == false
            && source["pluginInvocationAllowed"] == false
    }));

    let request = root["invocationRequest"]
        .as_object()
        .expect("invocation request must be an object");
    assert_eq!(request["requestKind"], "planned_plugin_invocation_gate");
    assert_eq!(request["summaryOnly"], true);
    assert_eq!(request["approvalRequired"], true);
    assert_eq!(request["approved"], false);
    assert_eq!(request["inputRefOnly"], true);
    assert_eq!(request["pathEchoAllowed"], false);
    assert_eq!(request["privatePathEchoAllowed"], false);
    assert_eq!(request["localFileReadAllowed"], false);
    assert_eq!(request["repositoryReadAllowed"], false);
    assert_eq!(request["rawTraceReadAllowed"], false);
    assert_eq!(request["rawReportReadAllowed"], false);
    assert_eq!(request["artifactReadAllowed"], false);
    assert_eq!(request["commandExecutionAllowed"], false);
    assert_eq!(request["shellExecutionAllowed"], false);
    assert_eq!(request["runtimeExecutionAllowed"], false);
    assert_eq!(request["pluginLoaderAllowed"], false);
    assert_eq!(request["pluginRuntimeAllowed"], false);
    assert_eq!(request["sandboxStartAllowed"], false);
    assert_eq!(request["hostApiBindAllowed"], false);
    assert_eq!(request["capabilityDispatchAllowed"], false);
    assert_eq!(request["pluginInvocationAllowed"], false);
    assert_eq!(request["packageInstallAllowed"], false);
    assert_eq!(request["dynamicCodeLoadAllowed"], false);
    assert_eq!(request["providerCallAllowed"], false);
    assert_eq!(request["networkCallAllowed"], false);
    assert_eq!(request["launcherExecutionAllowed"], false);
    assert_eq!(request["editorExecutionAllowed"], false);
    assert_eq!(request["hardwareAccessAllowed"], false);
    assert_eq!(request["modelLoadAllowed"], false);

    let decision = root["invocationDecision"]
        .as_object()
        .expect("invocation decision must be an object");
    assert_eq!(decision["state"], "not_invoked");
    assert_eq!(decision["approved"], false);
    assert_eq!(decision["denied"], true);
    assert_eq!(decision["pluginHostSessionStarted"], false);
    assert_eq!(decision["pluginLoaded"], false);
    assert_eq!(decision["sandboxStarted"], false);
    assert_eq!(decision["runtimeStarted"], false);
    assert_eq!(decision["hostApiBound"], false);
    assert_eq!(decision["capabilityDispatchStarted"], false);
    assert_eq!(decision["pluginInvocationStarted"], false);
    assert_eq!(decision["permissionExecutorCalled"], false);
    assert_eq!(decision["inputReaderCalled"], false);
    assert_eq!(decision["traceImporterCalled"], false);
    assert_eq!(decision["commandExecutionAttempted"], false);
    assert_eq!(decision["shellExecutionAttempted"], false);
    assert_eq!(decision["runtimeExecutionAttempted"], false);
    assert_eq!(decision["localFileReadAttempted"], false);
    assert_eq!(decision["repositoryReadAttempted"], false);
    assert_eq!(decision["rawTraceReadAttempted"], false);
    assert_eq!(decision["rawReportReadAttempted"], false);
    assert_eq!(decision["artifactReadAttempted"], false);
    assert_eq!(decision["artifactWriteAttempted"], false);
    assert_eq!(decision["reportWriteAttempted"], false);
    assert_eq!(decision["repositoryMutationAttempted"], false);
    assert_eq!(decision["providerCallAttempted"], false);
    assert_eq!(decision["networkCallAttempted"], false);
    assert_eq!(decision["hardwareAccessAttempted"], false);
    assert_eq!(decision["modelLoadAttempted"], false);

    let context = root["plannedPluginContext"]
        .as_object()
        .expect("planned plugin context must be an object");
    assert_eq!(context["summaryOnly"], true);
    assert_eq!(context["approvedInputReferenceOnly"], true);
    assert_eq!(context["privatePathsIncluded"], false);
    assert_eq!(context["manifestContentIncluded"], false);
    assert_eq!(context["packageContentIncluded"], false);
    assert_eq!(context["sourceCodeIncluded"], false);
    assert_eq!(context["localFileRead"], false);
    assert_eq!(context["repositoryRead"], false);
    assert_eq!(context["rawTraceRead"], false);
    assert_eq!(context["rawReportRead"], false);
    assert_eq!(context["artifactRead"], false);
    assert_eq!(context["stdoutIncluded"], false);
    assert_eq!(context["stderrIncluded"], false);
    assert_eq!(context["rawLogsIncluded"], false);
    assert_eq!(context["modelWeightPathsIncluded"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["pluginInvocationRequestFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginSandboxImplemented"], false);
    assert_eq!(safety["pluginHostSessionStarted"], false);
    assert_eq!(safety["pluginHostApiBound"], false);
    assert_eq!(safety["capabilityDispatchImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["inputReaderImplemented"], false);
    assert_eq!(safety["traceImporterImplemented"], false);
    assert_eq!(safety["manifestReaderImplemented"], false);
    assert_eq!(safety["validatorCommandImplemented"], false);
    assert_eq!(safety["pluginInvocationPathImplemented"], false);
    assert_eq!(safety["pluginInvocationAttempted"], false);
    assert_eq!(safety["pluginCodeLoaded"], false);
    assert_eq!(safety["dynamicLibrariesLoaded"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["repositoryRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["reportWriterImplemented"], false);
    assert_eq!(safety["auditLoggerImplemented"], false);
    assert_eq!(safety["auditPersistence"], false);
    assert_eq!(safety["packageInstall"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["dynamicCodeLoad"], false);
    assert_eq!(safety["untrustedExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["launcherExecution"], false);
    assert_eq!(safety["editorExecution"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["manifestContentIncluded"], false);
    assert_eq!(safety["packageContentIncluded"], false);
    assert_eq!(safety["sourceCodeIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["diagnosticsProduced"], false);
    assert_eq!(safety["panelProduced"], false);
    assert_eq!(safety["reportItemsProduced"], false);
    assert_eq!(safety["telemetry"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["compatibilityClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
}

#[test]
fn plugin_review_packet_example_keeps_summary_only_boundary() {
    let value: serde_json::Value = parse_example("plugin-review-packet.example.json");
    let root = value
        .as_object()
        .expect("plugin review packet must be an object");

    assert_eq!(root["schemaVersion"], "pccx.lab.plugin-review-packet.v0");
    assert_eq!(root["reviewState"], "descriptor_only");
    assert_eq!(root["adapterState"], "not_implemented");
    assert_eq!(root["defaultMode"], "read_only");
    assert_eq!(root["packetKind"], "summary_only_plugin_review_packet");

    let sources = root["sourceBoundaryRefs"]
        .as_array()
        .expect("source boundary refs must be an array");
    assert!(sources.iter().any(|source| {
        source["refId"] == "plugin_permission_model"
            && source["sandboxStartAllowed"] == false
            && source["pluginInvocationAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "plugin_blocked_invocation_result"
            && source["commandExecutionAllowed"] == false
            && source["pluginInvocationAllowed"] == false
    }));
    assert!(sources.iter().any(|source| {
        source["refId"] == "plugin_manifest_validation_result"
            && source["manifestReaderAllowed"] == false
            && source["validatorCommandAllowed"] == false
    }));

    let inputs = root["reviewInputs"]
        .as_array()
        .expect("review inputs must be an array");
    assert!(
        inputs.len() >= 6,
        "plugin review packet should include permission, input, output, blocked result, manifest validation, and audit summaries"
    );
    for input in inputs {
        assert_eq!(input["inputState"], "approved_summary_only");
        assert_eq!(input["summaryOnly"], true);
        assert_eq!(input["approvalRequired"], true);
        assert_eq!(input["localFileRead"], false);
        assert_eq!(input["repositoryRead"], false);
        assert_eq!(input["rawTraceRead"], false);
        assert_eq!(input["rawReportRead"], false);
        assert_eq!(input["artifactRead"], false);
        assert_eq!(input["privatePathEchoAllowed"], false);
        assert_eq!(input["stdoutIncluded"], false);
        assert_eq!(input["stderrIncluded"], false);
        assert_eq!(input["rawLogIncluded"], false);
        assert_eq!(input["artifactPathIncluded"], false);
        assert!(input["fieldDescriptors"].as_array().is_some());
    }

    let policy = root["reviewPolicy"]
        .as_object()
        .expect("review policy must be an object");
    assert_eq!(policy["summaryOnly"], true);
    assert_eq!(policy["approvalRequired"], true);
    assert_eq!(policy["auditRequired"], true);
    assert_eq!(policy["pluginInvocationAllowed"], false);
    assert_eq!(policy["pluginLoaderAllowed"], false);
    assert_eq!(policy["pluginRuntimeAllowed"], false);
    assert_eq!(policy["sandboxStartAllowed"], false);
    assert_eq!(policy["permissionExecutionAllowed"], false);
    assert_eq!(policy["inputReaderAllowed"], false);
    assert_eq!(policy["traceImporterAllowed"], false);
    assert_eq!(policy["manifestReaderAllowed"], false);
    assert_eq!(policy["validatorCommandAllowed"], false);
    assert_eq!(policy["commandExecutionAllowed"], false);
    assert_eq!(policy["localFileReadAllowed"], false);
    assert_eq!(policy["repositoryReadAllowed"], false);
    assert_eq!(policy["rawTraceReadAllowed"], false);
    assert_eq!(policy["rawReportReadAllowed"], false);
    assert_eq!(policy["artifactReadAllowed"], false);
    assert_eq!(policy["artifactWriteAllowed"], false);
    assert_eq!(policy["reportWriteAllowed"], false);
    assert_eq!(policy["repositoryMutationAllowed"], false);
    assert_eq!(policy["packageInstallAllowed"], false);
    assert_eq!(policy["packageDistributionAllowed"], false);
    assert_eq!(policy["marketplaceFlowAllowed"], false);
    assert_eq!(policy["dynamicCodeLoadAllowed"], false);
    assert_eq!(policy["untrustedExecutionAllowed"], false);

    let packet = root["sampleReviewPacket"]
        .as_object()
        .expect("sample review packet must be an object");
    assert_eq!(packet["reviewPacketState"], "summary_only_fixture");
    assert_eq!(packet["summaryOnly"], true);
    assert_eq!(packet["pathIncluded"], false);
    assert_eq!(packet["privatePathsIncluded"], false);
    assert_eq!(packet["stdoutIncluded"], false);
    assert_eq!(packet["stderrIncluded"], false);
    assert_eq!(packet["rawLogsIncluded"], false);
    assert_eq!(packet["artifactPathsIncluded"], false);
    assert_eq!(packet["generatedArtifactsIncluded"], false);
    assert_eq!(packet["rawTraceIncluded"], false);
    assert_eq!(packet["rawReportIncluded"], false);
    assert_eq!(packet["pluginInvoked"], false);
    assert_eq!(packet["manifestRead"], false);
    assert_eq!(packet["packageInstalled"], false);
    assert_eq!(packet["marketplacePublished"], false);

    let sections = packet["reviewSections"]
        .as_array()
        .expect("sample review sections must be an array");
    assert!(sections.iter().all(|section| {
        section["summaryOnly"] == true
            && section["pathIncluded"] == false
            && section["stdoutIncluded"] == false
            && section["stderrIncluded"] == false
            && section["rawLogsIncluded"] == false
            && section["rawTraceIncluded"] == false
            && section["rawReportIncluded"] == false
    }));

    let mutation = root["noMutationEvidence"]
        .as_object()
        .expect("no mutation evidence must be an object");
    assert_eq!(mutation["trackedFileMutationAllowed"], false);
    assert_eq!(mutation["trackedFileDiffCaptured"], false);
    assert_eq!(mutation["artifactReadAllowed"], false);
    assert_eq!(mutation["artifactWriteAllowed"], false);
    assert_eq!(mutation["reportWriteAllowed"], false);
    assert_eq!(mutation["repositoryMutationAllowed"], false);
    assert_eq!(mutation["pluginInvocationAllowed"], false);
    assert_eq!(mutation["commandExecutionAllowed"], false);
    assert_eq!(mutation["marketplacePublicationAllowed"], false);

    let blocked = root["blockedActions"]
        .as_array()
        .expect("blocked actions must be an array");
    for action in [
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
    assert_eq!(safety["pluginReviewPacketFixtureOnly"], true);
    assert_eq!(safety["summaryOnly"], true);
    assert_eq!(safety["pluginRuntimeImplemented"], false);
    assert_eq!(safety["pluginLoaderImplemented"], false);
    assert_eq!(safety["pluginSandboxImplemented"], false);
    assert_eq!(safety["permissionExecutorImplemented"], false);
    assert_eq!(safety["inputReaderImplemented"], false);
    assert_eq!(safety["traceImporterImplemented"], false);
    assert_eq!(safety["commandExecution"], false);
    assert_eq!(safety["shellExecution"], false);
    assert_eq!(safety["runtimeExecution"], false);
    assert_eq!(safety["localFileRead"], false);
    assert_eq!(safety["rawTraceRead"], false);
    assert_eq!(safety["rawReportRead"], false);
    assert_eq!(safety["readsArtifacts"], false);
    assert_eq!(safety["writesArtifacts"], false);
    assert_eq!(safety["packageInstall"], false);
    assert_eq!(safety["packageDistribution"], false);
    assert_eq!(safety["marketplaceFlow"], false);
    assert_eq!(safety["dynamicCodeLoad"], false);
    assert_eq!(safety["untrustedExecution"], false);
    assert_eq!(safety["networkCalls"], false);
    assert_eq!(safety["providerCalls"], false);
    assert_eq!(safety["hardwareAccess"], false);
    assert_eq!(safety["kv260Access"], false);
    assert_eq!(safety["fpgaRepoAccess"], false);
    assert_eq!(safety["modelExecution"], false);
    assert_eq!(safety["privatePathsIncluded"], false);
    assert_eq!(safety["secretsIncluded"], false);
    assert_eq!(safety["tokensIncluded"], false);
    assert_eq!(safety["stdoutIncluded"], false);
    assert_eq!(safety["stderrIncluded"], false);
    assert_eq!(safety["rawLogsIncluded"], false);
    assert_eq!(safety["writeBack"], false);
    assert_eq!(safety["repositoryMutation"], false);
    assert_eq!(safety["publicPush"], false);
    assert_eq!(safety["releaseOrTag"], false);
    assert_eq!(safety["stableApiAbiClaim"], false);
    assert_eq!(safety["compatibilityClaim"], false);
    assert_eq!(safety["marketplaceClaim"], false);
}
