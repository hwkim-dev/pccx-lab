# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

This is the **workspace-level** changelog.  Per-crate changelogs live
under each crate root and document library-level surface changes (see
`RELEASING.md` for the per-crate / workspace split).

## [Unreleased]

## v0.1.0-alpha — 2026-05-01

First public preview of the pccx-lab pre-RTL bottleneck profiler,
Rust + Tauri GUI, and CX live playground under the `pccxai`
organization. Mirrors the release notes at
[`docs/releases/v0.1.0-alpha.md`](docs/releases/v0.1.0-alpha.md).

### Highlights

- First public preview of the pccx-lab pre-RTL bottleneck profiler,
  Rust + Tauri GUI, and CX live playground under the `pccxai`
  organization.
- Docking layout with `flexlayout-react` and free-form panel splitting;
  occupancy calculator, metric tree browser, pipeline diagram,
  waveform annotation cursors, and synth resource heatmap.
- IPC DTO crate with `ts-rs` TypeScript generation, giving the Rust
  backend and the frontend a single source of truth for transport
  types.
- LSP integration: SystemVerilog hover, diagnostics, and ISA
  completion exposed through a Monaco bridge; CX language hover,
  completion, and diagnostics for the live playground.
- Verification surface: diff viewer, diagram panels, verification
  suite, speculative-tree verify, FSM state extraction with Mermaid
  rendering, and an HTML report engine.
- Remote session manager with RBAC and audit logs.
- Cargo formatting enforced in CI; the public validation workflow
  (`rust-check`, `frontend-check`) is required on `main`.

### Known limitations

- Performance numbers exposed by the UI come from the pre-RTL
  profiler model and are not silicon-measured throughput.
- LSP coverage is partial. ISA completion targets the v002 opcode set
  only; v003 is unsupported.
- The verification suite is wired against a small set of testbenches;
  larger suites land in v0.2.
- No standalone CLI yet. The profiler is exposed only through the GUI.
- The remote session manager has been validated on a single host;
  multi-tenant hardening (rate limiting, federation) is on the roadmap.

### Validation

- `cargo fmt --check` enforced on `main` through CI.
- `rust-check` and `frontend-check` required status checks green on
  `main`.
- Stage 1, 2, and 3 ruleset active; direct push to `main` blocked.
- IPC DTOs round-trip through `ts-rs` cleanly.
- No standalone-vendor brand-token leaks in tracked sources.

[Unreleased]: https://github.com/pccxai/pccx-lab/compare/HEAD...HEAD
