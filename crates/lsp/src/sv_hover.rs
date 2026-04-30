// sv_hover — SV hover provider (Phase 2 M2.2)
//
// Resolves hover information for SystemVerilog identifiers by parsing
// the source with `pccx_authoring::sv_parser` and matching the word
// under the cursor against module names, port names, and parameter
// names.  Returns formatted Markdown content.

use pccx_authoring::sv_parser::{parse_sv, PortDirection, SvModule, SvParam, SvPort};

use crate::{Hover, HoverProvider, Language, LspError, SourcePos, SourceRange};

pub struct SvHoverProvider;

impl SvHoverProvider {
    pub fn new() -> Self {
        Self
    }
}

impl Default for SvHoverProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl HoverProvider for SvHoverProvider {
    fn hover(
        &self,
        _language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Option<Hover>, LspError> {
        let word = match extract_word_at(source, pos) {
            Some(w) => w,
            None => return Ok(None),
        };

        let parsed = parse_sv(source, file);

        // Check module names first
        for module in &parsed.modules {
            if module.name == word.text {
                return Ok(Some(Hover {
                    contents: format_module_hover(module),
                    range: Some(word.range),
                }));
            }

            // Check port names within this module
            for port in &module.ports {
                if port.name == word.text {
                    return Ok(Some(Hover {
                        contents: format_port_hover(port, &module.name),
                        range: Some(word.range),
                    }));
                }
            }

            // Check parameter names within this module
            for param in &module.parameters {
                if param.name == word.text {
                    return Ok(Some(Hover {
                        contents: format_param_hover(param, &module.name),
                        range: Some(word.range),
                    }));
                }
            }
        }

        Ok(None)
    }

    fn name(&self) -> &'static str {
        "sv-hover"
    }
}

// ─── Word extraction ────────────────────────────────────────────────

struct WordAtPos {
    text: String,
    range: SourceRange,
}

/// Extracts the identifier under the cursor.  Scans outward from
/// `pos.character` on `pos.line` for `[A-Za-z0-9_]` boundaries.
fn extract_word_at(source: &str, pos: SourcePos) -> Option<WordAtPos> {
    let line_str = source.lines().nth(pos.line as usize)?;
    let col = pos.character as usize;

    if col >= line_str.len() {
        return None;
    }

    let bytes = line_str.as_bytes();
    if !is_ident_byte(bytes[col]) {
        return None;
    }

    // Scan left to find the start of the identifier
    let mut start = col;
    while start > 0 && is_ident_byte(bytes[start - 1]) {
        start -= 1;
    }

    // Scan right to find the end
    let mut end = col;
    while end < bytes.len() && is_ident_byte(bytes[end]) {
        end += 1;
    }

    let text = line_str[start..end].to_string();
    if text.is_empty() {
        return None;
    }

    Some(WordAtPos {
        text,
        range: SourceRange {
            start: SourcePos {
                line: pos.line,
                character: start as u32,
            },
            end: SourcePos {
                line: pos.line,
                character: end as u32,
            },
        },
    })
}

fn is_ident_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

// ─── Hover formatting ───────────────────────────────────────────────

fn format_module_hover(module: &SvModule) -> String {
    let mut out = String::new();

    out.push_str(&format!("### module `{}`\n\n", module.name));

    if let Some(doc) = &module.doc_comment {
        out.push_str(doc);
        out.push_str("\n\n");
    }

    if !module.parameters.is_empty() {
        out.push_str("**Parameters:**\n");
        for p in &module.parameters {
            let default = p
                .default_value
                .as_deref()
                .map(|v| format!(" = {v}"))
                .unwrap_or_default();
            out.push_str(&format!("- `{}{}`", p.name, default));
            if let Some(doc) = &p.doc {
                out.push_str(&format!(" -- {doc}"));
            }
            out.push('\n');
        }
        out.push('\n');
    }

    if !module.ports.is_empty() {
        out.push_str("**Ports:**\n");
        for port in &module.ports {
            let dir = direction_str(&port.direction);
            let width = if port.width == "1" {
                String::new()
            } else {
                format!(" {}", port.width)
            };
            out.push_str(&format!("- `{}` -- {}{}\n", port.name, dir, width));
        }
    }

    out
}

fn format_port_hover(port: &SvPort, module_name: &str) -> String {
    let mut out = String::new();
    let dir = direction_str(&port.direction);
    let width = if port.width == "1" {
        String::new()
    } else {
        format!(" {}", port.width)
    };

    out.push_str(&format!(
        "`{}` -- {} {}{}\n\n",
        port.name, dir, "port", width
    ));
    out.push_str(&format!("Module: `{}`\n", module_name));

    if let Some(doc) = &port.doc {
        out.push_str(&format!("\n{doc}\n"));
    }

    out
}

fn format_param_hover(param: &SvParam, module_name: &str) -> String {
    let mut out = String::new();

    let default = param
        .default_value
        .as_deref()
        .map(|v| format!(" = {v}"))
        .unwrap_or_default();

    out.push_str(&format!("`{}{}`\n\n", param.name, default));
    out.push_str(&format!("Module: `{}`\n", module_name));

    if let Some(doc) = &param.doc {
        out.push_str(&format!("\n{doc}\n"));
    }

    out
}

fn direction_str(dir: &PortDirection) -> &'static str {
    match dir {
        PortDirection::Input => "input",
        PortDirection::Output => "output",
        PortDirection::Inout => "inout",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_SV: &str = "\
/// Top-level NPU compute engine
/// Implements the MAC array with configurable dimensions
module ctrl_npu_frontend #(
    parameter int ROWS = 32,
    parameter int COLS = 32
) (
    input  logic i_clk,
    input  logic i_rst_n,
    output logic o_busy
);
endmodule
";

    #[test]
    fn hover_on_module_name_returns_doc() {
        let provider = SvHoverProvider::new();
        // "ctrl_npu_frontend" starts at line 2, character 7
        let result = provider
            .hover(
                Language::SystemVerilog,
                "test.sv",
                SourcePos {
                    line: 2,
                    character: 10,
                },
                SAMPLE_SV,
            )
            .expect("hover must not error");
        let hover = result.expect("hover must return Some for module name");
        assert!(
            hover.contents.contains("ctrl_npu_frontend"),
            "hover must mention module name"
        );
        assert!(
            hover.contents.contains("Top-level NPU compute engine"),
            "hover must include doc comment"
        );
        assert!(
            hover.contents.contains("ROWS"),
            "hover must list parameters"
        );
    }

    #[test]
    fn hover_on_port_returns_direction_and_width() {
        let sv = "\
module adder (
    input  logic [7:0] i_a,
    input  logic [7:0] i_b,
    output logic [8:0] o_sum
);
endmodule
";
        let provider = SvHoverProvider::new();
        // "i_a" is on line 1
        let result = provider
            .hover(
                Language::SystemVerilog,
                "adder.sv",
                SourcePos {
                    line: 1,
                    character: 24,
                },
                sv,
            )
            .expect("hover must not error");
        let hover = result.expect("hover should return Some for port name");
        assert!(hover.contents.contains("i_a"), "must mention port name");
        assert!(hover.contents.contains("input"), "must mention direction");
        assert!(
            hover.contents.contains("[7:0]"),
            "must mention width, got: {}",
            hover.contents
        );
    }

    #[test]
    fn hover_on_parameter_returns_default_value() {
        let provider = SvHoverProvider::new();
        // "ROWS" appears on line 3
        let result = provider
            .hover(
                Language::SystemVerilog,
                "test.sv",
                SourcePos {
                    line: 3,
                    character: 20,
                },
                SAMPLE_SV,
            )
            .expect("hover must not error");
        let hover = result.expect("hover should return Some for param name");
        assert!(hover.contents.contains("ROWS"), "must mention param name");
        assert!(hover.contents.contains("32"), "must mention default value");
    }

    #[test]
    fn hover_on_unknown_symbol_returns_none() {
        let provider = SvHoverProvider::new();
        let result = provider
            .hover(
                Language::SystemVerilog,
                "test.sv",
                SourcePos {
                    line: 10,
                    character: 0,
                },
                SAMPLE_SV,
            )
            .expect("hover must not error");
        // "endmodule" is an SV keyword, not a module/port/param name
        assert!(result.is_none());
    }

    #[test]
    fn hover_on_empty_line_returns_none() {
        let provider = SvHoverProvider::new();
        let sv = "module foo;\n\nendmodule\n";
        let result = provider
            .hover(
                Language::SystemVerilog,
                "test.sv",
                SourcePos {
                    line: 1,
                    character: 0,
                },
                sv,
            )
            .expect("hover must not error");
        assert!(result.is_none());
    }

    #[test]
    fn extract_word_at_identifies_module_name() {
        let word = extract_word_at(
            SAMPLE_SV,
            SourcePos {
                line: 2,
                character: 10,
            },
        )
        .expect("should find word");
        assert_eq!(word.text, "ctrl_npu_frontend");
    }

    #[test]
    fn extract_word_at_returns_none_on_whitespace() {
        let result = extract_word_at(
            "  hello  ",
            SourcePos {
                line: 0,
                character: 0,
            },
        );
        assert!(result.is_none());
    }

    #[test]
    fn provider_name_is_sv_hover() {
        assert_eq!(SvHoverProvider::new().name(), "sv-hover");
    }
}
