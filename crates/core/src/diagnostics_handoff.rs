//! Read-only validator for launcher diagnostics handoff JSON.
//!
//! This module parses a local JSON document supplied by the caller. It does
//! not execute launcher commands, contact providers, probe hardware, upload
//! telemetry, load plugins, or write files.

use serde::Serialize;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::error::Error;
use std::fmt;

pub const LAUNCHER_HANDOFF_SCHEMA_VERSION: &str = "pccx.diagnosticsHandoff.v0";
pub const HANDOFF_VALIDATION_SCHEMA_VERSION: &str = "pccx.lab.diagnosticsHandoffValidation.v0";

const REQUIRED_HANDOFF_FIELDS: &[&str] = &[
    "schemaVersion",
    "handoffId",
    "handoffKind",
    "producer",
    "consumer",
    "createdAt",
    "sessionId",
    "launcherStatusRef",
    "modelDescriptorRef",
    "runtimeDescriptorRef",
    "targetKind",
    "targetDevice",
    "diagnostics",
    "evidenceRefs",
    "artifactRefs",
    "privacyFlags",
    "safetyFlags",
    "transport",
    "limitations",
    "issueRefs",
];

const REQUIRED_DIAGNOSTIC_FIELDS: &[&str] = &[
    "diagnosticId",
    "severity",
    "category",
    "source",
    "title",
    "summary",
    "relatedContractRefs",
    "suggestedNextAction",
    "evidenceState",
    "redactionState",
];

const SEVERITY_VALUES: &[&str] = &["info", "warning", "blocked", "error"];

const CATEGORY_VALUES: &[&str] = &[
    "configuration",
    "model_descriptor",
    "runtime_descriptor",
    "target_device",
    "evidence",
    "safety",
    "diagnostics_handoff",
];

const TRANSPORT_VALUES: &[&str] = &[
    "json_file",
    "stdout_json",
    "read_only_local_artifact_reference",
];

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DiagnosticsHandoffSummary {
    pub schema_version: String,
    pub tool: String,
    pub valid: bool,
    pub handoff_schema_version: String,
    pub handoff_id: String,
    pub handoff_kind: String,
    pub producer_id: String,
    pub consumer_id: String,
    pub target_kind: String,
    pub diagnostic_count: usize,
    pub diagnostics_by_severity: BTreeMap<String, usize>,
    pub diagnostics_by_category: BTreeMap<String, usize>,
    pub read_only_flags: ReadOnlyFlags,
    pub descriptor_refs: DescriptorRefs,
    pub transport_kinds: Vec<String>,
    pub limitations: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReadOnlyFlags {
    pub no_user_data_upload: bool,
    pub no_telemetry: bool,
    pub no_automatic_upload: bool,
    pub no_write_back: bool,
    pub no_runtime_execution: bool,
    pub no_hardware_access: bool,
    pub no_pccx_lab_execution: bool,
    pub no_launcher_execution: bool,
    pub no_provider_calls: bool,
    pub no_network_calls: bool,
    pub no_mcp: bool,
    pub no_lsp: bool,
    pub no_marketplace_flow: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DescriptorRefs {
    pub launcher_status_operation_id: String,
    pub model_id: String,
    pub runtime_id: String,
    pub descriptor_policy: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DiagnosticsHandoffError {
    message: String,
}

impl DiagnosticsHandoffError {
    fn invalid(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for DiagnosticsHandoffError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl Error for DiagnosticsHandoffError {}

pub fn validate_diagnostics_handoff_json(
    text: &str,
) -> Result<DiagnosticsHandoffSummary, DiagnosticsHandoffError> {
    validate_text_safety(text)?;

    let value: Value = serde_json::from_str(text)
        .map_err(|_| DiagnosticsHandoffError::invalid("invalid diagnostics handoff JSON"))?;
    let root = object(&value, "handoff")?;

    for field in REQUIRED_HANDOFF_FIELDS {
        field_value(root, field)?;
    }

    ensure_string_value(&value, &["schemaVersion"], LAUNCHER_HANDOFF_SCHEMA_VERSION)?;
    ensure_string_value(&value, &["handoffKind"], "read_only_handoff")?;
    ensure_string_value(&value, &["producer", "role"], "launcher_generated_summary")?;
    ensure_string_value(&value, &["consumer", "role"], "pccx_lab_future_consumer")?;
    ensure_string_value(
        &value,
        &["targetDevice", "accessState"],
        "no_hardware_access",
    )?;

    let (diagnostic_count, diagnostics_by_severity, diagnostics_by_category) =
        validate_diagnostics(&value)?;
    validate_descriptor_refs(&value)?;
    validate_artifact_refs(&value)?;
    let transport_kinds = validate_transport(&value)?;
    let read_only_flags = validate_read_only_flags(&value)?;

    let limitations = array_path(&value, &["limitations"])?
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_string)
                .ok_or_else(|| DiagnosticsHandoffError::invalid("limitations must be strings"))
        })
        .collect::<Result<Vec<_>, _>>()?;

    Ok(DiagnosticsHandoffSummary {
        schema_version: HANDOFF_VALIDATION_SCHEMA_VERSION.to_string(),
        tool: "pccx-lab".to_string(),
        valid: true,
        handoff_schema_version: string_path(&value, &["schemaVersion"])?.to_string(),
        handoff_id: string_path(&value, &["handoffId"])?.to_string(),
        handoff_kind: string_path(&value, &["handoffKind"])?.to_string(),
        producer_id: string_path(&value, &["producer", "id"])?.to_string(),
        consumer_id: string_path(&value, &["consumer", "id"])?.to_string(),
        target_kind: string_path(&value, &["targetKind"])?.to_string(),
        diagnostic_count,
        diagnostics_by_severity,
        diagnostics_by_category,
        read_only_flags,
        descriptor_refs: DescriptorRefs {
            launcher_status_operation_id: string_path(
                &value,
                &["launcherStatusRef", "operationId"],
            )?
            .to_string(),
            model_id: string_path(&value, &["modelDescriptorRef", "modelId"])?.to_string(),
            runtime_id: string_path(&value, &["runtimeDescriptorRef", "runtimeId"])?.to_string(),
            descriptor_policy: string_path(&value, &["safetyFlags", "descriptorPolicy"])?
                .to_string(),
        },
        transport_kinds,
        limitations,
    })
}

pub fn diagnostics_handoff_summary_json_pretty(
    summary: &DiagnosticsHandoffSummary,
) -> serde_json::Result<String> {
    serde_json::to_string_pretty(summary)
}

pub fn diagnostics_handoff_error_json_pretty(message: &str) -> String {
    serde_json::to_string_pretty(&json!({
        "schemaVersion": HANDOFF_VALIDATION_SCHEMA_VERSION,
        "tool": "pccx-lab",
        "valid": false,
        "error": message,
    }))
    .unwrap_or_else(|_| "{\"valid\":false}".to_string())
}

fn validate_text_safety(text: &str) -> Result<(), DiagnosticsHandoffError> {
    let lower = text.to_lowercase();

    for marker in [
        "/home/",
        "/users/",
        "c:\\users\\",
        "api_key",
        "authorization:",
        "bearer ",
        "client_secret",
        "password:",
        "private_key",
        "ghp_",
        "github_pat_",
        "sk-",
        "begin rsa private key",
        "begin openssh private key",
        ".gguf",
        ".safetensors",
        ".ckpt",
        ".pt",
        ".pth",
        ".onnx",
    ] {
        if lower.contains(marker) {
            return Err(DiagnosticsHandoffError::invalid(
                "diagnostics handoff contains a forbidden private data marker",
            ));
        }
    }

    for marker in [
        "production-ready",
        "marketplace-ready",
        "stable api",
        "stable abi",
        "kv260 inference works",
        "gemma 3n e4b runs on kv260",
        "20 tok/s achieved",
        "timing closed",
        concat!("autonomous ", "coding system"),
        "claude directly controls",
        "gpt directly controls",
    ] {
        if lower.contains(marker) {
            return Err(DiagnosticsHandoffError::invalid(
                "diagnostics handoff contains an unsupported public claim marker",
            ));
        }
    }

    Ok(())
}

fn validate_diagnostics(
    value: &Value,
) -> Result<(usize, BTreeMap<String, usize>, BTreeMap<String, usize>), DiagnosticsHandoffError> {
    let diagnostics = array_path(value, &["diagnostics"])?;
    if diagnostics.is_empty() {
        return Err(DiagnosticsHandoffError::invalid(
            "diagnostics must contain at least one item",
        ));
    }

    let mut severity_counts = zero_counts(SEVERITY_VALUES);
    let mut category_counts = zero_counts(CATEGORY_VALUES);

    for diagnostic in diagnostics {
        let item = object(diagnostic, "diagnostic item")?;
        for field in REQUIRED_DIAGNOSTIC_FIELDS {
            field_value(item, field)?;
        }

        let severity = string_field(item, "severity")?;
        ensure_allowed("diagnostics.severity", severity, SEVERITY_VALUES)?;
        *severity_counts.get_mut(severity).unwrap() += 1;

        let category = string_field(item, "category")?;
        ensure_allowed("diagnostics.category", category, CATEGORY_VALUES)?;
        *category_counts.get_mut(category).unwrap() += 1;

        let refs = item
            .get("relatedContractRefs")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                DiagnosticsHandoffError::invalid("relatedContractRefs must be an array")
            })?;
        if refs.is_empty() {
            return Err(DiagnosticsHandoffError::invalid(
                "relatedContractRefs must not be empty",
            ));
        }
    }

    Ok((diagnostics.len(), severity_counts, category_counts))
}

fn validate_descriptor_refs(value: &Value) -> Result<(), DiagnosticsHandoffError> {
    ensure_string_value(
        value,
        &["launcherStatusRef", "operationId"],
        "pccxlab.diagnostics.handoff",
    )?;
    ensure_string_value(
        value,
        &["launcherStatusRef", "referenceKind"],
        "descriptor_ref_only",
    )?;
    ensure_string_value(
        value,
        &["launcherStatusRef", "coupling"],
        "data_reference_only",
    )?;
    ensure_string_value(
        value,
        &["modelDescriptorRef", "referenceKind"],
        "descriptor_ref_only",
    )?;
    ensure_string_value(
        value,
        &["runtimeDescriptorRef", "referenceKind"],
        "descriptor_ref_only",
    )?;
    string_path(value, &["modelDescriptorRef", "modelId"])?;
    string_path(value, &["runtimeDescriptorRef", "runtimeId"])?;
    Ok(())
}

fn validate_artifact_refs(value: &Value) -> Result<(), DiagnosticsHandoffError> {
    for item in array_path(value, &["artifactRefs"])? {
        let artifact = object(item, "artifactRef")?;
        ensure_string_value_from_object(
            artifact,
            "referenceKind",
            "read_only_local_artifact_reference",
        )?;
        let reference = string_field(artifact, "reference")?;
        if reference.starts_with('/')
            || reference.contains(":\\")
            || reference.starts_with("http://")
            || reference.starts_with("https://")
        {
            return Err(DiagnosticsHandoffError::invalid(
                "artifact references must be read-only relative local references",
            ));
        }
    }
    Ok(())
}

fn validate_transport(value: &Value) -> Result<Vec<String>, DiagnosticsHandoffError> {
    let mut kinds = Vec::new();
    for item in array_path(value, &["transport"])? {
        let transport = object(item, "transport")?;
        let kind = string_field(transport, "transportKind")?;
        ensure_allowed("transport.transportKind", kind, TRANSPORT_VALUES)?;
        ensure_string_value_from_object(transport, "mode", "read_only_handoff")?;
        ensure_string_value_from_object(transport, "execution", "no_pccx_lab_execution")?;
        kinds.push(kind.to_string());
    }
    Ok(kinds)
}

fn validate_read_only_flags(value: &Value) -> Result<ReadOnlyFlags, DiagnosticsHandoffError> {
    ensure_string_value(
        value,
        &["privacyFlags", "uploadPolicy"],
        "no_user_data_upload",
    )?;
    ensure_string_value(value, &["privacyFlags", "telemetryPolicy"], "no_telemetry")?;
    ensure_false(value, &["privacyFlags", "automaticUpload"])?;
    ensure_false(value, &["privacyFlags", "rawFullLogsIncluded"])?;
    ensure_false(value, &["privacyFlags", "userPromptsIncluded"])?;
    ensure_false(value, &["privacyFlags", "userSourceCodeIncluded"])?;
    ensure_false(value, &["privacyFlags", "privatePathsIncluded"])?;
    ensure_false(value, &["privacyFlags", "secretsIncluded"])?;
    ensure_false(value, &["privacyFlags", "tokensIncluded"])?;
    ensure_false(value, &["privacyFlags", "providerConfigsIncluded"])?;
    ensure_false(value, &["privacyFlags", "modelWeightPathsIncluded"])?;
    ensure_false(value, &["privacyFlags", "generatedBlobsIncluded"])?;

    ensure_string_value(value, &["safetyFlags", "contractKind"], "read_only_handoff")?;
    ensure_string_value(
        value,
        &["safetyFlags", "descriptorPolicy"],
        "descriptor_ref_only",
    )?;
    ensure_string_value(
        value,
        &["safetyFlags", "writeBackPolicy"],
        "no_auto_writeback",
    )?;
    ensure_string_value(
        value,
        &["safetyFlags", "runtimePolicy"],
        "no_runtime_execution",
    )?;
    ensure_string_value(
        value,
        &["safetyFlags", "hardwarePolicy"],
        "no_hardware_access",
    )?;
    ensure_true(value, &["safetyFlags", "dataOnly"])?;
    ensure_true(value, &["safetyFlags", "readOnly"])?;
    ensure_false(value, &["safetyFlags", "executesPccxLab"])?;
    ensure_false(value, &["safetyFlags", "executesLauncher"])?;
    ensure_false(value, &["safetyFlags", "runtimeExecution"])?;
    ensure_false(value, &["safetyFlags", "touchesHardware"])?;
    ensure_false(value, &["safetyFlags", "kv260Access"])?;
    ensure_false(value, &["safetyFlags", "modelExecution"])?;
    ensure_false(value, &["safetyFlags", "networkCalls"])?;
    ensure_false(value, &["safetyFlags", "providerCalls"])?;
    ensure_false(value, &["safetyFlags", "shellExecution"])?;
    ensure_false(value, &["safetyFlags", "mcpServerImplemented"])?;
    ensure_false(value, &["safetyFlags", "lspImplemented"])?;
    ensure_false(value, &["safetyFlags", "marketplaceFlow"])?;
    ensure_false(value, &["safetyFlags", "telemetry"])?;
    ensure_false(value, &["safetyFlags", "automaticUpload"])?;
    ensure_false(value, &["safetyFlags", "writeBack"])?;

    Ok(ReadOnlyFlags {
        no_user_data_upload: true,
        no_telemetry: true,
        no_automatic_upload: true,
        no_write_back: true,
        no_runtime_execution: true,
        no_hardware_access: true,
        no_pccx_lab_execution: true,
        no_launcher_execution: true,
        no_provider_calls: true,
        no_network_calls: true,
        no_mcp: true,
        no_lsp: true,
        no_marketplace_flow: true,
    })
}

fn zero_counts(values: &[&str]) -> BTreeMap<String, usize> {
    values
        .iter()
        .map(|value| ((*value).to_string(), 0usize))
        .collect()
}

fn ensure_allowed(
    context: &str,
    value: &str,
    allowed: &[&str],
) -> Result<(), DiagnosticsHandoffError> {
    if allowed.contains(&value) {
        Ok(())
    } else {
        Err(DiagnosticsHandoffError::invalid(format!(
            "unsupported value for {context}"
        )))
    }
}

fn ensure_string_value(
    value: &Value,
    path: &[&str],
    expected: &str,
) -> Result<(), DiagnosticsHandoffError> {
    let actual = string_path(value, path)?;
    if actual == expected {
        Ok(())
    } else {
        Err(DiagnosticsHandoffError::invalid(format!(
            "unexpected value for {}",
            path.join(".")
        )))
    }
}

fn ensure_string_value_from_object(
    object: &Map<String, Value>,
    field: &str,
    expected: &str,
) -> Result<(), DiagnosticsHandoffError> {
    let actual = string_field(object, field)?;
    if actual == expected {
        Ok(())
    } else {
        Err(DiagnosticsHandoffError::invalid(format!(
            "unexpected value for {field}"
        )))
    }
}

fn ensure_true(value: &Value, path: &[&str]) -> Result<(), DiagnosticsHandoffError> {
    if bool_path(value, path)? {
        Ok(())
    } else {
        Err(DiagnosticsHandoffError::invalid(format!(
            "{} must be true",
            path.join(".")
        )))
    }
}

fn ensure_false(value: &Value, path: &[&str]) -> Result<(), DiagnosticsHandoffError> {
    if !bool_path(value, path)? {
        Ok(())
    } else {
        Err(DiagnosticsHandoffError::invalid(format!(
            "{} must be false",
            path.join(".")
        )))
    }
}

fn object<'a>(
    value: &'a Value,
    context: &str,
) -> Result<&'a Map<String, Value>, DiagnosticsHandoffError> {
    value
        .as_object()
        .ok_or_else(|| DiagnosticsHandoffError::invalid(format!("{context} must be an object")))
}

fn field_value<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a Value, DiagnosticsHandoffError> {
    object
        .get(field)
        .ok_or_else(|| DiagnosticsHandoffError::invalid(format!("missing required field {field}")))
}

fn string_field<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a str, DiagnosticsHandoffError> {
    field_value(object, field)?
        .as_str()
        .ok_or_else(|| DiagnosticsHandoffError::invalid(format!("{field} must be a string")))
}

fn value_path<'a>(value: &'a Value, path: &[&str]) -> Result<&'a Value, DiagnosticsHandoffError> {
    let mut current = value;
    for part in path {
        current = current
            .as_object()
            .and_then(|object| object.get(*part))
            .ok_or_else(|| {
                DiagnosticsHandoffError::invalid(format!(
                    "missing required field {}",
                    path.join(".")
                ))
            })?;
    }
    Ok(current)
}

fn string_path<'a>(value: &'a Value, path: &[&str]) -> Result<&'a str, DiagnosticsHandoffError> {
    value_path(value, path)?.as_str().ok_or_else(|| {
        DiagnosticsHandoffError::invalid(format!("{} must be a string", path.join(".")))
    })
}

fn bool_path(value: &Value, path: &[&str]) -> Result<bool, DiagnosticsHandoffError> {
    value_path(value, path)?.as_bool().ok_or_else(|| {
        DiagnosticsHandoffError::invalid(format!("{} must be a boolean", path.join(".")))
    })
}

fn array_path<'a>(
    value: &'a Value,
    path: &[&str],
) -> Result<&'a Vec<Value>, DiagnosticsHandoffError> {
    value_path(value, path)?.as_array().ok_or_else(|| {
        DiagnosticsHandoffError::invalid(format!("{} must be an array", path.join(".")))
    })
}
