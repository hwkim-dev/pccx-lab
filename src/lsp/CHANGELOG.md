# Changelog

All notable changes to `pccx-lsp` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

SEMVER NOTE: pccx-lab is pre-1.0.  Every minor bump (`0.x.y` -> `0.{x+1}.0`)
may carry breaking public-API changes.

## [Unreleased]

### Added

- `LspMultiplexer` — per-`Language` registry of
  `(CompletionProvider, HoverProvider, LocationProvider)` trait-object
  triples.  Forwards queries to the registered triple; returns
  `LspError::NoBackend` for unregistered languages.  Partial /
  per-provider registration can be added later without breaking this
  API.  (Phase 2 M2.1, A-slice.)
- `NoopBackend` — reference backend implementing all three provider
  traits with empty-data answers.  Used by unit tests and as a safe
  default in pccx-ide before real backends register.
- Unit tests covering empty-init, unregistered-language rejection,
  full dispatch-through-noop, and register-replaces-existing
  semantics.

### Notes

- `tower-lsp` / `lsp-types` are **not** added as dependencies in this
  slice.  `tower_lsp::LanguageServer` is fully async while the
  `CompletionProvider` / `HoverProvider` / `LocationProvider` surface
  is sync; the tower-lsp adapter + sync-to-async bridge land together
  during Phase 2 proper (Weeks 6-9) so the scaffold stays free of
  runtime dependencies it does not yet exercise.

## [0.1.0] - 2026-04-24

### Added

- Initial release as part of the pccx-lab workspace.
- Phase 2 Language Server Protocol façade scaffold.
- `CompletionProvider`, `HoverProvider`, `LocationProvider` traits.
- `Language` enum covering SV / Rust / C / C++ / Python / Sail / MyST / RST.
- `SourcePos` / `SourceRange` / `Completion` / `Hover` types that line
  up with `lsp-types` so the tower-lsp adapter can cast directly.
- `CompletionSource` enum distinguishing Lsp / AiFast / AiDeep / Cache
  so pccx-ide can badge completions by provenance.
