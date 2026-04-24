// Module Boundary: lsp/
// pccx-lsp: Phase 2 IntelliSense façade.
//
// Scaffold-only crate.  The real implementation (tower-lsp adapter,
// external-LSP multiplexer, AI completion cache keyed by AST hash)
// lands during Phase 2 proper.  Landing the crate now keeps the
// dependency graph stable while implementation follows.

use std::collections::HashMap;

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

// ─── Multiplexer (Phase 2 M2.1, A-slice) ─────────────────────────────
//
// `LspMultiplexer` routes a query to the right set of providers per
// `Language`.  It is the call-site counterpart of `pccx_core::plugin`:
// where `PluginRegistry<P>` holds a concrete `Vec<P>` (one plugin kind
// per registry), the multiplexer holds three heterogeneous trait
// objects per language because a single editor interaction touches
// all three surfaces (complete / hover / locate) at once.
//
// The scaffold is intentionally minimal:
//   - no async (the tower-lsp adapter lands in Phase 2 proper and
//     wraps this type, not the other way around),
//   - no dynamic reload (callers that need it wrap in Mutex / RwLock
//     and swap backends between queries),
//   - all three providers per language register atomically; partial
//     registration can be added later without breaking this API.

/// Provider triple the multiplexer stores per registered language.
/// Kept as `Send + Sync` so the multiplexer can move across thread
/// boundaries when pccx-ide spawns its async LSP adapter in Phase 2
/// proper.
struct LanguageBackends {
    completion: Box<dyn CompletionProvider + Send + Sync>,
    hover: Box<dyn HoverProvider + Send + Sync>,
    location: Box<dyn LocationProvider + Send + Sync>,
}

/// Routes a query to the registered backend triple for its language.
/// Returns `LspError::NoBackend` for any language that was never
/// registered.
#[derive(Default)]
pub struct LspMultiplexer {
    backends: HashMap<Language, LanguageBackends>,
}

impl LspMultiplexer {
    /// Empty multiplexer with no languages registered.
    pub fn new() -> Self {
        Self::default()
    }

    /// Registers (or replaces) the provider triple for a language.
    pub fn register(
        &mut self,
        language: Language,
        completion: Box<dyn CompletionProvider + Send + Sync>,
        hover: Box<dyn HoverProvider + Send + Sync>,
        location: Box<dyn LocationProvider + Send + Sync>,
    ) {
        self.backends.insert(
            language,
            LanguageBackends {
                completion,
                hover,
                location,
            },
        );
    }

    /// True iff `language` has a registered provider triple.
    pub fn has(&self, language: Language) -> bool {
        self.backends.contains_key(&language)
    }

    /// Languages currently registered, in unspecified order.
    pub fn registered_languages(&self) -> Vec<Language> {
        self.backends.keys().copied().collect()
    }

    fn dispatch(&self, language: Language) -> Result<&LanguageBackends, LspError> {
        self.backends
            .get(&language)
            .ok_or(LspError::NoBackend { lang: language })
    }

    /// Forwards a completion query to the registered backend.
    pub fn complete(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Vec<Completion>, LspError> {
        self.dispatch(language)?
            .completion
            .complete(language, file, pos, source)
    }

    /// Forwards a hover query to the registered backend.
    pub fn hover(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Option<Hover>, LspError> {
        self.dispatch(language)?
            .hover
            .hover(language, file, pos, source)
    }

    /// Forwards a go-to-definition query to the registered backend.
    pub fn definitions(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Vec<SourceRange>, LspError> {
        self.dispatch(language)?
            .location
            .definitions(language, file, pos, source)
    }

    /// Forwards a references query to the registered backend.
    pub fn references(
        &self,
        language: Language,
        file: &str,
        pos: SourcePos,
        source: &str,
    ) -> Result<Vec<SourceRange>, LspError> {
        self.dispatch(language)?
            .location
            .references(language, file, pos, source)
    }
}

// ─── NoopBackend (Phase 2 M2.1, A-slice) ─────────────────────────────
//
// Reference backend used in unit tests and as a deliberate "no data"
// answer in pccx-ide before a real backend (verible, rust-analyzer,
// AI layer) has been registered for a language.  All three providers
// return empty results rather than errors — "I have nothing for you
// here" is a valid LSP answer and the editor should silently omit
// the affordance rather than surface a failure toast.

/// Empty-answer backend.  Implements all three provider traits and
/// always returns "no data".
pub struct NoopBackend;

impl CompletionProvider for NoopBackend {
    fn complete(
        &self,
        _language: Language,
        _file: &str,
        _pos: SourcePos,
        _source: &str,
    ) -> Result<Vec<Completion>, LspError> {
        Ok(Vec::new())
    }
    fn name(&self) -> &'static str {
        "noop"
    }
}

impl HoverProvider for NoopBackend {
    fn hover(
        &self,
        _language: Language,
        _file: &str,
        _pos: SourcePos,
        _source: &str,
    ) -> Result<Option<Hover>, LspError> {
        Ok(None)
    }
    fn name(&self) -> &'static str {
        "noop"
    }
}

impl LocationProvider for NoopBackend {
    fn definitions(
        &self,
        _language: Language,
        _file: &str,
        _pos: SourcePos,
        _source: &str,
    ) -> Result<Vec<SourceRange>, LspError> {
        Ok(Vec::new())
    }
    fn references(
        &self,
        _language: Language,
        _file: &str,
        _pos: SourcePos,
        _source: &str,
    ) -> Result<Vec<SourceRange>, LspError> {
        Ok(Vec::new())
    }
    fn name(&self) -> &'static str {
        "noop"
    }
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

    // ─── Multiplexer + NoopBackend (M2.1 A-slice) ────────────────

    fn origin() -> SourcePos {
        SourcePos {
            line: 0,
            character: 0,
        }
    }

    #[test]
    fn noop_backend_returns_empty_completions() {
        let out = NoopBackend
            .complete(Language::SystemVerilog, "foo.sv", origin(), "")
            .expect("noop completion");
        assert!(out.is_empty());
    }

    #[test]
    fn noop_backend_returns_none_for_hover() {
        let out = NoopBackend
            .hover(Language::Rust, "foo.rs", origin(), "")
            .expect("noop hover");
        assert!(out.is_none());
    }

    #[test]
    fn noop_backend_returns_empty_definitions_and_references() {
        let defs = NoopBackend
            .definitions(Language::Python, "a.py", origin(), "")
            .expect("noop defs");
        let refs = NoopBackend
            .references(Language::Python, "a.py", origin(), "")
            .expect("noop refs");
        assert!(defs.is_empty());
        assert!(refs.is_empty());
    }

    #[test]
    fn multiplexer_starts_empty() {
        let m = LspMultiplexer::new();
        assert!(!m.has(Language::SystemVerilog));
        assert!(m.registered_languages().is_empty());
    }

    #[test]
    fn multiplexer_rejects_unregistered_language_with_no_backend() {
        let m = LspMultiplexer::new();
        let err = m
            .complete(Language::Rust, "x.rs", origin(), "")
            .expect_err("unregistered must error");
        match err {
            LspError::NoBackend { lang } => assert_eq!(lang, Language::Rust),
            other => panic!("expected NoBackend, got {other:?}"),
        }
    }

    #[test]
    fn multiplexer_dispatches_to_registered_noop_backend() {
        let mut m = LspMultiplexer::new();
        m.register(
            Language::SystemVerilog,
            Box::new(NoopBackend),
            Box::new(NoopBackend),
            Box::new(NoopBackend),
        );

        assert!(m.has(Language::SystemVerilog));
        assert_eq!(m.registered_languages(), vec![Language::SystemVerilog]);

        assert!(m
            .complete(Language::SystemVerilog, "t.sv", origin(), "")
            .unwrap()
            .is_empty());
        assert!(m
            .hover(Language::SystemVerilog, "t.sv", origin(), "")
            .unwrap()
            .is_none());
        assert!(m
            .definitions(Language::SystemVerilog, "t.sv", origin(), "")
            .unwrap()
            .is_empty());
        assert!(m
            .references(Language::SystemVerilog, "t.sv", origin(), "")
            .unwrap()
            .is_empty());
    }

    #[test]
    fn multiplexer_register_replaces_existing_triple() {
        // A completion provider tagged with a stable id so we can
        // confirm the second register() call wins.
        struct TaggedCompletion {
            id: &'static str,
        }
        impl CompletionProvider for TaggedCompletion {
            fn complete(
                &self,
                _: Language,
                _: &str,
                _: SourcePos,
                _: &str,
            ) -> Result<Vec<Completion>, LspError> {
                Ok(vec![Completion {
                    label: self.id.into(),
                    detail: None,
                    documentation: None,
                    insert_text: self.id.into(),
                    source: CompletionSource::Lsp,
                }])
            }
            fn name(&self) -> &'static str {
                "tagged"
            }
        }

        let mut m = LspMultiplexer::new();
        m.register(
            Language::Rust,
            Box::new(TaggedCompletion { id: "first" }),
            Box::new(NoopBackend),
            Box::new(NoopBackend),
        );
        m.register(
            Language::Rust,
            Box::new(TaggedCompletion { id: "second" }),
            Box::new(NoopBackend),
            Box::new(NoopBackend),
        );

        let out = m.complete(Language::Rust, "x.rs", origin(), "").unwrap();
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].label, "second");
    }
}
