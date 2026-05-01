// status_cli — end-to-end CLI tests for `pccx-lab status`.
//
// Invokes the built binary and checks JSON output + exit codes.
// No external deps: uses std::process::Command + env!("CARGO_BIN_EXE_pccx-lab").

use std::collections::HashSet;
use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pccx-lab"))
}

#[test]
fn status_exits_zero() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    assert_eq!(out.status.code(), Some(0), "expected exit 0 for status");
}

#[test]
fn status_emits_valid_json() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(parsed["envelope"], "0");
    assert_eq!(parsed["tool"], "pccx-lab");
}

#[test]
fn status_format_json_flag_accepted() {
    let out = bin()
        .args(["status", "--format", "json"])
        .output()
        .expect("failed to run pccx-lab status --format json");

    assert_eq!(
        out.status.code(),
        Some(0),
        "expected exit 0 with --format json"
    );

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON with --format json");

    assert_eq!(parsed["envelope"], "0");
}

#[test]
fn status_unsupported_format_exits_two() {
    let out = bin()
        .args(["status", "--format", "text"])
        .output()
        .expect("failed to run pccx-lab status --format text");

    assert_eq!(
        out.status.code(),
        Some(2),
        "expected exit 2 for unsupported format"
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("unsupported format"),
        "expected 'unsupported format' in stderr, got: {stderr}"
    );
}

#[test]
fn status_version_matches_cargo_version() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(
        parsed["version"].as_str().unwrap_or(""),
        env!("CARGO_PKG_VERSION"),
        "status version must match CARGO_PKG_VERSION"
    );
}

#[test]
fn status_mode_is_host_dry_run() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(parsed["mode"], "host-dry-run");
}

#[test]
fn status_device_kv260_is_not_probed() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(
        parsed["device"]["kv260"].as_str().unwrap_or(""),
        "not-probed",
        "device.kv260 must be 'not-probed' — no real hardware probing"
    );
}

#[test]
fn status_inference_is_unavailable() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(
        parsed["inference"]["status"].as_str().unwrap_or(""),
        "unavailable",
        "inference.status must be 'unavailable' — no real inference"
    );
}

#[test]
fn status_diagnostics_integration_is_active() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(
        parsed["diagnostics_integration"]["status"]
            .as_str()
            .unwrap_or(""),
        "active",
        "diagnostics_integration.status must be 'active'"
    );
    assert_eq!(
        parsed["diagnostics_integration"]["consumer"]
            .as_str()
            .unwrap_or(""),
        "systemverilog-ide"
    );
}

#[test]
fn status_launcher_handoff_is_early_scaffold() {
    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(
        parsed["launcher_handoff"]["status"].as_str().unwrap_or(""),
        "early-scaffold"
    );
    assert_eq!(
        parsed["launcher_handoff"]["consumer"]
            .as_str()
            .unwrap_or(""),
        "pccx-llm-launcher"
    );
}

// Drift-prevention: output keys must match the example JSON keys.
// If the struct gains or loses a field, this test will catch the mismatch.
#[test]
fn status_keys_match_example_json() {
    use std::path::Path;

    let example_path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("docs/examples/run-status.example.json");

    let example_text = std::fs::read_to_string(&example_path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", example_path.display()));
    let example: serde_json::Value =
        serde_json::from_str(&example_text).expect("example JSON is not valid");

    let example_keys: HashSet<&str> = example
        .as_object()
        .expect("example JSON must be an object")
        .keys()
        .map(String::as_str)
        .collect();

    let out = bin()
        .arg("status")
        .output()
        .expect("failed to run pccx-lab status");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let live: serde_json::Value =
        serde_json::from_str(&stdout).expect("status stdout is not valid JSON");

    let live_keys: HashSet<&str> = live
        .as_object()
        .expect("status stdout must be an object")
        .keys()
        .map(String::as_str)
        .collect();

    assert_eq!(
        live_keys,
        example_keys,
        "live status keys differ from example JSON.\n  live only: {:?}\n  example only: {:?}",
        live_keys.difference(&example_keys).collect::<Vec<_>>(),
        example_keys.difference(&live_keys).collect::<Vec<_>>(),
    );
}
