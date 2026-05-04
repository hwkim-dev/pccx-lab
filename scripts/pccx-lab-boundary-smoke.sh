#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 pccxai
# scripts/pccx-lab-boundary-smoke.sh — verify key CLI/core boundary artifacts.
# Does not build the project. Does not run xsim. Does not require hardware.
# Exits 0 on success; exits 1 with diagnostics if an artifact is missing
# or malformed.

set -u

DEFAULT_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$DEFAULT_REPO_ROOT"

INFO() { printf '[INFO]  %s\n' "$*"; }
PASS() { printf '[PASS]  %s\n' "$*"; }
FAIL() { printf '[FAIL]  %s\n' "$*" >&2; }

usage() {
    cat <<'USAGE'
Usage: scripts/pccx-lab-boundary-smoke.sh [--root <repo-root>]

Without --root, checks the real pccx-lab repo. The explicit --root option is
for deterministic fixture tests; it does not run providers, hardware, browsers,
launchers, IDE integrations, or networked services.
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --root)
            if [ "$#" -lt 2 ]; then
                FAIL "missing path after --root"
                usage >&2
                exit 2
            fi
            if ! REPO_ROOT="$(cd "$2" 2>/dev/null && pwd)"; then
                FAIL "invalid --root path: $2"
                exit 2
            fi
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            FAIL "unknown argument: $1"
            usage >&2
            exit 2
            ;;
    esac
done

FAILURES=0

check_file() {
    if [ -f "$1" ]; then
        PASS "$1"
    else
        FAIL "missing: $1"
        FAILURES=$((FAILURES + 1))
    fi
}

INFO "pccx-lab CLI/core boundary smoke"
INFO "repo: $REPO_ROOT"

echo
INFO "planned boundary contracts:"
INFO "  diagnostics-envelope  (systemverilog-ide integration target)"
INFO "  lab-status-envelope   (CLI/core and GUI status surface)"
INFO "  theme-token-envelope  (theme-neutral presentation layer)"
INFO "  workflow-descriptors  (descriptor-only workflow catalog)"
INFO "  workflow-proposals    (proposal-only workflow previews)"
INFO "  workflow-results      (summary-only result metadata)"
INFO "  workflow-runner       (disabled-by-default allowlisted pilot)"
INFO "  sail-adoption-plan    (future descriptor-only Sail reference-model boundary)"
INFO "  sail-interface-boundary (future descriptor-only Sail CLI/core handoff boundary)"
INFO "  hybrid-strategy-plan  (future descriptor-only C++/SV and script control boundary)"
INFO "  hybrid-interface-boundary (future descriptor-only hybrid CLI/core handoff boundary)"
INFO "  hybrid-review-packet (future summary-only hybrid review packet)"
INFO "  launcher-diagnostics-handoff (read-only launcher handoff reader)"
INFO "  launcher-device-session-status (read-only launcher status reader)"
INFO "  mcp-read-only-tool-plan (future tool boundary map)"
INFO "  mcp-tool-list (future descriptor-only tool list shape)"
INFO "  mcp-tool-detail (future descriptor-only selected tool detail shape)"
INFO "  mcp-sample-plan (future descriptor-only sample tool plan)"
INFO "  mcp-sample-result (future descriptor-only sample result shape)"
INFO "  mcp-sample-catalog (future descriptor-only sample catalog shape)"
INFO "  mcp-sample-detail (future descriptor-only sample detail shape)"
INFO "  mcp-read-only-analysis-flow (future read-only flow contract)"
INFO "  mcp-read-only-report-contract (future summary report contract)"
INFO "  mcp-verification-run-comparison (future summary comparison contract)"
INFO "  mcp-pr-summary-handoff (future summary PR handoff contract)"
INFO "  mcp-review-packet (future summary review packet contract)"
INFO "  mcp-evidence-manifest (future summary evidence manifest contract)"
INFO "  mcp-evidence-detail (future descriptor-only evidence detail shape)"
INFO "  mcp-permission-model (future tool permission map)"
INFO "  mcp-approval-request (future tool approval request gate)"
INFO "  mcp-approval-decision (future tool approval decision gate)"
INFO "  mcp-invocation-request (future blocked tool invocation gate)"
INFO "  mcp-client-session-state (future blocked client/session state)"
INFO "  mcp-blocked-invocation-result (future blocked tool result gate)"
INFO "  mcp-audit-event (future redacted audit event shape)"
INFO "  plugin-boundary-plan (future plugin boundary map)"
INFO "  plugin-sample-plan (future descriptor-only sample plugin plan)"
INFO "  plugin-sample-result (future descriptor-only sample result shape)"
INFO "  plugin-sample-catalog (future descriptor-only sample catalog shape)"
INFO "  plugin-sample-detail (future descriptor-only sample detail shape)"
INFO "  plugin-manifest-validation-result (future plugin manifest validation result shape)"
INFO "  plugin-capability-list (future plugin capability list shape)"
INFO "  plugin-capability-detail (future plugin capability detail shape)"
INFO "  plugin-load-request (future blocked plugin load-request gate)"
INFO "  plugin-host-session-state (future blocked plugin host/session state)"
INFO "  plugin-invocation-request (future blocked plugin invocation request gate)"
INFO "  plugin-review-packet (future plugin review packet shape)"
INFO "  plugin-dry-run-flow (future plugin dry-run flow contract)"
INFO "  plugin-input-contract (future plugin summary input contract)"
INFO "  plugin-trace-summary-input (future plugin trace-summary input gate)"
INFO "  plugin-output-contract (future plugin summary output contract)"
INFO "  plugin-blocked-invocation-result (future blocked plugin result gate)"
INFO "  plugin-permission-model (future plugin permission map)"
INFO "  plugin-audit-event (future redacted plugin audit event shape)"
INFO "  trace-discovery       (headless CI path)"
INFO "  xsim-log-handoff      (pccx-FPGA verification loop)"

echo
INFO "docs presence"
check_file "$REPO_ROOT/docs/CLI_CORE_BOUNDARY.md"
check_file "$REPO_ROOT/docs/examples/diagnostics-envelope.example.json"
check_file "$REPO_ROOT/docs/examples/run-status.example.json"
check_file "$REPO_ROOT/docs/examples/theme-tokens.example.json"
check_file "$REPO_ROOT/docs/examples/workflow-descriptors.example.json"
check_file "$REPO_ROOT/docs/examples/workflow-proposals.example.json"
check_file "$REPO_ROOT/docs/examples/workflow-results.example.json"
check_file "$REPO_ROOT/docs/examples/workflow-runner-blocked.example.json"
check_file "$REPO_ROOT/docs/examples/sail-adoption-plan.example.json"
check_file "$REPO_ROOT/docs/examples/sail-interface-boundary.example.json"
check_file "$REPO_ROOT/docs/examples/hybrid-strategy-plan.example.json"
check_file "$REPO_ROOT/docs/examples/hybrid-interface-boundary.example.json"
check_file "$REPO_ROOT/docs/examples/hybrid-review-packet.example.json"
check_file "$REPO_ROOT/docs/examples/launcher-diagnostics-handoff.example.json"
check_file "$REPO_ROOT/docs/examples/launcher-device-session-status.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-read-only-tool-plan.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-tool-list.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-tool-detail.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-sample-plan.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-sample-result.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-sample-catalog.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-sample-detail.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-read-only-analysis-flow.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-read-only-report-contract.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-verification-run-comparison.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-pr-summary-handoff.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-review-packet.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-evidence-manifest.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-evidence-detail.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-permission-model.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-approval-request.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-approval-decision.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-invocation-request.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-client-session-state.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-blocked-invocation-result.example.json"
check_file "$REPO_ROOT/docs/examples/mcp-audit-event.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-boundary-plan.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-sample-plan.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-sample-result.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-sample-catalog.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-sample-detail.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-manifest-validation-result.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-capability-list.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-capability-detail.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-load-request.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-host-session-state.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-invocation-request.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-review-packet.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-dry-run-flow.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-input-contract.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-trace-summary-input.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-output-contract.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-blocked-invocation-result.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-permission-model.example.json"
check_file "$REPO_ROOT/docs/examples/plugin-audit-event.example.json"

echo
INFO "CLI command source presence"
check_file "$REPO_ROOT/crates/core/src/bin/pccx_lab.rs"
check_file "$REPO_ROOT/crates/core/src/status.rs"
check_file "$REPO_ROOT/crates/core/src/theme.rs"
check_file "$REPO_ROOT/crates/core/src/workflows.rs"
check_file "$REPO_ROOT/crates/core/src/proposals.rs"
check_file "$REPO_ROOT/crates/core/src/results.rs"
check_file "$REPO_ROOT/crates/core/src/runner.rs"
check_file "$REPO_ROOT/crates/core/src/device_session_status.rs"

echo
INFO "fixture presence"
check_file "$REPO_ROOT/fixtures/ok_module.sv"
check_file "$REPO_ROOT/fixtures/missing_endmodule.sv"
check_file "$REPO_ROOT/fixtures/empty.sv"

echo
INFO "JSON validity"
for f in "$REPO_ROOT/docs/examples/"*.example.json; do
    [ -f "$f" ] || continue
    if json_error="$(
        python3 - "$f" <<'PY' 2>&1
import json
import sys

path = sys.argv[1]

try:
    with open(path, encoding="utf-8") as handle:
        json.load(handle)
except Exception as error:
    print(f"{type(error).__name__}: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
    )"; then
        PASS "valid JSON: $f"
    else
        FAIL "invalid JSON: $f: $json_error"
        FAILURES=$((FAILURES + 1))
    fi
done

echo
if [ "$FAILURES" -eq 0 ]; then
    INFO "boundary smoke: all checks passed"
    exit 0
else
    FAIL "boundary smoke: $FAILURES check(s) failed"
    exit 1
fi
