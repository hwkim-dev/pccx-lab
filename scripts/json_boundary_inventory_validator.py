#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 pccxai
"""Validate the documented JSON boundary inventory stays in sync."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from json import JSONDecodeError
from pathlib import Path
from typing import Any

INVENTORY_SCHEMA_VERSION = "pccx.lab.jsonBoundaryInventory.v0"

REQUIRED_ENTRY_FIELDS = [
    "boundaryKind",
    "examplePath",
    "producingCommand",
    "coreGeneratorOrReader",
    "readerOnly",
    "shapeValidation",
    "rustValidation",
    "docsAnchor",
]


class InventoryError(Exception):
    """Raised when the inventory file itself cannot be loaded."""


class ErrorCollector:
    def __init__(self, inventory_path: Path) -> None:
        self.inventory_path = inventory_path
        self.count = 0

    def fail(self, index: int | None, kind: str | None, field: str, reason: str) -> None:
        self.count += 1
        if index is None:
            subject = f"[{kind}]" if kind else "root"
        else:
            subject = f"entry[{index}] [{kind or '<unknown>'}]"
        print(
            f"[FAIL]  {self.inventory_path} {subject} field {field}: {reason}",
            file=sys.stderr,
        )


def type_name(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int) or isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InventoryError(f"missing inventory file: {path}") from error
    except JSONDecodeError as error:
        raise InventoryError(
            f"invalid JSON at line {error.lineno} column {error.colno}: {error.msg}"
        ) from error


def is_safe_relpath(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def markdown_anchor(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text.strip().lower())
    text = re.sub(r"[^a-z0-9 _-]+", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return re.sub(r"-+", "-", text)


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip()
        if heading:
            anchors.add(markdown_anchor(heading))
    return anchors


def load_shape_specs(repo_root: Path, errors: ErrorCollector) -> dict[str, str]:
    validator_path = repo_root / "scripts/json_boundary_shape_validator.py"
    if not validator_path.is_file():
        errors.fail(
            None,
            "shape-validator",
            "shapeValidation.validator",
            f"missing file {validator_path}",
        )
        return {}

    module_name = "pccx_json_boundary_shape_validator"
    spec = importlib.util.spec_from_file_location(module_name, validator_path)
    if spec is None or spec.loader is None:
        errors.fail(
            None,
            "shape-validator",
            "shapeValidation.validator",
            f"cannot load {validator_path}",
        )
        return {}

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return {item.kind: item.relpath for item in module.SPECS}


def check_file(
    repo_root: Path,
    errors: ErrorCollector,
    index: int,
    kind: str | None,
    field: str,
    value: Any,
) -> bool:
    if not isinstance(value, str):
        errors.fail(index, kind, field, f"expected string path, got {type_name(value)}")
        return False
    if not is_safe_relpath(value):
        errors.fail(index, kind, field, f"expected local relative path, got {value}")
        return False

    path = repo_root / value
    if not path.is_file():
        errors.fail(index, kind, field, f"missing file {value}")
        return False
    return True


def check_docs_anchor(
    repo_root: Path,
    errors: ErrorCollector,
    index: int,
    kind: str | None,
    value: Any,
) -> None:
    if not isinstance(value, str):
        errors.fail(index, kind, "docsAnchor", f"expected string, got {type_name(value)}")
        return
    if "#" not in value:
        errors.fail(index, kind, "docsAnchor", "expected docs path with markdown anchor")
        return

    relpath, anchor = value.split("#", 1)
    if not is_safe_relpath(relpath):
        errors.fail(index, kind, "docsAnchor", f"expected local relative path, got {relpath}")
        return

    path = repo_root / relpath
    if not path.is_file():
        errors.fail(index, kind, "docsAnchor", f"missing docs file {relpath}")
        return
    if path.suffix != ".md":
        return

    anchors = markdown_anchors(path)
    if anchor not in anchors:
        errors.fail(
            index,
            kind,
            "docsAnchor",
            f"missing markdown anchor #{anchor} in {relpath}",
        )


def expect_object(
    errors: ErrorCollector,
    index: int,
    kind: str | None,
    field: str,
    value: Any,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.fail(index, kind, field, f"expected object, got {type_name(value)}")
        return None
    return value


def expect_string(
    errors: ErrorCollector,
    index: int,
    kind: str | None,
    field: str,
    value: Any,
    *,
    allow_null: bool = False,
) -> str | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, str):
        errors.fail(index, kind, field, f"expected string, got {type_name(value)}")
        return None
    if not value:
        errors.fail(index, kind, field, "expected non-empty string")
        return None
    return value


def validate_entry(
    repo_root: Path,
    errors: ErrorCollector,
    shape_specs: dict[str, str],
    entry: Any,
    index: int,
) -> tuple[str | None, str | None]:
    if not isinstance(entry, dict):
        errors.fail(index, None, "entry", f"expected object, got {type_name(entry)}")
        return None, None

    raw_kind = entry.get("boundaryKind")
    kind = raw_kind if isinstance(raw_kind, str) else None
    for field in REQUIRED_ENTRY_FIELDS:
        if field not in entry:
            errors.fail(index, kind, field, "missing required field")

    kind = expect_string(errors, index, kind, "boundaryKind", entry.get("boundaryKind"))
    example_path = expect_string(errors, index, kind, "examplePath", entry.get("examplePath"))
    expect_string(
        errors,
        index,
        kind,
        "producingCommand",
        entry.get("producingCommand"),
        allow_null=True,
    )
    expect_string(
        errors,
        index,
        kind,
        "coreGeneratorOrReader",
        entry.get("coreGeneratorOrReader"),
    )

    reader_only = entry.get("readerOnly")
    if not isinstance(reader_only, bool):
        errors.fail(index, kind, "readerOnly", f"expected boolean, got {type_name(reader_only)}")
        reader_only = False

    if example_path is not None:
        check_file(repo_root, errors, index, kind, "examplePath", example_path)

    if kind is not None:
        expected_path = shape_specs.get(kind)
        if expected_path is None and not reader_only:
            errors.fail(
                index,
                kind,
                "boundaryKind",
                "not accepted by shape validator and readerOnly is false",
            )
        if expected_path is not None and example_path is not None and example_path != expected_path:
            errors.fail(
                index,
                kind,
                "boundaryKind",
                f"mismatched shape example path: expected {expected_path}, got {example_path}",
            )

    shape_validation = expect_object(
        errors, index, kind, "shapeValidation", entry.get("shapeValidation")
    )
    if shape_validation is not None:
        shape_kind = expect_string(
            errors,
            index,
            kind,
            "shapeValidation.kind",
            shape_validation.get("kind"),
        )
        if kind is not None and shape_kind is not None and shape_kind != kind:
            errors.fail(
                index,
                kind,
                "shapeValidation.kind",
                f"expected {kind}, got {shape_kind}",
            )
        check_file(
            repo_root,
            errors,
            index,
            kind,
            "shapeValidation.validator",
            shape_validation.get("validator"),
        )
        check_file(
            repo_root,
            errors,
            index,
            kind,
            "shapeValidation.fixtureTest",
            shape_validation.get("fixtureTest"),
        )

    rust_validation = expect_object(
        errors, index, kind, "rustValidation", entry.get("rustValidation")
    )
    if rust_validation is not None:
        rust_test_path = rust_validation.get("testPath")
        rust_test_name = expect_string(
            errors,
            index,
            kind,
            "rustValidation.testName",
            rust_validation.get("testName"),
        )
        if check_file(
            repo_root,
            errors,
            index,
            kind,
            "rustValidation.testPath",
            rust_test_path,
        ) and rust_test_name is not None:
            test_file = repo_root / rust_test_path
            test_text = test_file.read_text(encoding="utf-8")
            if re.search(rf"\bfn\s+{re.escape(rust_test_name)}\s*\(", test_text) is None:
                errors.fail(
                    index,
                    kind,
                    "rustValidation.testName",
                    f"missing Rust test {rust_test_name} in {rust_test_path}",
                )

    check_docs_anchor(repo_root, errors, index, kind, entry.get("docsAnchor"))
    return kind, example_path


def rust_example_paths(repo_root: Path) -> set[str]:
    test_path = repo_root / "crates/core/tests/json_boundary_examples.rs"
    if not test_path.is_file():
        return set()
    text = test_path.read_text(encoding="utf-8")
    names = re.findall(r'(?:parse_example|read_example)\("([^"]+\.json)"\)', text)
    return {f"docs/examples/{name}" for name in names}


def shape_script_example_paths(repo_root: Path) -> set[str]:
    script_path = repo_root / "scripts/test-json-boundary-shapes.sh"
    if not script_path.is_file():
        return set()
    text = script_path.read_text(encoding="utf-8")
    return set(re.findall(r"docs/examples/[A-Za-z0-9_.-]+\.json", text))


def validate_inventory(repo_root: Path, inventory_path: Path) -> int:
    errors = ErrorCollector(inventory_path)
    try:
        inventory = load_json(inventory_path)
    except InventoryError as error:
        errors.fail(None, None, "json", str(error))
        print(f"[FAIL]  inventory validation: {errors.count} failure(s)", file=sys.stderr)
        return 1

    shape_specs = load_shape_specs(repo_root, errors)
    if not isinstance(inventory, dict):
        errors.fail(None, None, "inventory", f"expected object, got {type_name(inventory)}")
        print(f"[FAIL]  inventory validation: {errors.count} failure(s)", file=sys.stderr)
        return 1

    schema = inventory.get("schemaVersion")
    if schema != INVENTORY_SCHEMA_VERSION:
        errors.fail(
            None,
            None,
            "schemaVersion",
            f"expected {INVENTORY_SCHEMA_VERSION}, got {schema}",
        )

    entries = inventory.get("boundaries")
    if not isinstance(entries, list):
        errors.fail(None, None, "boundaries", f"expected array, got {type_name(entries)}")
        print(f"[FAIL]  inventory validation: {errors.count} failure(s)", file=sys.stderr)
        return 1

    seen_kinds: dict[str, int] = {}
    seen_paths: dict[str, int] = {}
    listed_kinds: set[str] = set()
    listed_paths: set[str] = set()

    for index, entry in enumerate(entries):
        before = errors.count
        kind, example_path = validate_entry(repo_root, errors, shape_specs, entry, index)
        if kind is not None:
            listed_kinds.add(kind)
            if kind in seen_kinds:
                errors.fail(
                    index,
                    kind,
                    "boundaryKind",
                    f"duplicate boundary kind first listed at entry[{seen_kinds[kind]}]",
                )
            else:
                seen_kinds[kind] = index
        if example_path is not None:
            listed_paths.add(example_path)
            if example_path in seen_paths:
                errors.fail(
                    index,
                    kind,
                    "examplePath",
                    f"duplicate example path first listed at entry[{seen_paths[example_path]}]",
                )
            else:
                seen_paths[example_path] = index
        if errors.count == before and kind is not None:
            print(f"[PASS]  {inventory_path} [{kind}] inventory ok")

    for kind, relpath in shape_specs.items():
        if kind not in listed_kinds:
            errors.fail(None, kind, "boundaryKind", "shape validator kind is not listed")
        if relpath not in listed_paths:
            errors.fail(
                None,
                kind,
                "examplePath",
                f"shape validator example is not listed: {relpath}",
            )

    for relpath in sorted(rust_example_paths(repo_root)):
        if relpath not in listed_paths:
            errors.fail(
                None,
                "rust-example-tests",
                "rustValidation",
                f"Rust example test path is not listed: {relpath}",
            )

    for relpath in sorted(shape_script_example_paths(repo_root)):
        if relpath not in listed_paths:
            errors.fail(
                None,
                "shape-fixture-tests",
                "shapeValidation.fixtureTest",
                f"shape fixture example path is not listed: {relpath}",
            )

    if errors.count:
        print(f"[FAIL]  inventory validation: {errors.count} failure(s)", file=sys.stderr)
        return 1

    print("[INFO]  inventory validation: all checks passed")
    return 0


def main() -> int:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Validate pccx-lab JSON boundary inventory coverage."
    )
    parser.add_argument(
        "--root",
        default=default_root,
        type=Path,
        help="repository root used for local relative paths",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        help="inventory JSON file to validate",
    )
    args = parser.parse_args()

    repo_root = args.root.resolve()
    inventory_path = args.inventory
    if inventory_path is None:
        inventory_path = repo_root / "scripts/fixtures/json-boundary-inventory.json"
    return validate_inventory(repo_root, inventory_path.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
