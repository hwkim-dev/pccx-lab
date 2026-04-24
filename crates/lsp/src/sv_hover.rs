// sv_hover — SV hover provider stub (Phase 2 M2.2)
//
// Placeholder `HoverProvider` for SystemVerilog.  Returns `None` for
// every position today; the tree-sitter-based semantic hover that
// resolves module ports, parameter values, and UVM class hierarchies
// lands in M2.3.

use crate::{Hover, HoverProvider, Language, LspError, SourcePos};

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
        _file: &str,
        _pos: SourcePos,
        _source: &str,
    ) -> Result<Option<Hover>, LspError> {
        // Stub — M2.3 adds tree-sitter queries for semantic hover.
        Ok(None)
    }

    fn name(&self) -> &'static str {
        "sv-hover"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hover_returns_none_for_any_position() {
        let provider = SvHoverProvider::new();
        let result = provider
            .hover(
                Language::SystemVerilog,
                "test.sv",
                SourcePos { line: 10, character: 5 },
                "module foo; endmodule",
            )
            .expect("hover must not error");
        assert!(result.is_none());
    }

    #[test]
    fn provider_name_is_sv_hover() {
        assert_eq!(SvHoverProvider::new().name(), "sv-hover");
    }
}
