// Module Boundary: lsp/
// pccx-lsp: Phase 2 IntelliSense façade.
//
// Scaffold-only crate.  The real implementation (tower-lsp adapter,
// external-LSP multiplexer, AI completion cache keyed by AST hash)
// lands during Phase 2 proper.  Landing the crate now keeps the
// dependency graph stable while implementation follows.

use serde::{Deserialize, Serialize};

pub const LSP_FAÇADE_API_VERSION: u32 = 1;

/// File coordinate — matches the LSP `Position` shape so it translates
/// directly to `lsp-types::Position` when the tower-lsp adapter lands.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SourcePos {
    pub line: u32,
    pub character: u32,
}

/// A source range: two coordinates.  Again: LSP-shape-compatible.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SourceRange {
    pub start: SourcePos,
    pub end: SourcePos,
}

/// Languages the Phase 2 multiplexer dispatches over.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Language {
    SystemVerilog,   // verible
    Rust,            // rust-analyzer
    C,               // clangd
    Cpp,             // clangd
    Python,          // pylsp
    Sail,            // no LSP upstream; pccx-lsp provides basic syntax
    MyStMarkdown,    // prosemirror via tree-sitter-markdown
    RstDoc,          // esbonio
}

impl Language {
    pub fn from_extension(ext: &str) -> Option<Self> {
        match ext.to_ascii_lowercase().as_str() {
            "sv" | "svh" => Some(Self::SystemVerilog),
            "rs" => Some(Self::Rust),
            "c" | "h" => Some(Self::C),
            "cpp" | "cxx" | "hpp" | "hxx" => Some(Self::Cpp),
            "py" => Some(Self::Python),
            "sail" => Some(Self::Sail),
            "md" => Some(Self::MyStMarkdown),
            "rst" => Some(Self::RstDoc),
            _ => None,
        }
    }
}

/// Completion item.  Subset of `lsp-types::CompletionItem` — just the
/// fields pccx-ide renders in its dropdown.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Completion {
    pub label: String,
    pub detail: Option<String>,
    pub documentation: Option<String>,
    pub insert_text: String,
    pub source: CompletionSource,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CompletionSource {
    /// Came from an upstream language server (verible etc.).
    Lsp,
    /// Came from a Claude-Haiku AI predictor.
    AiFast,
    /// Came from a Claude-Sonnet AI predictor (higher latency).
    AiDeep,
    /// Cached hit (keyed by AST hash).
    Cache,
}

/// Hover card — what pccx-ide renders when the user hovers a symbol.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hover {
    pub contents: String,
    pub range: Option<SourceRange>,
}

// ─── Unstable plugin API (Phase 2 M2.1) ──────────────────────────────
//
// Backends land behind three trait objects so the IntelliSense pipeline
// can swap providers per-language per-query without a rebuild.

/// Returns completion candidates at a source position.  The real
/// implementations either (a) wrap an external LSP, (b) query Claude,
/// or (c) hit an AST-hash cache.
pub trait CompletionProvider {
    fn complete(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Vec<Completion>, LspError>;

    fn name(&self) -> &'static str;
}

/// Returns hover documentation for a symbol at a source position.
pub trait HoverProvider {
    fn hover(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Option<Hover>, LspError>;

    fn name(&self) -> &'static str;
}

/// Returns a one-to-many list of source locations (definitions /
/// references).  Consumers choose which call site to emit.
pub trait LocationProvider {
    fn definitions(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Vec<SourceRange>, LspError>;

    fn references(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Vec<SourceRange>, LspError>;

    fn name(&self) -> &'static str;
}

#[derive(Debug, Clone, thiserror::Error)]
pub enum LspError {
    #[error("backend '{backend}' unavailable: {reason}")]
    BackendUnavailable { backend: String, reason: String },

    #[error("backend '{backend}' timed out after {ms} ms")]
    Timeout { backend: String, ms: u64 },

    #[error("language {lang:?} has no configured backend")]
    NoBackend { lang: Language },

    #[error("internal error: {0}")]
    Internal(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn language_from_extension_maps_sv_and_svh() {
        assert_eq!(Language::from_extension("sv"), Some(Language::SystemVerilog));
        assert_eq!(Language::from_extension("SVH"), Some(Language::SystemVerilog));
        assert_eq!(Language::from_extension("unknown"), None);
    }

    #[test]
    fn language_from_extension_handles_c_family() {
        assert_eq!(Language::from_extension("c"), Some(Language::C));
        assert_eq!(Language::from_extension("h"), Some(Language::C));
        assert_eq!(Language::from_extension("cpp"), Some(Language::Cpp));
        assert_eq!(Language::from_extension("hpp"), Some(Language::Cpp));
    }

    #[test]
    fn completion_source_variants_serialize_round_trip() {
        for s in [
            CompletionSource::Lsp,
            CompletionSource::AiFast,
            CompletionSource::AiDeep,
            CompletionSource::Cache,
        ] {
            let j = serde_json::to_string(&s).unwrap();
            let back: CompletionSource = serde_json::from_str(&j).unwrap();
            assert_eq!(s, back);
        }
    }

    #[test]
    fn api_version_is_one() {
        assert_eq!(LSP_FAÇADE_API_VERSION, 1);
    }
}
