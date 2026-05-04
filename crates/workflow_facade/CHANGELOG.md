# Changelog

All notable changes to `pccx-workflow-facade` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

SEMVER NOTE: pccx-lab is pre-1.0.  Every minor bump (`0.x.y` -> `0.{x+1}.0`)
may carry breaking public-API changes.  Pin to `=0.x` in downstream
`Cargo.toml` if you need a quiet upgrade path.

## [Unreleased]

_No changes yet._

## [0.1.0] - 2026-04-24

### Added

- Initial release as part of the pccx-lab workspace.
- LLM wrapper + extension registry for the pccx-ide. `ContextCompressor` + `SubagentRunner` traits scaffolded for Phase 2 parallel subagent orchestration.
