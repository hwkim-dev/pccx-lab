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
