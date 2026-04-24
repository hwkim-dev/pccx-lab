// sv_provider — SV keyword completion provider (Phase 2 M2.2)
//
// Concrete `CompletionProvider` that returns IEEE 1800-2017 keyword
// completions for SystemVerilog editing in the Monaco editor, plus
// a handful of UVM macros and pccx-specific identifiers.  This is
// a static, in-process provider — no external LSP subprocess needed.
// Tree-sitter-aware context filtering (e.g., suppress keywords inside
// a string literal) lands in M2.3.

use crate::{Completion, CompletionProvider, CompletionSource, Language, LspError, SourcePos};

pub struct SvKeywordProvider {
    keywords: Vec<(&'static str, &'static str)>,
}

impl SvKeywordProvider {
    pub fn new() -> Self {
        Self {
            keywords: vec![
                // IEEE 1800-2017 keywords
                ("module", "Module declaration"),
                ("endmodule", "End module"),
                ("interface", "Interface declaration"),
                ("endinterface", "End interface"),
                ("class", "Class declaration"),
                ("endclass", "End class"),
                ("function", "Function declaration"),
                ("endfunction", "End function"),
                ("task", "Task declaration"),
                ("endtask", "End task"),
                ("always_ff", "Clocked always block (flip-flop)"),
                ("always_comb", "Combinational always block"),
                ("always_latch", "Latch always block"),
                ("assign", "Continuous assignment"),
                ("logic", "4-state data type"),
                ("reg", "Register data type"),
                ("wire", "Net data type"),
                ("input", "Input port"),
                ("output", "Output port"),
                ("inout", "Bidirectional port"),
                ("parameter", "Parameter declaration"),
                ("localparam", "Local parameter"),
                ("typedef", "Type definition"),
                ("enum", "Enumeration"),
                ("struct", "Structure"),
                ("union", "Union"),
                ("packed", "Packed qualifier"),
                ("generate", "Generate block"),
                ("endgenerate", "End generate"),
                ("for", "For loop"),
                ("if", "If statement"),
                ("else", "Else clause"),
                ("case", "Case statement"),
                ("endcase", "End case"),
                ("begin", "Block begin"),
                ("end", "Block end"),
                ("initial", "Initial block"),
                ("posedge", "Positive edge"),
                ("negedge", "Negative edge"),
                ("import", "Package import"),
                ("export", "Package export"),
                ("package", "Package declaration"),
                ("endpackage", "End package"),
                // UVM macros
                ("`uvm_component_utils", "UVM component factory registration"),
                ("`uvm_object_utils", "UVM object factory registration"),
                ("`uvm_info", "UVM info message"),
                ("`uvm_warning", "UVM warning message"),
                ("`uvm_error", "UVM error message"),
                ("`uvm_fatal", "UVM fatal message"),
                // pccx-specific
                ("pccx_transaction", "pccx NPU transaction class"),
                ("pccx_driver", "pccx UVM driver"),
                ("pccx_monitor", "pccx UVM monitor"),
                ("pccx_scoreboard", "pccx UVM scoreboard"),
            ],
        }
    }
}

impl Default for SvKeywordProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl CompletionProvider for SvKeywordProvider {
    fn complete(
        &self,
        _language: Language,
        _file: &str,
        _pos: SourcePos,
        _source: &str,
    ) -> Result<Vec<Completion>, LspError> {
        Ok(self
            .keywords
            .iter()
            .map(|(kw, doc)| Completion {
                label: kw.to_string(),
                detail: Some(doc.to_string()),
                documentation: None,
                insert_text: kw.to_string(),
                source: CompletionSource::Lsp,
            })
            .collect())
    }

    fn name(&self) -> &'static str {
        "sv-keyword"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keyword_list_is_non_empty() {
        let provider = SvKeywordProvider::new();
        assert!(!provider.keywords.is_empty());
    }

    #[test]
    fn completions_contain_core_sv_keywords() {
        let provider = SvKeywordProvider::new();
        let completions = provider
            .complete(Language::SystemVerilog, "test.sv", SourcePos { line: 0, character: 0 }, "")
            .expect("complete must succeed");
        let labels: Vec<&str> = completions.iter().map(|c| c.label.as_str()).collect();
        assert!(labels.contains(&"module"), "must contain 'module'");
        assert!(labels.contains(&"always_ff"), "must contain 'always_ff'");
        assert!(labels.contains(&"always_comb"), "must contain 'always_comb'");
        assert!(labels.contains(&"logic"), "must contain 'logic'");
    }

    #[test]
    fn completions_contain_uvm_macros() {
        let provider = SvKeywordProvider::new();
        let completions = provider
            .complete(Language::SystemVerilog, "test.sv", SourcePos { line: 0, character: 0 }, "")
            .expect("complete must succeed");
        let labels: Vec<&str> = completions.iter().map(|c| c.label.as_str()).collect();
        assert!(labels.contains(&"`uvm_info"), "must contain '`uvm_info'");
        assert!(labels.contains(&"`uvm_component_utils"), "must contain '`uvm_component_utils'");
    }

    #[test]
    fn completions_contain_pccx_identifiers() {
        let provider = SvKeywordProvider::new();
        let completions = provider
            .complete(Language::SystemVerilog, "test.sv", SourcePos { line: 0, character: 0 }, "")
            .expect("complete must succeed");
        let labels: Vec<&str> = completions.iter().map(|c| c.label.as_str()).collect();
        assert!(labels.contains(&"pccx_transaction"), "must contain 'pccx_transaction'");
        assert!(labels.contains(&"pccx_scoreboard"), "must contain 'pccx_scoreboard'");
    }

    #[test]
    fn all_completions_use_lsp_source() {
        let provider = SvKeywordProvider::new();
        let completions = provider
            .complete(Language::SystemVerilog, "test.sv", SourcePos { line: 0, character: 0 }, "")
            .expect("complete must succeed");
        for c in &completions {
            assert_eq!(c.source, CompletionSource::Lsp);
        }
    }

    #[test]
    fn all_completions_have_detail_set() {
        let provider = SvKeywordProvider::new();
        let completions = provider
            .complete(Language::SystemVerilog, "test.sv", SourcePos { line: 0, character: 0 }, "")
            .expect("complete must succeed");
        for c in &completions {
            assert!(c.detail.is_some(), "every keyword must carry a detail string");
        }
    }

    #[test]
    fn insert_text_matches_label() {
        let provider = SvKeywordProvider::new();
        let completions = provider
            .complete(Language::SystemVerilog, "test.sv", SourcePos { line: 0, character: 0 }, "")
            .expect("complete must succeed");
        for c in &completions {
            assert_eq!(c.label, c.insert_text);
        }
    }

    #[test]
    fn provider_name_is_sv_keyword() {
        let provider = SvKeywordProvider::new();
        assert_eq!(provider.name(), "sv-keyword");
    }

    #[test]
    fn default_construction_matches_new() {
        let a = SvKeywordProvider::new();
        let b = SvKeywordProvider::default();
        assert_eq!(a.keywords.len(), b.keywords.len());
    }
}
