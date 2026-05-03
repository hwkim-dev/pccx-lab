# pccx-lab scripts

Small shell helpers for bootstrapping a fresh machine (human *or* AI agent)
to the point where `npm run tauri dev` works.

## Files

| Script                         | Purpose                                                         |
| ------------------------------ | --------------------------------------------------------------- |
| `setup_env.sh`                 | Install apt deps, Rust, Node 20, and fetch workspace deps.      |
| `run_dev.sh`                   | Launch the Tauri dev window with cargo+nvm pre-sourced.         |
| `doctor.sh`                    | Read-only environment diagnostic.  Prints versions + fixes.     |
| `pccx-lab-boundary-smoke.sh`   | Verify CLI/core boundary artifacts exist and JSON examples are valid. |
| `test-boundary-smoke-fixtures.sh` | Prove boundary smoke fails clearly on malformed or missing fixture roots. |
| `test-json-boundary-shapes.sh` | Validate documented CLI/core JSON example shapes and negative drift fixtures. |
| `validate-local.sh`            | Run the local PR-readiness gate: Rust, frontend, static guards, and boundary smoke. |

`npm run test:static` in `ui/` runs the local assistant guard against
production GUI/source copy, then runs fixture tests that prove forbidden
API-key, provider-call, overclaim wording, and runtime-claim examples
fail while safe local-only wording passes. The fixtures are inert test
text only; they do not add provider, credential, telemetry, or runtime
integration paths.

`scripts/pccx-lab-boundary-smoke.sh` checks the real repository by default.
Its explicit `--root <path>` option is for deterministic tests only:
`scripts/test-boundary-smoke-fixtures.sh` stages minimal boundary roots, proves
the positive fixture passes, and proves malformed JSON plus missing required
boundary examples fail with file paths and short reasons. These checks do not
add runtime, provider, MCP, launcher, IDE, network, or hardware execution.

`scripts/test-json-boundary-shapes.sh` validates required top-level and stable
nested fields for the documented JSON examples, then stages negative overlays
from `scripts/fixtures/json-boundary-shapes/` to prove missing fields and wrong
types fail with file path, boundary kind, and reason. It is parse-only and
shape-only; it does not run providers, launchers, IDE bridges, MCP runtimes,
network calls, or hardware flows.

## Typical flows

**Fresh machine:**

```bash
bash scripts/setup_env.sh       # installs everything
bash scripts/run_dev.sh         # opens the profiler window
```

**"Did my install actually work?"**

```bash
bash scripts/doctor.sh
```

**Partial re-run** (e.g., apt deps are fine but node_modules got wiped):

```bash
bash scripts/setup_env.sh install
```

**Full local validation before a PR:**

```bash
bash scripts/validate-local.sh
```

For an already-bootstrapped frontend loop, skip the clean npm reinstall:

```bash
PCCX_SKIP_NPM_CI=1 bash scripts/validate-local.sh
```

**Boundary smoke fixture loop:**

```bash
bash scripts/test-boundary-smoke-fixtures.sh
```

**JSON boundary shape fixture loop:**

```bash
bash scripts/test-json-boundary-shapes.sh
```

## For AI agents

- All scripts exit non-zero on first error (`set -euo pipefail`), so an agent
  can detect failure by exit code alone.
- All steps are **idempotent** — re-running `setup_env.sh` on an already-set
  machine is a no-op.
- `doctor.sh` prints, for each missing dependency, the exact remediation
  command — use it to decide the next action programmatically.
- New code, script, and test files should carry:
  `SPDX-License-Identifier: Apache-2.0` and `Copyright 2026 pccxai`.
  Keep shebangs on the first line and place shell comments immediately after.
