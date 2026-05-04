// Module Boundary: verification/
// pccx-verification: end-to-end golden-model diff + robust config reader.
//
// Two sub-modules live here:
//   * `golden_diff`    — end-to-end correctness gate (consultation
//                        report §6.2).
//   * `robust_reader`  — 4-level (Strict / Warn / Fix / Lenient) TOML
//                        and JSON robustness policy used by the config
//                        readers in `isa_spec` / `api_spec`.

pub mod golden_diff;
pub mod robust_reader;

use pccx_core::trace::NpuTrace;

// ─── Experimental plugin surface (Phase 1 M1.2) ─────────────────────
//
// `VerificationGate` lets the pccx-ide Verify tab and CI pipelines plug
// different correctness-gate backends (golden-diff today; Sail
// refinement, UVM coverage, formal property check as they land).
//
// SEMVER NOTE: unstable until pccx-lab v0.3.  Held behind
// `Box<dyn VerificationGate>` everywhere so adding new gate kinds is
// source-compatible.

/// One-line verdict + opaque details from a single gate run.  Rendered
/// by the IDE as a status badge + expandable JSON tree.
#[derive(Debug, Clone)]
pub struct GateVerdict {
    pub gate: &'static str,
    pub passed: bool,
    pub summary: String,
    pub details: serde_json::Value,
}

/// A pluggable correctness-gate backend.  Checks a `.pccx` trace
/// against the gate's own reference oracle and returns a structured
/// verdict.
pub trait VerificationGate {
    /// Run the gate on a trace.  The reference oracle is held by
    /// `self` (e.g. a parsed `.ref.jsonl` for the golden-diff gate).
    fn check(&self, trace: &NpuTrace) -> GateVerdict;

    /// Stable short name (`"golden-diff"`, `"sail-refinement"`, …).
    fn name(&self) -> &'static str;
}

/// The flagship gate: compares a trace to a `.ref.jsonl` profile per
/// the consultation report §6.2 end-to-end contract.
pub struct GoldenDiffGate {
    reference: Vec<golden_diff::RefProfileRow>,
}

impl GoldenDiffGate {
    pub fn new(reference: Vec<golden_diff::RefProfileRow>) -> Self {
        Self { reference }
    }

    /// Build a gate from a `.ref.jsonl` string (one row per line).
    pub fn from_jsonl(src: &str) -> Result<Self, golden_diff::GoldenDiffError> {
        Ok(Self::new(golden_diff::parse_reference_jsonl(src)?))
    }
}

impl VerificationGate for GoldenDiffGate {
    fn check(&self, trace: &NpuTrace) -> GateVerdict {
        let report = golden_diff::diff(trace, &self.reference);
        let passed = report.is_clean();
        let summary = format!("{} / {} steps pass", report.pass_count, report.step_count);
        let details = serde_json::to_value(&report).unwrap_or(serde_json::Value::Null);
        GateVerdict {
            gate: "golden-diff",
            passed,
            summary,
            details,
        }
    }

    fn name(&self) -> &'static str {
        "golden-diff"
    }
}
