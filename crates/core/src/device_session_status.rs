//! Read-only validator for launcher device/session status JSON.
//!
//! This module parses a local JSON document supplied by the caller. It does
//! not execute launcher commands, open serial ports, scan networks, attempt
//! authentication, probe hardware, upload telemetry, or write files.

use serde::Serialize;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::error::Error;
use std::fmt;

pub const LAUNCHER_DEVICE_SESSION_STATUS_SCHEMA_VERSION: &str = "pccx.deviceSessionStatus.v0";
pub const DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION: &str =
    "pccx.lab.deviceSessionStatusValidation.v0";

const REQUIRED_STATUS_FIELDS: &[&str] = &[
    "schemaVersion",
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
    "statusPanel",
    "discoveryPaths",
    "connectionLaunchFlow",
    "errorTaxonomy",
    "pccxLabDiagnostics",
    "safetyFlags",
    "limitations",
    "issueRefs",
];

const PANEL_ROW_FIELDS: &[&str] = &["rowId", "label", "state", "summary", "nextAction"];

const DISCOVERY_PATH_FIELDS: &[&str] = &[
    "pathId",
    "transport",
    "state",
    "summary",
    "suggestedUserAction",
];

const FLOW_STEP_FIELDS: &[&str] = &[
    "stepId",
    "order",
    "stage",
    "state",
    "userAction",
    "launcherAction",
    "statusPanelUpdate",
    "sideEffectPolicy",
];

const ERROR_FIELDS: &[&str] = &[
    "errorId",
    "stage",
    "severity",
    "state",
    "userMessage",
    "suggestedRemediation",
    "claimBoundary",
];

const REQUIRED_PANEL_ROWS: &[&str] = &[
    "device_connection",
    "model_load",
    "session_activity",
    "pccx_lab_diagnostics",
    "runtime_readiness",
];

const TRANSPORT_VALUES: &[&str] = &["usb_serial", "network_host", "serial_console"];
const ERROR_SEVERITY_VALUES: &[&str] = &["info", "warning", "blocked", "error", "placeholder"];

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DeviceSessionStatusSummary {
    pub schema_version: String,
    pub tool: String,
    pub valid: bool,
    pub status_schema_version: String,
    pub status_id: String,
    pub target_device: String,
    pub target_board: String,
    pub target_model: String,
    pub status_answer: String,
    pub connection_state: String,
    pub discovery_state: String,
    pub authentication_state: String,
    pub runtime_state: String,
    pub model_load_state: String,
    pub session_state: String,
    pub log_stream_state: String,
    pub diagnostics_state: String,
    pub readiness_state: String,
    pub status_panel_rows: BTreeMap<String, String>,
    pub discovery_path_count: usize,
    pub flow_step_count: usize,
    pub error_count: usize,
    pub read_only_flags: DeviceSessionReadOnlyFlags,
    pub limitations: Vec<String>,
    pub issue_refs: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DeviceSessionReadOnlyFlags {
    pub no_artifact_writes: bool,
    pub no_hardware_access: bool,
    pub no_serial_access: bool,
    pub no_network_access: bool,
    pub no_network_scan: bool,
    pub no_ssh_execution: bool,
    pub no_authentication_attempt: bool,
    pub no_runtime_execution: bool,
    pub no_model_load: bool,
    pub no_model_execution: bool,
    pub no_provider_calls: bool,
    pub no_telemetry: bool,
    pub no_upload: bool,
    pub no_write_back: bool,
    pub no_pccx_lab_execution: bool,
    pub no_systemverilog_ide_execution: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeviceSessionStatusError {
    message: String,
}

impl DeviceSessionStatusError {
    fn invalid(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for DeviceSessionStatusError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl Error for DeviceSessionStatusError {}

pub fn validate_device_session_status_json(
    text: &str,
) -> Result<DeviceSessionStatusSummary, DeviceSessionStatusError> {
    validate_text_safety(text)?;

    let value: Value = serde_json::from_str(text)
        .map_err(|_| DeviceSessionStatusError::invalid("invalid device/session status JSON"))?;
    let root = object(&value, "device/session status")?;

    for field in REQUIRED_STATUS_FIELDS {
        field_value(root, field)?;
    }

    ensure_string_value(
        &value,
        &["schemaVersion"],
        LAUNCHER_DEVICE_SESSION_STATUS_SCHEMA_VERSION,
    )?;

    let status_panel_rows = validate_status_panel(&value)?;
    let discovery_path_count = validate_discovery_paths(&value)?;
    let flow_step_count = validate_flow_steps(&value)?;
    let error_count = validate_error_taxonomy(&value)?;
    validate_pccx_lab_diagnostics(&value)?;
    let read_only_flags = validate_read_only_flags(&value)?;

    let limitations = string_array_path(&value, &["limitations"])?;
    let issue_refs = string_array_path(&value, &["issueRefs"])?;

    Ok(DeviceSessionStatusSummary {
        schema_version: DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION.to_string(),
        tool: "pccx-lab".to_string(),
        valid: true,
        status_schema_version: string_path(&value, &["schemaVersion"])?.to_string(),
        status_id: string_path(&value, &["statusId"])?.to_string(),
        target_device: string_path(&value, &["targetDevice"])?.to_string(),
        target_board: string_path(&value, &["targetBoard"])?.to_string(),
        target_model: string_path(&value, &["targetModel"])?.to_string(),
        status_answer: string_path(&value, &["statusAnswer"])?.to_string(),
        connection_state: string_path(&value, &["connectionState"])?.to_string(),
        discovery_state: string_path(&value, &["discoveryState"])?.to_string(),
        authentication_state: string_path(&value, &["authenticationState"])?.to_string(),
        runtime_state: string_path(&value, &["runtimeState"])?.to_string(),
        model_load_state: string_path(&value, &["modelLoadState"])?.to_string(),
        session_state: string_path(&value, &["sessionState"])?.to_string(),
        log_stream_state: string_path(&value, &["logStreamState"])?.to_string(),
        diagnostics_state: string_path(&value, &["diagnosticsState"])?.to_string(),
        readiness_state: string_path(&value, &["readinessState"])?.to_string(),
        status_panel_rows,
        discovery_path_count,
        flow_step_count,
        error_count,
        read_only_flags,
        limitations,
        issue_refs,
    })
}

pub fn device_session_status_summary_json_pretty(
    summary: &DeviceSessionStatusSummary,
) -> serde_json::Result<String> {
    serde_json::to_string_pretty(summary)
}

pub fn device_session_status_error_json_pretty(message: &str) -> String {
    serde_json::to_string_pretty(&json!({
        "schemaVersion": DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION,
        "tool": "pccx-lab",
        "valid": false,
        "error": message,
    }))
    .unwrap_or_else(|_| "{\"valid\":false}".to_string())
}

fn validate_text_safety(text: &str) -> Result<(), DeviceSessionStatusError> {
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
            return Err(DeviceSessionStatusError::invalid(
                "device/session status contains a forbidden private data marker",
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
        "bitstream ready",
        "autonomous coding system",
        "claude directly controls",
        "gpt directly controls",
    ] {
        if lower.contains(marker) {
            return Err(DeviceSessionStatusError::invalid(
                "device/session status contains an unsupported public claim marker",
            ));
        }
    }

    Ok(())
}

fn validate_status_panel(
    value: &Value,
) -> Result<BTreeMap<String, String>, DeviceSessionStatusError> {
    let mut rows = BTreeMap::new();
    for item in array_path(value, &["statusPanel"])? {
        let row = object(item, "statusPanel row")?;
        for field in PANEL_ROW_FIELDS {
            string_field(row, field)?;
        }
        let row_id = string_field(row, "rowId")?;
        let state = string_field(row, "state")?;
        rows.insert(row_id.to_string(), state.to_string());
    }

    for row_id in REQUIRED_PANEL_ROWS {
        if !rows.contains_key(*row_id) {
            return Err(DeviceSessionStatusError::invalid(format!(
                "missing status panel row {row_id}"
            )));
        }
    }

    Ok(rows)
}

fn validate_discovery_paths(value: &Value) -> Result<usize, DeviceSessionStatusError> {
    let paths = array_path(value, &["discoveryPaths"])?;
    if paths.is_empty() {
        return Err(DeviceSessionStatusError::invalid(
            "discoveryPaths must contain at least one item",
        ));
    }

    for item in paths {
        let path = object(item, "discovery path")?;
        for field in DISCOVERY_PATH_FIELDS {
            string_field(path, field)?;
        }
        ensure_allowed(
            "discoveryPaths.transport",
            string_field(path, "transport")?,
            TRANSPORT_VALUES,
        )?;
    }

    Ok(paths.len())
}

fn validate_flow_steps(value: &Value) -> Result<usize, DeviceSessionStatusError> {
    let steps = array_path(value, &["connectionLaunchFlow"])?;
    if steps.is_empty() {
        return Err(DeviceSessionStatusError::invalid(
            "connectionLaunchFlow must contain at least one item",
        ));
    }

    for (index, item) in steps.iter().enumerate() {
        let step = object(item, "connection flow step")?;
        for field in FLOW_STEP_FIELDS {
            field_value(step, field)?;
        }
        for field in [
            "stepId",
            "stage",
            "state",
            "userAction",
            "launcherAction",
            "statusPanelUpdate",
            "sideEffectPolicy",
        ] {
            string_field(step, field)?;
        }
        let order = integer_field(step, "order")?;
        if order != (index + 1) as i64 {
            return Err(DeviceSessionStatusError::invalid(
                "connectionLaunchFlow order must be contiguous from 1",
            ));
        }
    }

    Ok(steps.len())
}

fn validate_error_taxonomy(value: &Value) -> Result<usize, DeviceSessionStatusError> {
    let errors = array_path(value, &["errorTaxonomy"])?;
    if errors.is_empty() {
        return Err(DeviceSessionStatusError::invalid(
            "errorTaxonomy must contain at least one item",
        ));
    }

    for item in errors {
        let error = object(item, "error taxonomy item")?;
        for field in ERROR_FIELDS {
            string_field(error, field)?;
        }
        ensure_allowed(
            "errorTaxonomy.severity",
            string_field(error, "severity")?,
            ERROR_SEVERITY_VALUES,
        )?;
    }

    Ok(errors.len())
}

fn validate_pccx_lab_diagnostics(value: &Value) -> Result<(), DeviceSessionStatusError> {
    ensure_string_value(value, &["pccxLabDiagnostics", "state"], "planned")?;
    ensure_string_value(value, &["pccxLabDiagnostics", "mode"], "read_only_handoff")?;
    ensure_false(value, &["pccxLabDiagnostics", "automaticUpload"])?;
    ensure_false(value, &["pccxLabDiagnostics", "writeBack"])?;
    ensure_false(value, &["pccxLabDiagnostics", "executesPccxLab"])?;
    Ok(())
}

fn validate_read_only_flags(
    value: &Value,
) -> Result<DeviceSessionReadOnlyFlags, DeviceSessionStatusError> {
    ensure_true(value, &["safetyFlags", "dataOnly"])?;
    ensure_true(value, &["safetyFlags", "readOnly"])?;
    ensure_true(value, &["safetyFlags", "deterministic"])?;

    for path in [
        &["safetyFlags", "writesArtifacts"][..],
        &["safetyFlags", "touchesHardware"][..],
        &["safetyFlags", "kv260Access"][..],
        &["safetyFlags", "opensSerialPort"][..],
        &["safetyFlags", "serialWrites"][..],
        &["safetyFlags", "networkCalls"][..],
        &["safetyFlags", "networkScan"][..],
        &["safetyFlags", "sshExecution"][..],
        &["safetyFlags", "authenticationAttempt"][..],
        &["safetyFlags", "runtimeExecution"][..],
        &["safetyFlags", "modelLoaded"][..],
        &["safetyFlags", "modelExecution"][..],
        &["safetyFlags", "modelWeightPathsIncluded"][..],
        &["safetyFlags", "privatePathsIncluded"][..],
        &["safetyFlags", "secretsIncluded"][..],
        &["safetyFlags", "tokensIncluded"][..],
        &["safetyFlags", "generatedBlobsIncluded"][..],
        &["safetyFlags", "hardwareDumpsIncluded"][..],
        &["safetyFlags", "providerCalls"][..],
        &["safetyFlags", "telemetry"][..],
        &["safetyFlags", "automaticUpload"][..],
        &["safetyFlags", "writeBack"][..],
        &["safetyFlags", "executesPccxLab"][..],
        &["safetyFlags", "executesSystemverilogIde"][..],
        &["safetyFlags", "firmwareFlashing"][..],
        &["safetyFlags", "packageInstallation"][..],
        &["safetyFlags", "stableApiAbiClaim"][..],
    ] {
        ensure_false(value, path)?;
    }

    Ok(DeviceSessionReadOnlyFlags {
        no_artifact_writes: true,
        no_hardware_access: true,
        no_serial_access: true,
        no_network_access: true,
        no_network_scan: true,
        no_ssh_execution: true,
        no_authentication_attempt: true,
        no_runtime_execution: true,
        no_model_load: true,
        no_model_execution: true,
        no_provider_calls: true,
        no_telemetry: true,
        no_upload: true,
        no_write_back: true,
        no_pccx_lab_execution: true,
        no_systemverilog_ide_execution: true,
    })
}

fn ensure_allowed(
    context: &str,
    value: &str,
    allowed: &[&str],
) -> Result<(), DeviceSessionStatusError> {
    if allowed.contains(&value) {
        Ok(())
    } else {
        Err(DeviceSessionStatusError::invalid(format!(
            "unsupported value for {context}"
        )))
    }
}

fn ensure_string_value(
    value: &Value,
    path: &[&str],
    expected: &str,
) -> Result<(), DeviceSessionStatusError> {
    let actual = string_path(value, path)?;
    if actual == expected {
        Ok(())
    } else {
        Err(DeviceSessionStatusError::invalid(format!(
            "unexpected value for {}",
            path.join(".")
        )))
    }
}

fn ensure_true(value: &Value, path: &[&str]) -> Result<(), DeviceSessionStatusError> {
    if bool_path(value, path)? {
        Ok(())
    } else {
        Err(DeviceSessionStatusError::invalid(format!(
            "{} must be true",
            path.join(".")
        )))
    }
}

fn ensure_false(value: &Value, path: &[&str]) -> Result<(), DeviceSessionStatusError> {
    if !bool_path(value, path)? {
        Ok(())
    } else {
        Err(DeviceSessionStatusError::invalid(format!(
            "{} must be false",
            path.join(".")
        )))
    }
}

fn object<'a>(
    value: &'a Value,
    context: &str,
) -> Result<&'a Map<String, Value>, DeviceSessionStatusError> {
    value
        .as_object()
        .ok_or_else(|| DeviceSessionStatusError::invalid(format!("{context} must be an object")))
}

fn field_value<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a Value, DeviceSessionStatusError> {
    object
        .get(field)
        .ok_or_else(|| DeviceSessionStatusError::invalid(format!("missing required field {field}")))
}

fn string_field<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a str, DeviceSessionStatusError> {
    field_value(object, field)?
        .as_str()
        .ok_or_else(|| DeviceSessionStatusError::invalid(format!("{field} must be a string")))
}

fn integer_field(
    object: &Map<String, Value>,
    field: &str,
) -> Result<i64, DeviceSessionStatusError> {
    field_value(object, field)?
        .as_i64()
        .ok_or_else(|| DeviceSessionStatusError::invalid(format!("{field} must be an integer")))
}

fn value_path<'a>(value: &'a Value, path: &[&str]) -> Result<&'a Value, DeviceSessionStatusError> {
    let mut current = value;
    for part in path {
        current = current
            .as_object()
            .and_then(|object| object.get(*part))
            .ok_or_else(|| {
                DeviceSessionStatusError::invalid(format!(
                    "missing required field {}",
                    path.join(".")
                ))
            })?;
    }
    Ok(current)
}

fn string_path<'a>(value: &'a Value, path: &[&str]) -> Result<&'a str, DeviceSessionStatusError> {
    value_path(value, path)?.as_str().ok_or_else(|| {
        DeviceSessionStatusError::invalid(format!("{} must be a string", path.join(".")))
    })
}

fn bool_path(value: &Value, path: &[&str]) -> Result<bool, DeviceSessionStatusError> {
    value_path(value, path)?.as_bool().ok_or_else(|| {
        DeviceSessionStatusError::invalid(format!("{} must be a boolean", path.join(".")))
    })
}

fn array_path<'a>(
    value: &'a Value,
    path: &[&str],
) -> Result<&'a Vec<Value>, DeviceSessionStatusError> {
    value_path(value, path)?.as_array().ok_or_else(|| {
        DeviceSessionStatusError::invalid(format!("{} must be an array", path.join(".")))
    })
}

fn string_array_path(
    value: &Value,
    path: &[&str],
) -> Result<Vec<String>, DeviceSessionStatusError> {
    array_path(value, path)?
        .iter()
        .map(|item| {
            item.as_str().map(str::to_string).ok_or_else(|| {
                DeviceSessionStatusError::invalid(format!(
                    "{} must contain only strings",
                    path.join(".")
                ))
            })
        })
        .collect()
}
