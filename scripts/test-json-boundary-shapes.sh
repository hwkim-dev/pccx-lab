#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 pccxai
# Run deterministic shape checks for documented CLI/core JSON boundaries.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/json_boundary_shape_validator.py"
FIXTURE_ROOT="$REPO_ROOT/scripts/fixtures/json-boundary-shapes"
CASE_ROOT="$FIXTURE_ROOT/cases"
WORK_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

INFO() { printf '[INFO]  %s\n' "$*"; }
PASS() { printf '[PASS]  %s\n' "$*"; }
FAIL() { printf '[FAIL]  %s\n' "$*" >&2; }

FAILURES=0

stage_fixture() {
    local slug="$1"
    local root="$WORK_DIR/$slug"
    local case_dir="$CASE_ROOT/$slug"
    local overlay_dir="$case_dir/overlay"
    local remove_file="$case_dir/remove.txt"

    mkdir -p "$root/docs"
    cp -R "$REPO_ROOT/docs/examples" "$root/docs/examples"

    if [ -d "$overlay_dir" ]; then
        cp -R "$overlay_dir/." "$root"
    fi

    if [ -f "$remove_file" ]; then
        while IFS= read -r relative_path || [ -n "$relative_path" ]; do
            case "$relative_path" in
                ''|\#*) continue ;;
                /*|*..*)
                    FAIL "$slug remove.txt contains unsafe path: $relative_path"
                    FAILURES=$((FAILURES + 1))
                    continue
                    ;;
            esac
            rm -rf "$root/$relative_path"
        done < "$remove_file"
    fi

    printf '%s\n' "$root"
}

run_case() {
    local name="$1"
    local root="$2"
    local expected="$3"
    shift 3
    local output_file="$WORK_DIR/${name//[^a-zA-Z0-9]/_}.out"
    local status=0
    local output

    set +e
    python3 "$VALIDATOR" --root "$root" >"$output_file" 2>&1
    status=$?
    set -e

    output="$(cat "$output_file")"

    case "$expected:$status" in
        pass:0)
            ;;
        pass:*)
            FAIL "$name: expected pass, got exit $status"
            printf '%s\n' "$output" >&2
            FAILURES=$((FAILURES + 1))
            return
            ;;
        fail:0)
            FAIL "$name: expected failure, got pass"
            printf '%s\n' "$output" >&2
            FAILURES=$((FAILURES + 1))
            return
            ;;
        fail:*)
            ;;
        *)
            FAIL "$name: internal test error for expected=$expected status=$status"
            FAILURES=$((FAILURES + 1))
            return
            ;;
    esac

    local snippet
    for snippet in "$@"; do
        if ! grep -Fq "$snippet" "$output_file"; then
            FAIL "$name: missing output snippet: $snippet"
            printf '%s\n' "$output" >&2
            FAILURES=$((FAILURES + 1))
            return
        fi
    done

    PASS "$name"
}

INFO "JSON boundary shape fixture tests"
INFO "repo: $REPO_ROOT"
INFO "fixture cases: $CASE_ROOT"

run_case \
    "real docs examples" \
    "$REPO_ROOT" \
    pass \
    "shape validation: all checks passed" \
    "[lab-status] shape ok" \
    "[launcher-diagnostics-handoff] shape ok" \
    "[mcp-read-only-tool-plan] shape ok" \
    "[mcp-tool-list] shape ok" \
    "[mcp-tool-detail] shape ok" \
    "[mcp-read-only-analysis-flow] shape ok" \
    "[mcp-read-only-report-contract] shape ok" \
    "[mcp-verification-run-comparison] shape ok" \
    "[mcp-pr-summary-handoff] shape ok" \
    "[mcp-review-packet] shape ok" \
    "[mcp-evidence-manifest] shape ok" \
    "[mcp-permission-model] shape ok" \
    "[mcp-approval-request] shape ok" \
    "[mcp-approval-decision] shape ok" \
    "[mcp-invocation-request] shape ok" \
    "[mcp-blocked-invocation-result] shape ok" \
    "[mcp-audit-event] shape ok" \
    "[plugin-permission-model] shape ok" \
    "[plugin-audit-event] shape ok" \
    "[plugin-manifest-validation-result] shape ok" \
    "[plugin-capability-list] shape ok" \
    "[plugin-load-request] shape ok" \
    "[plugin-review-packet] shape ok" \
    "[plugin-boundary-plan] shape ok" \
    "[plugin-dry-run-flow] shape ok" \
    "[plugin-input-contract] shape ok" \
    "[plugin-trace-summary-input] shape ok" \
    "[plugin-output-contract] shape ok" \
    "[plugin-blocked-invocation-result] shape ok"

run_case \
    "missing status schema version" \
    "$(stage_fixture missing-status-schema-version)" \
    fail \
    "docs/examples/run-status.example.json" \
    "[lab-status]" \
    "missing required field $.schemaVersion"

run_case \
    "diagnostics list wrong type" \
    "$(stage_fixture diagnostics-list-wrong-type)" \
    fail \
    "docs/examples/diagnostics-envelope.example.json" \
    "[diagnostics-envelope]" \
    "expected array at $.diagnostics"

run_case \
    "theme presets wrong type" \
    "$(stage_fixture theme-presets-wrong-type)" \
    fail \
    "docs/examples/theme-tokens.example.json" \
    "[theme-tokens]" \
    "expected array at $.presets"

run_case \
    "missing descriptor list" \
    "$(stage_fixture workflow-descriptors-missing-list)" \
    fail \
    "docs/examples/workflow-descriptors.example.json" \
    "[workflow-descriptors]" \
    "missing required field $.descriptors"

run_case \
    "proposal item missing state" \
    "$(stage_fixture workflow-proposal-missing-state)" \
    fail \
    "docs/examples/workflow-proposals.example.json" \
    "[workflow-proposals]" \
    "missing required field $.proposals[].proposalState"

run_case \
    "workflow result max entries wrong type" \
    "$(stage_fixture workflow-results-max-entries-wrong-type)" \
    fail \
    "docs/examples/workflow-results.example.json" \
    "[workflow-results]" \
    "expected integer at $.maxEntries"

run_case \
    "runner result status missing" \
    "$(stage_fixture workflow-runner-status-missing)" \
    fail \
    "docs/examples/workflow-runner-blocked.example.json" \
    "[workflow-runner-result]" \
    "missing required field $.status"

run_case \
    "handoff safety flags missing" \
    "$(stage_fixture launcher-handoff-safety-flags-missing)" \
    fail \
    "docs/examples/launcher-diagnostics-handoff.example.json" \
    "[launcher-diagnostics-handoff]" \
    "missing required field $.safetyFlags"

run_case \
    "device session safety flags missing" \
    "$(stage_fixture launcher-device-session-safety-flags-missing)" \
    fail \
    "docs/examples/launcher-device-session-status.example.json" \
    "[launcher-device-session-status]" \
    "missing required field $.safetyFlags"

run_case \
    "mcp permission profiles missing" \
    "$(stage_fixture mcp-permission-profiles-missing)" \
    fail \
    "docs/examples/mcp-permission-model.example.json" \
    "[mcp-permission-model]" \
    "missing required field $.permissionProfiles"

run_case \
    "plugin permission profiles missing" \
    "$(stage_fixture plugin-permission-profiles-missing)" \
    fail \
    "docs/examples/plugin-permission-model.example.json" \
    "[plugin-permission-model]" \
    "missing required field $.permissionProfiles"

if [ "$FAILURES" -eq 0 ]; then
    INFO "JSON boundary shape fixture tests passed"
    exit 0
else
    FAIL "JSON boundary shape fixture tests: $FAILURES failure(s)"
    exit 1
fi
