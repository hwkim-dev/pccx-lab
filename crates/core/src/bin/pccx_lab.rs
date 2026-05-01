/// pccx-lab: central CLI entry point for the pccx-lab boundary.
///
/// Commands
///   analyze <path> [--format json]
///       Emit a diagnostics envelope for the given SystemVerilog file.
///       File-shape checks only — no semantic parsing.
///       See docs/CLI_CORE_BOUNDARY.md for the full contract.
///
///   status [--format json]
///       Emit a run-status envelope: version, mode, device/inference paths.
///       Host-only / dry-run. No real KV260 probing. No real inference.
///       See docs/CLI_CORE_BOUNDARY.md and docs/examples/run-status.example.json.
///
/// Exit codes
///   0  — no error-severity diagnostics
///   1  — at least one error-severity diagnostic
///   2  — I/O failure (file missing or unreadable; envelope still emitted)
use serde::Serialize;
use std::process;

// ─── Diagnostics envelope ─────────────────────────────────────────────────────

#[derive(Serialize)]
struct Envelope<'a> {
    _note: &'a str,
    envelope: &'a str,
    tool: &'a str,
    source: &'a str,
    diagnostics: Vec<DiagEntry>,
}

#[derive(Serialize)]
struct DiagEntry {
    line: u32,
    column: u32,
    severity: &'static str,
    code: &'static str,
    message: String,
    source: &'static str,
}

const TOOL: &str = "pccx-lab";
const DIAG_SOURCE: &str = "pccx-lab";
const ENVELOPE_NOTE: &str = "Early example — not a stable API contract. \
     Shape matches pccxai/systemverilog-ide schema/diagnostics-v0.json.";

// ─── Run-status envelope ──────────────────────────────────────────────────────

#[derive(Serialize)]
struct RunStatusEnvelope {
    _note: &'static str,
    envelope: &'static str,
    tool: &'static str,
    version: &'static str,
    mode: &'static str,
    device: DeviceStatus,
    inference: InferenceStatus,
    diagnostics_integration: IntegrationStatus,
    launcher_handoff: IntegrationStatus,
    evidence_required: &'static [&'static str],
    pccx_lab_bin: &'static str,
}

#[derive(Serialize)]
struct DeviceStatus {
    kv260: &'static str,
    note: &'static str,
}

#[derive(Serialize)]
struct InferenceStatus {
    status: &'static str,
    note: &'static str,
}

#[derive(Serialize)]
struct IntegrationStatus {
    status: &'static str,
    path: &'static str,
    consumer: &'static str,
}

fn status_envelope() -> RunStatusEnvelope {
    RunStatusEnvelope {
        _note: "Early example — not a stable API contract.",
        envelope: "0",
        tool: TOOL,
        version: env!("CARGO_PKG_VERSION"),
        mode: "host-dry-run",
        device: DeviceStatus {
            kv260: "not-probed",
            note: "KV260 path pending verified FPGA bring-up evidence.",
        },
        inference: InferenceStatus {
            status: "unavailable",
            note: "Inference path deferred; requires timing-closed bitstream and KV260 bring-up.",
        },
        diagnostics_integration: IntegrationStatus {
            status: "active",
            path: "pccx-lab analyze <file> [--format json]",
            consumer: "systemverilog-ide",
        },
        launcher_handoff: IntegrationStatus {
            status: "early-scaffold",
            path: "pccx-lab status [--format json]",
            consumer: "pccx-llm-launcher",
        },
        evidence_required: &[
            "timing-closed bitstream (pccx-FPGA-NPU-LLM-kv260)",
            "KV260 bring-up verification",
            "xsim pass evidence",
        ],
        pccx_lab_bin: "pccx-lab",
    }
}

// ─── Shape checks ─────────────────────────────────────────────────────────────

fn analyze(path: &str) -> (Vec<DiagEntry>, i32) {
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(e) => {
            let diag = DiagEntry {
                line: 0,
                column: 0,
                severity: "error",
                code: "PCCX-IO-001",
                message: format!("cannot read file: {e}"),
                source: DIAG_SOURCE,
            };
            return (vec![diag], 2);
        }
    };

    let mut diags: Vec<DiagEntry> = Vec::new();
    let mut exit = 0i32;

    if content.trim().is_empty() {
        diags.push(DiagEntry {
            line: 0,
            column: 0,
            severity: "error",
            code: "PCCX-SHAPE-001",
            message: "file is empty".to_string(),
            source: DIAG_SOURCE,
        });
        exit = 1;
        return (diags, exit);
    }

    let has_module = content.lines().any(|l| {
        let trimmed = l.trim();
        trimmed.starts_with("module ") || trimmed == "module"
    });
    let has_endmodule = content.lines().any(|l| l.trim().starts_with("endmodule"));

    if !has_module {
        diags.push(DiagEntry {
            line: 0,
            column: 0,
            severity: "error",
            code: "PCCX-SHAPE-002",
            message: "no `module` declaration found".to_string(),
            source: DIAG_SOURCE,
        });
        exit = 1;
    }

    if has_module && !has_endmodule {
        // Find the line number of the module declaration (1-indexed).
        let module_line = content
            .lines()
            .enumerate()
            .find(|(_, l)| {
                let t = l.trim();
                t.starts_with("module ") || t == "module"
            })
            .map(|(i, _)| (i + 1) as u32)
            .unwrap_or(0);

        diags.push(DiagEntry {
            line: module_line,
            column: 0,
            severity: "error",
            code: "PCCX-SCAFFOLD-003",
            message: "module declaration found but `endmodule` is missing".to_string(),
            source: DIAG_SOURCE,
        });
        exit = 1;
    }

    (diags, exit)
}

// ─── CLI ──────────────────────────────────────────────────────────────────────

fn usage() -> ! {
    eprintln!("usage: pccx-lab <command> [options]");
    eprintln!("  analyze <path> [--format json]   emit diagnostics envelope");
    eprintln!("  status [--format json]            emit run-status envelope");
    process::exit(2);
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();

    if args.is_empty() {
        usage();
    }

    match args[0].as_str() {
        "analyze" => {
            let path = args.get(1).unwrap_or_else(|| {
                eprintln!("error: analyze requires a file path");
                process::exit(2);
            });
            // --format json is the only format; accept and ignore (future-proof).

            let (diags, exit_code) = analyze(path);
            let envelope = Envelope {
                _note: ENVELOPE_NOTE,
                envelope: "0",
                tool: TOOL,
                source: path.as_str(),
                diagnostics: diags,
            };
            let json = serde_json::to_string_pretty(&envelope).unwrap_or_else(|_| "{}".to_string());
            println!("{json}");
            process::exit(exit_code);
        }
        "status" => {
            // --format json is the only supported format.
            if let Some(fmt) = args.get(1) {
                if fmt == "--format" {
                    match args.get(2).map(String::as_str) {
                        Some("json") | None => {}
                        Some(other) => {
                            eprintln!(
                                "error: unsupported format `{other}` (only `json` is supported)"
                            );
                            process::exit(2);
                        }
                    }
                }
            }
            let envelope = status_envelope();
            let json = serde_json::to_string_pretty(&envelope).unwrap_or_else(|_| "{}".to_string());
            println!("{json}");
            process::exit(0);
        }
        "--help" | "-h" | "help" => {
            eprintln!("pccx-lab — NPU profiler CLI boundary");
            eprintln!();
            eprintln!("commands:");
            eprintln!("  analyze <path> [--format json]   emit diagnostics envelope");
            eprintln!(
                "  status [--format json]            emit run-status envelope (host-dry-run)"
            );
            eprintln!();
            eprintln!("exit codes: 0 clean  1 diagnostics found  2 I/O error");
            process::exit(0);
        }
        other => {
            eprintln!("error: unknown command `{other}`");
            usage();
        }
    }
}

// ─── Unit tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn write_fixture(content: &str) -> NamedTempFile {
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(content.as_bytes()).unwrap();
        f
    }

    #[test]
    fn ok_module_exits_0_with_empty_diagnostics() {
        let f = write_fixture("module ok_mod;\nendmodule\n");
        let (diags, exit) = analyze(f.path().to_str().unwrap());
        assert_eq!(exit, 0);
        assert!(diags.is_empty());
    }

    #[test]
    fn missing_endmodule_exits_1_with_scaffold_003() {
        let f = write_fixture("module broken;\n  // no endmodule\n");
        let (diags, exit) = analyze(f.path().to_str().unwrap());
        assert_eq!(exit, 1);
        assert!(diags.iter().any(|d| d.code == "PCCX-SCAFFOLD-003"));
    }

    #[test]
    fn empty_file_exits_1_with_shape_001() {
        let f = write_fixture("   \n");
        let (diags, exit) = analyze(f.path().to_str().unwrap());
        assert_eq!(exit, 1);
        assert!(diags.iter().any(|d| d.code == "PCCX-SHAPE-001"));
    }

    #[test]
    fn no_module_keyword_exits_1_with_shape_002() {
        let f = write_fixture("// just a comment\nassign x = 1;\n");
        let (diags, exit) = analyze(f.path().to_str().unwrap());
        assert_eq!(exit, 1);
        assert!(diags.iter().any(|d| d.code == "PCCX-SHAPE-002"));
    }

    #[test]
    fn missing_file_exits_2_with_io_001() {
        let (diags, exit) = analyze("/nonexistent/path/that/cannot/exist.sv");
        assert_eq!(exit, 2);
        assert!(diags.iter().any(|d| d.code == "PCCX-IO-001"));
    }

    #[test]
    fn diagnostics_are_valid_json() {
        let f = write_fixture("module ok;\nendmodule\n");
        let (diags, _) = analyze(f.path().to_str().unwrap());
        let envelope = Envelope {
            _note: ENVELOPE_NOTE,
            envelope: "0",
            tool: TOOL,
            source: "test.sv",
            diagnostics: diags,
        };
        let json = serde_json::to_string_pretty(&envelope).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["envelope"], "0");
        assert_eq!(parsed["tool"], "pccx-lab");
    }
}
