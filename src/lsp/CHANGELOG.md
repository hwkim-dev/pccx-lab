# Changelog

All notable changes to `pccx-lsp` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

SEMVER NOTE: pccx-lab is pre-1.0.  Every minor bump (`0.x.y` -> `0.{x+1}.0`)
may carry breaking public-API changes.

## [Unreleased]

_No changes yet._

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
