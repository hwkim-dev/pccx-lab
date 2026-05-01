// analyze_cli — end-to-end CLI tests for `pccx-lab analyze`.
//
// Invokes the built binary and checks JSON output + exit codes.
// No external deps: uses std::process::Command + env!("CARGO_BIN_EXE_pccx-lab").

use std::path::Path;
use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pccx-lab"))
}

fn repo_root() -> std::path::PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

#[test]
fn analyze_ok_fixture_exits_0_and_emits_json() {
    let fixture = repo_root().join("fixtures/ok_module.sv");
    let out = bin()
        .args(["analyze", fixture.to_str().unwrap(), "--format", "json"])
        .output()
        .expect("failed to run pccx-lab");

    assert_eq!(
        out.status.code(),
        Some(0),
        "expected exit 0 for ok_module.sv"
    );

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    assert_eq!(parsed["envelope"], "0");
    assert_eq!(parsed["tool"], "pccx-lab");
    assert!(
        parsed["diagnostics"].as_array().unwrap().is_empty(),
        "expected no diagnostics for a valid module"
    );
}

#[test]
fn analyze_missing_endmodule_exits_1_with_scaffold_003() {
    let fixture = repo_root().join("fixtures/missing_endmodule.sv");
    let out = bin()
        .args(["analyze", fixture.to_str().unwrap()])
        .output()
        .expect("failed to run pccx-lab");

    assert_eq!(
        out.status.code(),
        Some(1),
        "expected exit 1 for missing endmodule"
    );

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    let codes: Vec<&str> = parsed["diagnostics"]
        .as_array()
        .unwrap()
        .iter()
        .map(|d| d["code"].as_str().unwrap())
        .collect();

    assert!(
        codes.contains(&"PCCX-SCAFFOLD-003"),
        "expected PCCX-SCAFFOLD-003 in diagnostics, got: {codes:?}"
    );
}

#[test]
fn analyze_empty_fixture_exits_1_with_shape_001() {
    let fixture = repo_root().join("fixtures/empty.sv");
    let out = bin()
        .args(["analyze", fixture.to_str().unwrap()])
        .output()
        .expect("failed to run pccx-lab");

    assert_eq!(out.status.code(), Some(1), "expected exit 1 for empty file");

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    let codes: Vec<&str> = parsed["diagnostics"]
        .as_array()
        .unwrap()
        .iter()
        .map(|d| d["code"].as_str().unwrap())
        .collect();

    assert!(
        codes.contains(&"PCCX-SHAPE-001"),
        "expected PCCX-SHAPE-001, got: {codes:?}"
    );
}

#[test]
fn analyze_nonexistent_file_exits_2_with_io_001() {
    let out = bin()
        .args(["analyze", "/tmp/pccx-lab-test-nonexistent-file.sv"])
        .output()
        .expect("failed to run pccx-lab");

    assert_eq!(
        out.status.code(),
        Some(2),
        "expected exit 2 for missing file"
    );

    let stdout = String::from_utf8_lossy(&out.stdout);
    let parsed: serde_json::Value =
        serde_json::from_str(&stdout).expect("stdout is not valid JSON");

    let codes: Vec<&str> = parsed["diagnostics"]
        .as_array()
        .unwrap()
        .iter()
        .map(|d| d["code"].as_str().unwrap())
        .collect();

    assert!(
        codes.contains(&"PCCX-IO-001"),
        "expected PCCX-IO-001, got: {codes:?}"
    );
}
