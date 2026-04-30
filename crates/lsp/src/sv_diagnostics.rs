// sv_diagnostics — SV diagnostics provider (Phase 2 M2.2)
//
// Parses SV source with `pccx_authoring::sv_parser` and reports
// diagnostics for pccx RTL convention violations:
//   - Ports missing the `i_`/`o_`/`io_` prefix convention (Warning)
//   - Modules with no ports and no parameters (Information — stub?)
//
// Called on file open and save.

use pccx_authoring::sv_parser::{parse_sv, PortDirection};

use crate::{
    Diagnostic, DiagnosticSeverity, DiagnosticsProvider, Language, LspError, SourcePos, SourceRange,
};

pub struct SvDiagnosticsProvider;

impl SvDiagnosticsProvider {
    pub fn new() -> Self {
        Self
    }
}

impl Default for SvDiagnosticsProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl DiagnosticsProvider for SvDiagnosticsProvider {
    fn diagnostics(
        &self,
        _language: Language,
        file: &str,
        source: &str,
    ) -> Result<Vec<Diagnostic>, LspError> {
        let parsed = parse_sv(source, file);
        let lines: Vec<&str> = source.lines().collect();
        let mut diags = Vec::new();

        for module in &parsed.modules {
            // Module line is 1-indexed from the parser; convert to 0-indexed.
            let module_line = module.line_number.saturating_sub(1) as u32;

            // Check for empty module stubs (no ports, no parameters).
            if module.ports.is_empty() && module.parameters.is_empty() {
                diags.push(Diagnostic {
                    range: SourceRange {
                        start: SourcePos {
                            line: module_line,
                            character: 0,
                        },
                        end: SourcePos {
                            line: module_line,
                            character: line_length(&lines, module_line),
                        },
                    },
                    severity: DiagnosticSeverity::Information,
                    message: format!(
                        "module `{}` has no ports or parameters — stub?",
                        module.name
                    ),
                    source: Some("pccx-lsp".to_string()),
                });
            }

            // Check port naming convention.
            for port in &module.ports {
                let expected_prefix = match port.direction {
                    PortDirection::Input => "i_",
                    PortDirection::Output => "o_",
                    PortDirection::Inout => "io_",
                };

                if !port.name.starts_with(expected_prefix) {
                    let range = find_port_range(&lines, &port.name, module_line);
                    let dir_label = match port.direction {
                        PortDirection::Input => "input",
                        PortDirection::Output => "output",
                        PortDirection::Inout => "inout",
                    };
                    diags.push(Diagnostic {
                        range,
                        severity: DiagnosticSeverity::Warning,
                        message: format!(
                            "{} port `{}` does not follow the `{}` prefix convention",
                            dir_label, port.name, expected_prefix
                        ),
                        source: Some("pccx-lsp".to_string()),
                    });
                }
            }
        }

        Ok(diags)
    }

    fn name(&self) -> &'static str {
        "sv-diagnostics"
    }
}

// ─── Helpers ────────────────────────────────────────────────────────

/// Returns the length of line `n` (0-indexed), or 0 if out of range.
fn line_length(lines: &[&str], n: u32) -> u32 {
    lines.get(n as usize).map(|l| l.len() as u32).unwrap_or(0)
}

/// Searches downward from `start_line` for the port name in source
/// lines and returns a `SourceRange` covering the identifier.  Falls
/// back to the module line if not found.
fn find_port_range(lines: &[&str], port_name: &str, start_line: u32) -> SourceRange {
    // Search a reasonable window (module headers rarely exceed 50 lines).
    let search_end = ((start_line as usize) + 50).min(lines.len());
    for i in (start_line as usize)..search_end {
        if let Some(col) = lines[i].find(port_name) {
            // Verify it's a word boundary (not a substring of a longer ident).
            let before_ok = col == 0
                || !lines[i].as_bytes()[col - 1].is_ascii_alphanumeric()
                    && lines[i].as_bytes()[col - 1] != b'_';
            let after = col + port_name.len();
            let after_ok = after >= lines[i].len()
                || !lines[i].as_bytes()[after].is_ascii_alphanumeric()
                    && lines[i].as_bytes()[after] != b'_';
            if before_ok && after_ok {
                return SourceRange {
                    start: SourcePos {
                        line: i as u32,
                        character: col as u32,
                    },
                    end: SourcePos {
                        line: i as u32,
                        character: (col + port_name.len()) as u32,
                    },
                };
            }
        }
    }

    // Fallback: point at the module declaration line.
    SourceRange {
        start: SourcePos {
            line: start_line,
            character: 0,
        },
        end: SourcePos {
            line: start_line,
            character: line_length(lines, start_line),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_diagnostics_for_convention_following_module() {
        let sv = "\
module good_module (
    input  logic       i_clk,
    input  logic       i_rst_n,
    output logic [7:0] o_data
);
endmodule
";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "good.sv", sv)
            .expect("diagnostics must not error");
        assert!(
            diags.is_empty(),
            "convention-following module should produce no diagnostics"
        );
    }

    #[test]
    fn warns_on_non_prefixed_port_name() {
        let sv = "\
module bad_names (
    input  logic clk,
    input  logic reset,
    output logic data_out
);
endmodule
";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "bad.sv", sv)
            .expect("diagnostics must not error");

        // Three ports violate the prefix convention.
        assert_eq!(
            diags.len(),
            3,
            "expected 3 prefix warnings, got {}",
            diags.len()
        );
        for d in &diags {
            assert_eq!(d.severity, DiagnosticSeverity::Warning);
            assert!(d.message.contains("prefix convention"));
        }
    }

    #[test]
    fn warns_on_output_without_o_prefix() {
        let sv = "\
module half_bad (
    input  logic       i_clk,
    output logic [7:0] result
);
endmodule
";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "half.sv", sv)
            .expect("diagnostics must not error");

        assert_eq!(diags.len(), 1);
        assert!(diags[0].message.contains("output port `result`"));
        assert!(diags[0].message.contains("`o_`"));
    }

    #[test]
    fn info_for_empty_module_stub() {
        let sv = "module empty_stub;\nendmodule\n";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "stub.sv", sv)
            .expect("diagnostics must not error");

        assert_eq!(diags.len(), 1);
        assert_eq!(diags[0].severity, DiagnosticSeverity::Information);
        assert!(diags[0].message.contains("stub"));
    }

    #[test]
    fn no_stub_warning_when_module_has_parameters_only() {
        let sv = "\
module param_only #(
    parameter int WIDTH = 8
) ();
endmodule
";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "param_only.sv", sv)
            .expect("diagnostics must not error");

        // Has parameters so it's not a stub; no port prefix issues either.
        assert!(diags.is_empty());
    }

    #[test]
    fn inout_port_expects_io_prefix() {
        let sv = "\
module bidir (
    inout wire [7:0] debug_bus
);
endmodule
";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "bidir.sv", sv)
            .expect("diagnostics must not error");

        assert_eq!(diags.len(), 1);
        assert!(diags[0].message.contains("inout port `debug_bus`"));
        assert!(diags[0].message.contains("`io_`"));
    }

    #[test]
    fn diagnostic_range_points_to_port_name() {
        let sv = "\
module ranged (
    input  logic bad_port
);
endmodule
";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "ranged.sv", sv)
            .expect("diagnostics must not error");

        assert_eq!(diags.len(), 1);
        let range = &diags[0].range;
        // "bad_port" should be found on line 1
        assert_eq!(range.start.line, 1);
        // Verify the range covers the identifier width
        let width = range.end.character - range.start.character;
        assert_eq!(width, "bad_port".len() as u32);
    }

    #[test]
    fn provider_name_is_sv_diagnostics() {
        assert_eq!(SvDiagnosticsProvider::new().name(), "sv-diagnostics");
    }

    #[test]
    fn mixed_good_and_bad_ports() {
        let sv = "\
module mixed (
    input  logic       i_clk,
    input  logic       reset_n,
    output logic [7:0] o_data,
    output logic       valid
);
endmodule
";
        let provider = SvDiagnosticsProvider::new();
        let diags = provider
            .diagnostics(Language::SystemVerilog, "mixed.sv", sv)
            .expect("diagnostics must not error");

        // Only reset_n and valid should be flagged.
        assert_eq!(diags.len(), 2);
        let names: Vec<&str> = diags
            .iter()
            .map(|d| {
                if d.message.contains("reset_n") {
                    "reset_n"
                } else if d.message.contains("valid") {
                    "valid"
                } else {
                    "unknown"
                }
            })
            .collect();
        assert!(names.contains(&"reset_n"));
        assert!(names.contains(&"valid"));
    }
}
