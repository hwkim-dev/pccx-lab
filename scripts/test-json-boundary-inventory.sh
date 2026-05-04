#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 pccxai
# Validate the JSON boundary inventory and deterministic negative fixtures.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/json_boundary_inventory_validator.py"
INVENTORY="$REPO_ROOT/scripts/fixtures/json-boundary-inventory.json"
CASE_ROOT="$REPO_ROOT/scripts/fixtures/json-boundary-inventory/cases"
WORK_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

INFO() { printf '[INFO]  %s\n' "$*"; }
PASS() { printf '[PASS]  %s\n' "$*"; }
FAIL() { printf '[FAIL]  %s\n' "$*" >&2; }

FAILURES=0

stage_inventory_fixture() {
    local slug="$1"
    local patch_file="$CASE_ROOT/$slug.json"
    local output_file="$WORK_DIR/$slug.inventory.json"

    python3 - "$INVENTORY" "$patch_file" "$output_file" <<'PY'
import json
import sys
from pathlib import Path

inventory_path = Path(sys.argv[1])
patch_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])

inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
patch = json.loads(patch_path.read_text(encoding="utf-8"))


def parent_for_path(root, path):
    current = root
    for part in path[:-1]:
        current = current[part]
    return current, path[-1]


for mutation in patch.get("set", []):
    parent, key = parent_for_path(inventory, mutation["path"])
    parent[key] = mutation["value"]

for path in patch.get("delete", []):
    parent, key = parent_for_path(inventory, path)
    del parent[key]

output_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
PY

    printf '%s\n' "$output_file"
}

run_case() {
    local name="$1"
    local inventory_path="$2"
    local expected="$3"
    shift 3
    local output_file="$WORK_DIR/${name//[^a-zA-Z0-9]/_}.out"
    local status=0
    local output

    set +e
    python3 "$VALIDATOR" --root "$REPO_ROOT" --inventory "$inventory_path" >"$output_file" 2>&1
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

INFO "JSON boundary inventory tests"
INFO "repo: $REPO_ROOT"
INFO "inventory: $INVENTORY"

run_case \
    "real boundary inventory" \
    "$INVENTORY" \
    pass \
    "inventory validation: all checks passed" \
    "[lab-status] inventory ok" \
    "[launcher-diagnostics-handoff] inventory ok" \
    "[mcp-read-only-tool-plan] inventory ok" \
    "[mcp-tool-list] inventory ok" \
    "[mcp-tool-detail] inventory ok" \
    "[mcp-read-only-report-contract] inventory ok" \
    "[mcp-verification-run-comparison] inventory ok" \
    "[mcp-pr-summary-handoff] inventory ok" \
    "[mcp-review-packet] inventory ok" \
    "[mcp-evidence-manifest] inventory ok" \
    "[mcp-evidence-detail] inventory ok" \
    "[mcp-permission-model] inventory ok" \
    "[mcp-approval-request] inventory ok" \
    "[mcp-approval-decision] inventory ok" \
    "[mcp-invocation-request] inventory ok" \
    "[mcp-blocked-invocation-result] inventory ok" \
    "[mcp-audit-event] inventory ok" \
    "[mcp-sample-catalog] inventory ok" \
    "[mcp-sample-detail] inventory ok" \
    "[sail-interface-boundary] inventory ok" \
    "[sail-review-packet] inventory ok" \
    "[sail-evidence-manifest] inventory ok" \
    "[hybrid-strategy-plan] inventory ok" \
    "[hybrid-interface-boundary] inventory ok" \
    "[hybrid-review-packet] inventory ok" \
    "[hybrid-evidence-manifest] inventory ok" \
    "[plugin-boundary-plan] inventory ok" \
    "[plugin-manifest-validation-result] inventory ok" \
    "[plugin-sample-catalog] inventory ok" \
    "[plugin-sample-detail] inventory ok" \
    "[plugin-capability-list] inventory ok" \
    "[plugin-capability-detail] inventory ok" \
    "[plugin-load-request] inventory ok" \
    "[plugin-review-packet] inventory ok" \
    "[plugin-dry-run-flow] inventory ok" \
    "[plugin-input-contract] inventory ok" \
    "[plugin-trace-summary-input] inventory ok" \
    "[plugin-output-contract] inventory ok" \
    "[plugin-blocked-invocation-result] inventory ok" \
    "[plugin-permission-model] inventory ok"

missing_path_inventory="$(stage_inventory_fixture missing-example-path)"
run_case \
    "missing example path fixture" \
    "$missing_path_inventory" \
    fail \
    "$missing_path_inventory" \
    "[diagnostics-envelope]" \
    "field examplePath" \
    "missing file docs/examples/not-present.example.json"

missing_field_inventory="$(stage_inventory_fixture missing-required-field)"
run_case \
    "missing required field fixture" \
    "$missing_field_inventory" \
    fail \
    "$missing_field_inventory" \
    "[lab-status]" \
    "field producingCommand" \
    "missing required field"

unknown_kind_inventory="$(stage_inventory_fixture unknown-boundary-kind)"
run_case \
    "unknown boundary kind fixture" \
    "$unknown_kind_inventory" \
    fail \
    "$unknown_kind_inventory" \
    "[not-a-json-boundary]" \
    "field boundaryKind" \
    "not accepted by shape validator"

mismatched_kind_inventory="$(stage_inventory_fixture mismatched-boundary-kind)"
run_case \
    "mismatched boundary kind fixture" \
    "$mismatched_kind_inventory" \
    fail \
    "$mismatched_kind_inventory" \
    "[lab-status]" \
    "field boundaryKind" \
    "mismatched shape example path"

missing_coverage_inventory="$(stage_inventory_fixture missing-coverage-path)"
run_case \
    "missing coverage path fixture" \
    "$missing_coverage_inventory" \
    fail \
    "$missing_coverage_inventory" \
    "[workflow-results]" \
    "field rustValidation.testPath" \
    "missing file crates/core/tests/missing_inventory_coverage.rs"

if [ "$FAILURES" -eq 0 ]; then
    INFO "JSON boundary inventory tests passed"
    exit 0
else
    FAIL "JSON boundary inventory tests: $FAILURES failure(s)"
    exit 1
fi
