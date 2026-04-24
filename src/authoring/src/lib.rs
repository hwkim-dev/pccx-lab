// Module Boundary: authoring/
// pccx-authoring: ISA + driver-API declarative specs (TOML-driven).
//
// Two companion modules:
//   * `isa_spec` — opcode / field / encoding declarations; emits SV
//                  package + doc tables from a single TOML source.
//   * `api_spec` — host-visible driver API (uca_init, uca_launch_gemm,
//                  uca_read_trace, …); emits C header + Rust FFI.
//
// Roadmap: Phase 5D (Model-to-ISA-API compiler) consumes these specs
// as ground truth for auto-generating model-specific driver code.

pub mod isa_spec;
pub mod api_spec;
