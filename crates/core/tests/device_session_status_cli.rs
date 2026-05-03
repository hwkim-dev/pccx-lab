// device_session_status_cli — read-only consumer tests for launcher status JSON.
//
// The validator parses local JSON only. It must not execute launcher flows,
// open serial ports, scan networks, authenticate, touch hardware, or write files.

use std::path::{Path, PathBuf};
use std::process::Command;

use pccx_core::{
    device_session_status_summary_json_pretty, validate_device_session_status_json,
    DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION, LAUNCHER_DEVICE_SESSION_STATUS_SCHEMA_VERSION,
};

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pccx-lab"))
}

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn fixture_path() -> PathBuf {
    repo_root().join("docs/examples/launcher-device-session-status.example.json")
}

fn read_fixture() -> String {
    std::fs::read_to_string(fixture_path()).expect("cannot read device/session fixture")
}

fn fixture_value() -> serde_json::Value {
    serde_json::from_str(&read_fixture()).expect("fixture JSON must be valid")
}

fn object_mut(value: &mut serde_json::Value) -> &mut serde_json::Map<String, serde_json::Value> {
    value.as_object_mut().expect("fixture must be an object")
}

#[test]
fn valid_fixture_summary_has_expected_shape() {
    let summary = validate_device_session_status_json(&read_fixture()).unwrap();

    assert_eq!(
        summary.schema_version,
        DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION
    );
    assert_eq!(summary.tool, "pccx-lab");
    assert!(summary.valid);
    assert_eq!(
        summary.status_schema_version,
        LAUNCHER_DEVICE_SESSION_STATUS_SCHEMA_VERSION
    );
    assert_eq!(
        summary.status_id,
        "device_session_status_gemma3n_e4b_kv260_placeholder"
    );
    assert_eq!(summary.target_device, "kv260");
    assert_eq!(summary.target_board, "xilinx_kria_kv260");
    assert_eq!(summary.target_model, "gemma3n-e4b");
    assert_eq!(
        summary.status_answer,
        "device_session_status_placeholder_blocked"
    );
    assert_eq!(summary.connection_state, "not_configured");
    assert_eq!(summary.model_load_state, "not_loaded");
    assert_eq!(summary.session_state, "inactive");
    assert_eq!(summary.diagnostics_state, "available_as_placeholder");
    assert_eq!(summary.readiness_state, "blocked");
    assert_eq!(summary.discovery_path_count, 3);
    assert_eq!(summary.flow_step_count, 8);
    assert_eq!(summary.error_count, 9);
}

#[test]
fn valid_fixture_reports_expected_status_panel_rows() {
    let summary = validate_device_session_status_json(&read_fixture()).unwrap();

    assert_eq!(
        summary.status_panel_rows["device_connection"],
        "not_configured"
    );
    assert_eq!(summary.status_panel_rows["model_load"], "not_loaded");
    assert_eq!(summary.status_panel_rows["session_activity"], "inactive");
    assert_eq!(
        summary.status_panel_rows["pccx_lab_diagnostics"],
        "available_as_placeholder"
    );
    assert_eq!(summary.status_panel_rows["runtime_readiness"], "blocked");
}

#[test]
fn valid_fixture_reports_read_only_boundary_flags() {
    let summary = validate_device_session_status_json(&read_fixture()).unwrap();
    let flags = summary.read_only_flags;

    assert!(flags.no_artifact_writes);
    assert!(flags.no_hardware_access);
    assert!(flags.no_serial_access);
    assert!(flags.no_network_access);
    assert!(flags.no_network_scan);
    assert!(flags.no_ssh_execution);
    assert!(flags.no_authentication_attempt);
    assert!(flags.no_runtime_execution);
    assert!(flags.no_model_load);
    assert!(flags.no_model_execution);
    assert!(flags.no_provider_calls);
    assert!(flags.no_telemetry);
    assert!(flags.no_upload);
    assert!(flags.no_write_back);
    assert!(flags.no_pccx_lab_execution);
    assert!(flags.no_systemverilog_ide_execution);
}

#[test]
fn summary_output_is_deterministic() {
    let summary = validate_device_session_status_json(&read_fixture()).unwrap();
    let first = device_session_status_summary_json_pretty(&summary).unwrap();
    let second = device_session_status_summary_json_pretty(&summary).unwrap();

    assert_eq!(first, second);
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(&first).unwrap()["schemaVersion"],
        DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION
    );
}

#[test]
fn missing_required_field_is_rejected() {
    let mut value = fixture_value();
    object_mut(&mut value).remove("statusPanel");
    let text = serde_json::to_string(&value).unwrap();

    let err = validate_device_session_status_json(&text).unwrap_err();
    assert!(err
        .to_string()
        .contains("missing required field statusPanel"));
}

#[test]
fn missing_required_panel_row_is_rejected() {
    let mut value = fixture_value();
    let rows = value["statusPanel"].as_array_mut().unwrap();
    rows.retain(|row| row["rowId"] != "runtime_readiness");
    let text = serde_json::to_string(&value).unwrap();

    let err = validate_device_session_status_json(&text).unwrap_err();
    assert!(err
        .to_string()
        .contains("missing status panel row runtime_readiness"));
}

#[test]
fn flow_steps_must_have_contiguous_order() {
    let mut value = fixture_value();
    value["connectionLaunchFlow"][0]["order"] = serde_json::Value::from(2);
    let text = serde_json::to_string(&value).unwrap();

    let err = validate_device_session_status_json(&text).unwrap_err();
    assert!(err
        .to_string()
        .contains("connectionLaunchFlow order must be contiguous"));
}

#[test]
fn unsafe_runtime_or_access_flags_are_rejected() {
    let mut value = fixture_value();
    value["safetyFlags"]["runtimeExecution"] = serde_json::Value::Bool(true);
    assert!(validate_device_session_status_json(&serde_json::to_string(&value).unwrap()).is_err());

    let mut value = fixture_value();
    value["safetyFlags"]["opensSerialPort"] = serde_json::Value::Bool(true);
    assert!(validate_device_session_status_json(&serde_json::to_string(&value).unwrap()).is_err());

    let mut value = fixture_value();
    value["pccxLabDiagnostics"]["executesPccxLab"] = serde_json::Value::Bool(true);
    assert!(validate_device_session_status_json(&serde_json::to_string(&value).unwrap()).is_err());
}

#[test]
fn private_paths_secrets_weight_paths_and_claim_markers_are_rejected() {
    let mut private_path = fixture_value();
    private_path["limitations"][0] =
        serde_json::Value::String("/home/user/private.log".to_string());
    assert!(
        validate_device_session_status_json(&serde_json::to_string(&private_path).unwrap())
            .is_err()
    );

    let mut weight_path = fixture_value();
    weight_path["limitations"][0] =
        serde_json::Value::String("models/private/model.safetensors".to_string());
    assert!(
        validate_device_session_status_json(&serde_json::to_string(&weight_path).unwrap()).is_err()
    );

    let mut unsupported_claim = fixture_value();
    unsupported_claim["statusPanel"][0]["summary"] =
        serde_json::Value::String("KV260 inference works".to_string());
    assert!(validate_device_session_status_json(
        &serde_json::to_string(&unsupported_claim).unwrap()
    )
    .is_err());
}

#[test]
fn cli_validate_emits_json_summary_and_exits_zero() {
    let out = bin()
        .args([
            "device-session-status",
            "validate",
            "--file",
            fixture_path().to_str().unwrap(),
            "--format",
            "json",
        ])
        .output()
        .expect("failed to run pccx-lab device-session-status validate");

    assert_eq!(out.status.code(), Some(0));
    assert!(out.stderr.is_empty());
    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout must be valid JSON");
    assert_eq!(
        parsed["schemaVersion"],
        DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION
    );
    assert_eq!(parsed["valid"].as_bool(), Some(true));
    assert_eq!(parsed["targetDevice"], "kv260");
    assert_eq!(parsed["statusPanelRows"]["runtime_readiness"], "blocked");
}

#[test]
fn cli_validate_output_is_deterministic() {
    let first = bin()
        .args([
            "device-session-status",
            "validate",
            "--file",
            fixture_path().to_str().unwrap(),
        ])
        .output()
        .expect("failed to run first validation");
    let second = bin()
        .args([
            "device-session-status",
            "validate",
            "--file",
            fixture_path().to_str().unwrap(),
        ])
        .output()
        .expect("failed to run second validation");

    assert_eq!(first.status.code(), Some(0));
    assert_eq!(second.status.code(), Some(0));
    assert_eq!(first.stdout, second.stdout);
}

#[test]
fn cli_validate_does_not_write_files() {
    let tmp = tempfile::tempdir().unwrap();
    let fixture = tmp.path().join("device-session.json");
    std::fs::write(&fixture, read_fixture()).unwrap();

    let before = std::fs::read_dir(tmp.path()).unwrap().count();
    let out = bin()
        .args([
            "device-session-status",
            "validate",
            "--file",
            fixture.to_str().unwrap(),
        ])
        .output()
        .expect("failed to run validation");
    let after = std::fs::read_dir(tmp.path()).unwrap().count();

    assert_eq!(out.status.code(), Some(0));
    assert_eq!(before, after);
}

#[test]
fn cli_rejects_invalid_json_without_echoing_input_path() {
    let tmp = tempfile::tempdir().unwrap();
    let fixture = tmp.path().join("bad-device-session.json");
    std::fs::write(&fixture, "{\"schemaVersion\":\"not-device-session\"}").unwrap();

    let out = bin()
        .args([
            "device-session-status",
            "validate",
            "--file",
            fixture.to_str().unwrap(),
        ])
        .output()
        .expect("failed to run validation");

    assert_eq!(out.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(!stderr.contains(fixture.to_str().unwrap()));
    let parsed: serde_json::Value =
        serde_json::from_str(&stderr).expect("stderr must be JSON error");
    assert_eq!(
        parsed["schemaVersion"],
        DEVICE_SESSION_STATUS_VALIDATION_SCHEMA_VERSION
    );
    assert_eq!(parsed["valid"].as_bool(), Some(false));
}
