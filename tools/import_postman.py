#!/usr/bin/env python3
"""Import postman/collection_raw.json into src/spec/operations.py (GraphQL)
and src/spec/endpoints.py (REST).

Regenerate after re-exporting the Postman collection:
    python3 tools/import_postman.py

Do not hand-edit the generated files - fix this importer instead.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTION_PATH = ROOT / "postman" / "collection_raw.json"
OPERATIONS_OUT = ROOT / "src" / "spec" / "operations.py"
ENDPOINTS_OUT = ROOT / "src" / "spec" / "endpoints.py"

# Third-party noise captured alongside the real API traffic - not part of
# the platform under test.
EXCLUDED_HOST_SUBSTRINGS = (
    "jam.dev",
    "monitoring.jam.dev",
    "freshdesk.com",
    "freshworks.com",
    "static.ambak.com",
)

OP_NAME_RE = re.compile(r"(query|mutation)\s+([A-Za-z_][A-Za-z0-9_]*)")
# Headers that are per-request auth/signing artifacts, not service config -
# don't carry these into the generated spec (they're handled by the HTTP
# client / auth layer).
SKIP_HEADER_KEYS = {"authorization", "x-hmac-meta", "x-hmac-signature", "content-length"}


def to_snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_")
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", s)
    return s.lower()


def iter_leaf_items(items):
    for item in items:
        if item.get("item"):
            yield from iter_leaf_items(item["item"])
        else:
            yield item


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else ""


def path_of(url: str) -> str:
    """Path including any query string - GET endpoints in this collection
    frequently carry required params there (e.g. ?dealer_id_hash=...), so
    dropping it silently breaks the endpoint."""
    m = re.match(r"https?://[^/]+(/.*)", url)
    return m.group(1) if m else "/"


def service_of(path: str) -> str:
    return path.split("?")[0].strip("/").split("/")[0] or "unknown"


def is_excluded(host: str) -> bool:
    return any(sub in host for sub in EXCLUDED_HOST_SUBSTRINGS)


def extract_headers(item) -> dict:
    headers = {}
    for h in (item.get("request", {}).get("header") or []):
        key = (h.get("key") or "").strip()
        if not key or key.lower() in SKIP_HEADER_KEYS:
            continue
        if h.get("disabled"):
            continue
        headers[key] = h.get("value", "")
    return headers


def is_graphql_body(body) -> bool:
    """Detect GraphQL by body shape, not URL. bank-integration and
    reporting-api speak GraphQL over a plain /api/v1 path with no
    "graphql" in the URL at all - relying on the URL substring
    misclassified them as opaque REST bodies, which is how a real
    mutation (SelectPropertyType) slipped past write-detection during
    suite verification. See AUTH_FINDINGS.md."""
    return isinstance(body, dict) and isinstance(body.get("query"), str) and body["query"].strip() != ""


def parse_graphql_item(item, service: str, path: str, body: dict):
    query = body.get("query", "")
    variables = body.get("variables") or {}
    op_name = body.get("operationName")
    anonymous = False

    if not op_name:
        m = OP_NAME_RE.search(query)
        if m:
            op_name = m.group(2)
        else:
            op_name = to_snake(item.get("name", "unnamed"))
            anonymous = True

    kind = "mutation" if re.search(r"^\s*mutation\b", query) else "query"

    return {
        "service": service,
        "name": op_name,
        "kind": kind,
        "path": path,
        "query": query,
        "variables": variables,
        "anonymous": anonymous,
        "confidence": "inferred" if anonymous else "confirmed",
    }


def parse_rest_item(item, service: str, path: str, method: str, body):
    return {
        "service": service,
        "name": to_snake(item.get("name", "unnamed")),
        "method": method,
        "path": path,
        "headers": extract_headers(item),
        "body": body,
        "confidence": "confirmed",
    }


def main():
    collection = json.loads(COLLECTION_PATH.read_text())["collection"]
    operations = []
    endpoints = []
    excluded_count = 0
    seen_op_names = {}

    for item in iter_leaf_items(collection.get("item", [])):
        request = item.get("request")
        if not request:
            continue
        url_raw = (request.get("url") or {}).get("raw", "")
        if not url_raw:
            continue
        host = host_of(url_raw)
        if is_excluded(host):
            excluded_count += 1
            continue

        path = path_of(url_raw)
        method = request.get("method", "GET").upper()
        service = service_of(path)

        raw = (request.get("body") or {}).get("raw")
        body = None
        if raw:
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = None

        if is_graphql_body(body):
            op = parse_graphql_item(item, service, path, body)
            # disambiguate duplicate operation names within a service
            key = (op["service"], op["name"])
            seen_op_names[key] = seen_op_names.get(key, 0) + 1
            if seen_op_names[key] > 1:
                op["name"] = f'{op["name"]}_{seen_op_names[key]}'
            operations.append(op)
            continue

        endpoints.append(parse_rest_item(item, service, path, method, body))

    write_operations(operations)
    write_endpoints(endpoints)

    print(f"Imported {len(operations)} GraphQL operations, {len(endpoints)} REST endpoints, "
          f"excluded {excluded_count} third-party requests.")
    anon = sum(1 for o in operations if o["anonymous"])
    mutations = sum(1 for o in operations if o["kind"] == "mutation")
    print(f"  {mutations} mutations, {anon} anonymous-body operations (name derived from request title).")


def write_operations(operations):
    lines = [
        '"""GENERATED by tools/import_postman.py from postman/collection_raw.json.',
        "",
        "Do not hand-edit - re-run the importer instead.",
        '"""',
        "from src.spec.types import OperationDef",
        "",
        "OPERATIONS = [",
    ]
    for op in operations:
        lines.append("    OperationDef(")
        lines.append(f"        service={op['service']!r},")
        lines.append(f"        name={op['name']!r},")
        lines.append(f"        kind={op['kind']!r},")
        lines.append(f"        path={op['path']!r},")
        lines.append(f"        query={op['query']!r},")
        lines.append(f"        variables={op['variables']!r},")
        lines.append(f"        anonymous={op['anonymous']!r},")
        lines.append(f"        confidence={op['confidence']!r},")
        lines.append("    ),")
    lines.append("]")
    OPERATIONS_OUT.write_text("\n".join(lines) + "\n")


def write_endpoints(endpoints):
    lines = [
        '"""GENERATED by tools/import_postman.py from postman/collection_raw.json.',
        "",
        "Do not hand-edit - re-run the importer instead.",
        '"""',
        "from src.spec.types import EndpointDef",
        "",
        "ENDPOINTS = [",
    ]
    for ep in endpoints:
        lines.append("    EndpointDef(")
        lines.append(f"        service={ep['service']!r},")
        lines.append(f"        name={ep['name']!r},")
        lines.append(f"        method={ep['method']!r},")
        lines.append(f"        path={ep['path']!r},")
        lines.append(f"        headers={ep['headers']!r},")
        lines.append(f"        body={ep['body']!r},")
        lines.append(f"        confidence={ep['confidence']!r},")
        lines.append("    ),")
    lines.append("]")
    ENDPOINTS_OUT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
