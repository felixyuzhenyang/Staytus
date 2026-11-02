#!/usr/bin/env python3
"""Validate/export the reviewed OpenAPI 3.0 tool contract.

This deliberately does NOT rename FastAPI's 3.1 schema to 3.0. It maintains a
narrow source-owned 3.0 contract and checks it against the backend path surface.
Run from any directory: python scripts/export_openapi_3_0.py --check
"""

import argparse
import json
from pathlib import Path
import sys

import yaml
from openapi_spec_validator import validate_spec


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "orchestrate" / "tools" / "openapi.yaml"
FORBIDDEN_31 = {"$schema", "$id", "$defs", "const", "unevaluatedProperties", "prefixItems", "dependentSchemas"}


def check_schema(node, location="root"):
    if isinstance(node, dict):
        bad = FORBIDDEN_31.intersection(node)
        if bad:
            raise ValueError(f"Unsupported JSON Schema 2020-12 keywords at {location}: {sorted(bad)}")
        if isinstance(node.get("type"), list):
            raise ValueError(f"OpenAPI 3.0 does not permit type arrays: {location}")
        if node.get("type") == "null":
            raise ValueError(f"Use nullable in OpenAPI 3.0 instead of type:null: {location}")
        for key, value in node.items():
            check_schema(value, f"{location}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            check_schema(item, f"{location}[{index}]")


def validate_contract(spec):
    if spec.get("openapi") != "3.0.3":
        raise ValueError("Source contract must be genuine OpenAPI 3.0.3")
    check_schema(spec)
    validate_spec(spec)
    operations = set()
    for path, methods in spec["paths"].items():
        if not path.startswith("/tools/"):
            raise ValueError(f"Only the narrow tool gateway may be exported: {path}")
        if set(methods) != {"post"}:
            raise ValueError(f"Unexpected tool method: {path}")
        operation = methods["post"]["operationId"]
        if operation in operations:
            raise ValueError(f"Duplicate operationId: {operation}")
        operations.add(operation)
        if any(word in operation for word in ("approve", "execute", "confirm", "admin", "save_email", "create_calendar_event")):
            raise ValueError(f"Final writes/admin are not agent-callable: {operation}")
    return operations


def check_backend(spec, operations):
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app

    native = app.openapi()
    for path, methods in spec["paths"].items():
        native_operation = native["paths"].get(path, {}).get("post")
        if native_operation is None:
            raise ValueError(f"Exported endpoint absent in backend: {path}")
        if native_operation.get("operationId") != methods["post"]["operationId"]:
            raise ValueError(f"Operation ID drifted for {path}")
        exported_schema = resolve_ref(spec, methods["post"]["requestBody"])["content"]["application/json"]["schema"]
        exported_schema = resolve_ref(spec, exported_schema)
        native_body = native_operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
        native_body = resolve_ref(native, native_body)
        if set(exported_schema.get("properties", {})) != set(native_body.get("properties", {})):
            raise ValueError(f"Request fields drifted for {path}")
        if set(exported_schema.get("required", [])) != set(native_body.get("required", [])):
            raise ValueError(f"Required fields drifted for {path}")
    return operations


def resolve_ref(spec, node):
    while "$ref" in node:
        reference = node["$ref"]
        if not reference.startswith("#/"):
            raise ValueError("External references are intentionally unsupported")
        value = spec
        for segment in reference[2:].split("/"):
            value = value[segment.replace("~1", "/").replace("~0", "~")]
        node = value
    return node


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate and check backend contract; do not write output")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "openapi-3.0.json")
    args = parser.parse_args()
    spec = yaml.safe_load(SOURCE.read_text())
    operations = validate_contract(spec)
    check_backend(spec, operations)
    if not args.check:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Validated OpenAPI 3.0.3: {len(operations)} authenticated read/proposal tools; backend paths and request fields match.")


if __name__ == "__main__":
    main()
