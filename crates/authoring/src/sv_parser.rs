// Module: sv_parser
// Regex-based SystemVerilog module extractor for the Phase 6 M6.1
// SV-docstring-to-ISA-PDF pipeline.
//
// Parses module declarations, port lists, parameter blocks, and
// preceding doc-comments from `.sv` source files without requiring
// a full grammar (tree-sitter-verilog is not reliably available on
// crates.io). Good enough for the pccx RTL codebase where modules
// follow the `npu_interfaces.svh` port-prefix conventions.

#[derive(Debug, Clone, serde::Serialize)]
pub struct SvModule {
    pub name: String,
    pub ports: Vec<SvPort>,
    pub parameters: Vec<SvParam>,
    pub doc_comment: Option<String>,
    pub line_number: usize,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct SvPort {
    pub name: String,
    pub direction: PortDirection,
    pub width: String,
    pub doc: Option<String>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub enum PortDirection {
    Input,
    Output,
    Inout,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct SvParam {
    pub name: String,
    pub default_value: Option<String>,
    pub doc: Option<String>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct SvParseResult {
    pub modules: Vec<SvModule>,
    pub file_path: String,
    pub total_lines: usize,
}

/// Parse a SystemVerilog source file and extract module declarations,
/// ports, parameters, and doc comments.
pub fn parse_sv(source: &str, file_path: &str) -> SvParseResult {
    let mut modules = Vec::new();
    let lines: Vec<&str> = source.lines().collect();
    let total_lines = lines.len();

    let mut i = 0;
    while i < lines.len() {
        let line = lines[i].trim();

        // Look for module declarations
        if line.starts_with("module ") || line.starts_with("module\t") {
            let doc = extract_preceding_doc_comment(&lines, i);
            let module = parse_module_header(&lines, &mut i);
            if let Some(mut m) = module {
                m.doc_comment = doc;
                modules.push(m);
            }
        }
        i += 1;
    }

    SvParseResult {
        modules,
        file_path: file_path.to_string(),
        total_lines,
    }
}

fn extract_preceding_doc_comment(lines: &[&str], module_line: usize) -> Option<String> {
    let mut doc_lines = Vec::new();
    let mut j = module_line.saturating_sub(1);

    loop {
        let line = lines[j].trim();
        if line.starts_with("//") {
            doc_lines.push(line.trim_start_matches("//").trim().to_string());
        } else if line.starts_with("/*") || line.ends_with("*/") || line.starts_with("*") {
            let cleaned = line
                .trim_start_matches("/*!")
                .trim_start_matches("/*")
                .trim_start_matches("*")
                .trim_end_matches("*/")
                .trim();
            if !cleaned.is_empty() {
                doc_lines.push(cleaned.to_string());
            }
        } else {
            break;
        }
        if j == 0 { break; }
        j -= 1;
    }

    doc_lines.reverse();
    if doc_lines.is_empty() {
        None
    } else {
        Some(doc_lines.join("\n"))
    }
}

fn parse_module_header(lines: &[&str], i: &mut usize) -> Option<SvModule> {
    // Collect the full module header (may span multiple lines until ';' or ')')
    let mut header = String::new();
    let start_line = *i;
    while *i < lines.len() {
        header.push_str(lines[*i]);
        header.push(' ');
        if lines[*i].contains(';') {
            break;
        }
        *i += 1;
    }

    // Extract module name
    let name = header.split_whitespace()
        .nth(1)?  // word after "module"
        .trim_end_matches(|c: char| !c.is_alphanumeric() && c != '_')
        .to_string();

    // Extract ports from the parenthesized section
    let ports = extract_ports(&header);
    let parameters = extract_parameters(&header);

    Some(SvModule {
        name,
        ports,
        parameters,
        doc_comment: None,
        line_number: start_line + 1,
    })
}

fn extract_ports(header: &str) -> Vec<SvPort> {
    let mut ports = Vec::new();

    // Find the port list between parentheses
    if let Some(start) = header.find('(') {
        if let Some(end) = header.rfind(')') {
            let port_str = &header[start + 1..end];
            for part in port_str.split(',') {
                let part = part.trim();
                if part.is_empty() { continue; }

                let tokens: Vec<&str> = part.split_whitespace().collect();
                if tokens.is_empty() { continue; }

                let mut direction = PortDirection::Input;
                let mut width = String::new();

                for (_idx, &tok) in tokens.iter().enumerate() {
                    match tok {
                        "input" => { direction = PortDirection::Input; }
                        "output" => { direction = PortDirection::Output; }
                        "inout" => { direction = PortDirection::Inout; }
                        _ if tok.starts_with('[') => {
                            width = tok.to_string();
                        }
                        _ => {}
                    }
                }

                if let Some(&name) = tokens.last() {
                    let name = name.trim_end_matches(|c: char| !c.is_alphanumeric() && c != '_');
                    if !name.is_empty() && name != "input" && name != "output" && name != "inout" {
                        ports.push(SvPort {
                            name: name.to_string(),
                            direction,
                            width: if width.is_empty() { "1".to_string() } else { width },
                            doc: None,
                        });
                    }
                }
            }
        }
    }

    ports
}

fn extract_parameters(header: &str) -> Vec<SvParam> {
    let mut params = Vec::new();

    // Look for #(...) parameter section
    if let Some(hash_pos) = header.find('#') {
        if let Some(start) = header[hash_pos..].find('(') {
            let after_hash = &header[hash_pos + start + 1..];
            if let Some(end) = after_hash.find(')') {
                let param_str = &after_hash[..end];
                for part in param_str.split(',') {
                    let part = part.trim();
                    let tokens: Vec<&str> = part.split_whitespace().collect();

                    // Look for "parameter TYPE NAME = VALUE" pattern
                    for (idx, &tok) in tokens.iter().enumerate() {
                        if tok == "parameter" || tok == "localparam" {
                            if let Some(&name_tok) = tokens.get(idx + 1).or(tokens.get(idx + 2)) {
                                let (name, default) = if let Some(eq_pos) = part.find('=') {
                                    let name = name_tok.trim_end_matches(|c: char| !c.is_alphanumeric() && c != '_');
                                    let val = part[eq_pos + 1..].trim().to_string();
                                    (name.to_string(), Some(val))
                                } else {
                                    (name_tok.trim_end_matches(|c: char| !c.is_alphanumeric() && c != '_').to_string(), None)
                                };

                                params.push(SvParam { name, default_value: default, doc: None });
                            }
                            break;
                        }
                    }
                }
            }
        }
    }

    params
}

/// Generate a Markdown documentation page for a parsed SV file.
pub fn generate_module_docs(result: &SvParseResult) -> String {
    let mut out = String::new();

    out.push_str(&format!("# {}\n\n", result.file_path));
    out.push_str(&format!("Source: `{}` ({} lines)\n\n", result.file_path, result.total_lines));

    for module in &result.modules {
        out.push_str(&format!("## Module: `{}`\n\n", module.name));

        if let Some(doc) = &module.doc_comment {
            out.push_str(&format!("{}\n\n", doc));
        }

        out.push_str(&format!("**Defined at:** line {}\n\n", module.line_number));

        if !module.parameters.is_empty() {
            out.push_str("### Parameters\n\n");
            out.push_str("| Name | Default |\n|---|---|\n");
            for p in &module.parameters {
                out.push_str(&format!("| `{}` | {} |\n",
                    p.name,
                    p.default_value.as_deref().unwrap_or("-")));
            }
            out.push_str("\n");
        }

        if !module.ports.is_empty() {
            out.push_str("### Ports\n\n");
            out.push_str("| Direction | Width | Name |\n|---|---|---|\n");
            for port in &module.ports {
                let dir = match port.direction {
                    PortDirection::Input => "input",
                    PortDirection::Output => "output",
                    PortDirection::Inout => "inout",
                };
                out.push_str(&format!("| {} | {} | `{}` |\n", dir, port.width, port.name));
            }
            out.push_str("\n");
        }
    }

    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_module() {
        let sv = r#"
// NPU top-level wrapper
// Connects AXI-Lite frontend to compute cores
module npu_top #(
    parameter NUM_CORES = 8,
    parameter DATA_WIDTH = 128
)(
    input  logic        i_clk,
    input  logic        i_rst_n,
    output logic [31:0] o_status
);
endmodule
"#;
        let result = parse_sv(sv, "npu_top.sv");
        assert_eq!(result.modules.len(), 1);
        let m = &result.modules[0];
        assert_eq!(m.name, "npu_top");
        assert!(m.doc_comment.is_some());
        assert!(!m.ports.is_empty());
    }

    #[test]
    fn test_generate_docs() {
        let sv = "module simple(input logic clk, output logic data);\nendmodule\n";
        let result = parse_sv(sv, "simple.sv");
        let doc = generate_module_docs(&result);
        assert!(doc.contains("simple"));
        assert!(doc.contains("clk"));
        assert!(doc.contains("data"));
    }
}
