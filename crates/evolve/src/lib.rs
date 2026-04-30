// Module Boundary: evolve/
// pccx-evolve: design-space exploration + evolutionary-search primitives.
//
// Current sub-module:
//   * `speculative` — data primitives for EAGLE-family tree speculative
//                     decoding; longest matching prefix, per-step accept
//                     stats, p50/p95 aggregation.  No I/O.
//
// Planned (Phase 5):
//   * `surrogate`   — lightweight GNN predictor of area/power/delay
//                     from RTL AST features.
//   * `evo_loop`    — population + mutation + crossover loop.
//   * `prm_gate`    — process-reward model filter (Verilator + lint
//                     + timing sanity) on LLM-proposed candidates.

pub mod speculative;

// ─── Unstable Phase 5 plugin API (Phase 1 M1.2) ──────────────────────
//
// Three trait scaffolds so Phase 5 can start landing `impl`s without
// touching the crate structure.  All are generic over the RTL
// individual type so the chip-DSE (RTL candidates) and compiler-DSE
// (LLVM pass orderings) loops can share machinery.
//
// SEMVER NOTE: every trait here is unstable and expected to evolve
// through Phase 5.  Do not ship public APIs that depend on these
// trait shapes before pccx-lab v0.5.

/// Predicts a cost metric (area / power / delay / fmax) from a
/// description of a design candidate — fast neural-network surrogate
/// trained on historical synth runs.
pub trait SurrogateModel {
    type Input;
    type Output;

    /// Cheap forward pass.  Latency target: < 10 ms per query so the
    /// evolutionary loop can sweep thousands of candidates per minute.
    fn predict(&self, input: &Self::Input) -> Self::Output;

    /// Model identifier for logging / dashboard display.
    fn name(&self) -> &'static str;
}

/// One step of an evolutionary loop — mutate or crossover individuals
/// of the same kind.  The implementation owns all randomness.
pub trait EvoOperator {
    type Individual;

    fn mutate(&self, individual: &Self::Individual) -> Self::Individual;
    fn crossover(&self, a: &Self::Individual, b: &Self::Individual) -> Self::Individual;
}

/// Process-reward model gate — yes/no admission check for
/// LLM-proposed candidates.  Runs cheap static filters (Verilator
/// elaborate, verible-lint, basic timing sanity) before the costly
/// synth call.
pub trait PRMGate {
    /// Input is the raw candidate source (RTL, LLVM IR, kernel C…).
    /// Returns a score in [0.0, 1.0]; higher = better.  Callers can
    /// reject anything under a threshold to keep the population clean.
    fn score(&self, candidate_source: &str) -> f64;

    fn name(&self) -> &'static str;
}
