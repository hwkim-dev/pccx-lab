// isa_provider — ISA TOML completion provider
//
// Concrete `CompletionProvider` that returns context-aware completions
// when editing ISA definition TOML files (the `.toml` specs consumed by
// `pccx_authoring::isa_spec::IsaSpec`).  Provides:
//
//   - TOML structural tokens (`[[opcodes]]`, `[[reserved]]`, etc.)
//   - Schema key names for top-level, per-opcode, and per-field scopes
//   - Static pccx v002 mnemonics as a baseline
//   - Dynamic extraction of mnemonics and field names from the source
//     when it parses successfully
//
// Falls back to the static set silently on malformed / in-progress
// files — partial TOML must not produce errors in the editor.

use pccx_authoring::isa_spec::IsaSpec;

use crate::{Completion, CompletionProvider, CompletionSource, Language, LspError, SourcePos};

/// Static TOML section headers for ISA spec files.
const SECTION_HEADERS: &[(&str, &str, &str)] = &[
    (
        "[[opcodes]]",
        "Opcode definition table",
        "[[opcodes]]\nname = \"\"\nencoding = 0x00\ndescription = \"\"\nfields = []\n",
    ),
    (
        "[[reserved]]",
        "Reserved bit range",
        "[[reserved]]\nmsb = 0\nlsb = 0\n",
    ),
];

/// Top-level spec keys (outside any `[[opcodes]]` or `[[reserved]]`).
const TOP_LEVEL_KEYS: &[(&str, &str)] = &[
    (
        "name",
        "ISA name — used as identifier prefix in emitted code",
    ),
    ("width_bits", "Total instruction width in bits (8..128)"),
    ("version", "Optional version string (e.g. \"v002.0.0\")"),
    ("citation", "Optional research citation URL or arxiv id"),
    ("opcodes", "Opcode definition array"),
    ("reserved", "Reserved bit-range array"),
];

/// Per-opcode keys (inside `[[opcodes]]`).
const OPCODE_KEYS: &[(&str, &str)] = &[
    ("name", "Opcode mnemonic (ALL CAPS by convention)"),
    ("encoding", "Numerical encoding value (hex)"),
    (
        "opcode_field_bits",
        "Bit width of the opcode field (default 6)",
    ),
    ("fields", "Operand field list"),
    ("description", "Free-text description for docs"),
];

/// Per-field keys (inside `fields = [...]`).
const FIELD_KEYS: &[(&str, &str)] = &[
    ("name", "Operand field name"),
    ("msb", "High bit (MSB, inclusive)"),
    ("lsb", "Low bit (LSB, inclusive)"),
    ("description", "Optional doc string for this operand"),
];

/// Baseline pccx v002 mnemonics — always present so that completions
/// work even when the file is empty or unparseable.
const PCCX_V002_MNEMONICS: &[(&str, &str)] = &[
    ("GEMV", "General matrix-vector multiply"),
    ("GEMM", "General matrix-matrix multiply"),
    ("MEMCPY", "DMA copy"),
];

pub struct IsaCompletionProvider;

impl IsaCompletionProvider {
    pub fn new() -> Self {
        Self
    }

    /// Build the static completion set that is always returned.
    fn static_completions() -> Vec<Completion> {
        let mut out = Vec::new();

        // Section headers.
        for &(label, detail, insert) in SECTION_HEADERS {
            out.push(Completion {
                label: label.to_string(),
                detail: Some(detail.to_string()),
                documentation: None,
                insert_text: insert.to_string(),
                source: CompletionSource::Lsp,
            });
        }

        // Top-level keys.
        for &(key, desc) in TOP_LEVEL_KEYS {
            out.push(Completion {
                label: key.to_string(),
                detail: Some(format!("Top-level: {desc}")),
                documentation: None,
                insert_text: key.to_string(),
                source: CompletionSource::Lsp,
            });
        }

        // Per-opcode keys.
        for &(key, desc) in OPCODE_KEYS {
            out.push(Completion {
                label: key.to_string(),
                detail: Some(format!("Opcode: {desc}")),
                documentation: None,
                insert_text: key.to_string(),
                source: CompletionSource::Lsp,
            });
        }

        // Per-field keys.
        for &(key, desc) in FIELD_KEYS {
            out.push(Completion {
                label: key.to_string(),
                detail: Some(format!("Field: {desc}")),
                documentation: None,
                insert_text: key.to_string(),
                source: CompletionSource::Lsp,
            });
        }

        // Baseline pccx v002 mnemonics.
        for &(mnem, desc) in PCCX_V002_MNEMONICS {
            out.push(Completion {
                label: mnem.to_string(),
                detail: Some(format!("pccx v002 mnemonic: {desc}")),
                documentation: None,
                insert_text: mnem.to_string(),
                source: CompletionSource::Lsp,
            });
        }

        out
    }

    /// Try to parse the source as an ISA spec TOML and extract dynamic
    /// completions (opcode mnemonics, field names, encoding values).
    /// Returns an empty vec on parse failure — never errors.
    fn dynamic_completions(source: &str) -> Vec<Completion> {
        let spec = match IsaSpec::from_toml_str(source) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };

        let mut out = Vec::new();
        let mut seen_mnemonics = std::collections::HashSet::new();
        let mut seen_fields = std::collections::HashSet::new();

        for op in &spec.opcodes {
            // Deduplicate against the static baseline.
            if seen_mnemonics.insert(op.name.clone()) {
                out.push(Completion {
                    label: op.name.clone(),
                    detail: Some(if op.description.is_empty() {
                        format!("Opcode 0x{:X}", op.encoding)
                    } else {
                        format!("Opcode 0x{:X}: {}", op.encoding, op.description)
                    }),
                    documentation: None,
                    insert_text: op.name.clone(),
                    source: CompletionSource::Lsp,
                });
            }

            for f in &op.fields {
                if seen_fields.insert(f.name.clone()) {
                    out.push(Completion {
                        label: f.name.clone(),
                        detail: Some(format!("Field [{}..{}] ({} bits)", f.msb, f.lsb, f.width())),
                        documentation: None,
                        insert_text: f.name.clone(),
                        source: CompletionSource::Lsp,
                    });
                }
            }
        }

        out
    }
}

impl Default for IsaCompletionProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl CompletionProvider for IsaCompletionProvider {
    fn complete(
        &self,
        _language: Language,
        _file: &str,
        _pos: SourcePos,
        source: &str,
    ) -> Result<Vec<Completion>, LspError> {
        let mut items = Self::static_completions();
        items.extend(Self::dynamic_completions(source));
        Ok(items)
    }

    fn name(&self) -> &'static str {
        "isa-toml"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn origin() -> SourcePos {
        SourcePos {
            line: 0,
            character: 0,
        }
    }

    const SAMPLE_ISA_TOML: &str = r#"
        name = "pccx_v002"
        width_bits = 64
        version = "v002.0.0"

        [[opcodes]]
        name = "GEMV"
        encoding = 0x00
        description = "General matrix-vector multiply"
        fields = [
          { name = "dst",    msb = 57, lsb = 52 },
          { name = "src_a",  msb = 51, lsb = 46 },
          { name = "src_b",  msb = 45, lsb = 40 },
          { name = "tile_m", msb = 39, lsb = 32 },
        ]

        [[opcodes]]
        name = "GEMM"
        encoding = 0x01
        description = "General matrix-matrix multiply"
        fields = [
          { name = "dst",    msb = 57, lsb = 52 },
          { name = "src_a",  msb = 51, lsb = 46 },
          { name = "src_b",  msb = 45, lsb = 40 },
          { name = "tile_m", msb = 39, lsb = 32 },
          { name = "tile_n", msb = 31, lsb = 24 },
          { name = "tile_k", msb = 23, lsb = 16 },
        ]

        [[opcodes]]
        name = "MEMCPY"
        encoding = 0x02
        description = "DMA copy"
        fields = [
          { name = "dst", msb = 57, lsb = 52 },
          { name = "src", msb = 51, lsb = 46 },
          { name = "len", msb = 45, lsb = 16 },
        ]
    "#;

    #[test]
    fn empty_source_returns_static_set() {
        let provider = IsaCompletionProvider::new();
        let items = provider
            .complete(Language::SystemVerilog, "isa.toml", origin(), "")
            .expect("must not error");
        assert!(
            !items.is_empty(),
            "empty file must still yield static completions"
        );
    }

    #[test]
    fn sample_toml_extends_with_dynamic_completions() {
        let provider = IsaCompletionProvider::new();
        let items = provider
            .complete(
                Language::SystemVerilog,
                "isa.toml",
                origin(),
                SAMPLE_ISA_TOML,
            )
            .expect("must not error");
        let static_count = IsaCompletionProvider::static_completions().len();
        assert!(
            items.len() > static_count,
            "parsed TOML must add dynamic entries beyond the static set"
        );
    }

    #[test]
    fn malformed_toml_falls_back_to_static_set() {
        let provider = IsaCompletionProvider::new();
        let bad_source = "name = \"broken\"\n[[opcodes\n";
        let items = provider
            .complete(Language::SystemVerilog, "isa.toml", origin(), bad_source)
            .expect("must not error on malformed TOML");
        let static_count = IsaCompletionProvider::static_completions().len();
        assert_eq!(
            items.len(),
            static_count,
            "malformed TOML returns exactly the static set"
        );
    }

    #[test]
    fn completions_contain_known_pccx_mnemonics() {
        let provider = IsaCompletionProvider::new();
        let items = provider
            .complete(Language::SystemVerilog, "isa.toml", origin(), "")
            .expect("must not error");
        let labels: Vec<&str> = items.iter().map(|c| c.label.as_str()).collect();
        assert!(labels.contains(&"GEMV"), "must contain GEMV");
        assert!(labels.contains(&"GEMM"), "must contain GEMM");
        assert!(labels.contains(&"MEMCPY"), "must contain MEMCPY");
    }

    #[test]
    fn dynamic_completions_include_extracted_field_names() {
        let provider = IsaCompletionProvider::new();
        let items = provider
            .complete(
                Language::SystemVerilog,
                "isa.toml",
                origin(),
                SAMPLE_ISA_TOML,
            )
            .expect("must not error");
        let labels: Vec<&str> = items.iter().map(|c| c.label.as_str()).collect();
        assert!(
            labels.contains(&"dst"),
            "must contain extracted field 'dst'"
        );
        assert!(
            labels.contains(&"src_a"),
            "must contain extracted field 'src_a'"
        );
        assert!(
            labels.contains(&"tile_m"),
            "must contain extracted field 'tile_m'"
        );
        assert!(
            labels.contains(&"tile_k"),
            "must contain extracted field 'tile_k'"
        );
    }

    #[test]
    fn all_completions_use_lsp_source() {
        let provider = IsaCompletionProvider::new();
        let items = provider
            .complete(
                Language::SystemVerilog,
                "isa.toml",
                origin(),
                SAMPLE_ISA_TOML,
            )
            .expect("must not error");
        for c in &items {
            assert_eq!(c.source, CompletionSource::Lsp);
        }
    }

    #[test]
    fn all_completions_have_detail_set() {
        let provider = IsaCompletionProvider::new();
        let items = provider
            .complete(
                Language::SystemVerilog,
                "isa.toml",
                origin(),
                SAMPLE_ISA_TOML,
            )
            .expect("must not error");
        for c in &items {
            assert!(
                c.detail.is_some(),
                "every completion must carry a detail string, label: {}",
                c.label
            );
        }
    }

    #[test]
    fn section_headers_have_snippet_insert_text() {
        let provider = IsaCompletionProvider::new();
        let items = provider
            .complete(Language::SystemVerilog, "isa.toml", origin(), "")
            .expect("must not error");
        let opcodes_item = items
            .iter()
            .find(|c| c.label == "[[opcodes]]")
            .expect("must have [[opcodes]] completion");
        assert!(
            opcodes_item.insert_text.contains("name = "),
            "[[opcodes]] insert_text should include a template skeleton"
        );
    }

    #[test]
    fn provider_name_is_isa_toml() {
        let provider = IsaCompletionProvider::new();
        assert_eq!(provider.name(), "isa-toml");
    }

    #[test]
    fn default_construction_matches_new() {
        let _a = IsaCompletionProvider::new();
        let _b = IsaCompletionProvider::default();
        // Both are unit structs — this just confirms Default is wired.
    }
}
