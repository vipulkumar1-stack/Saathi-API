"""In-memory accumulator for the post-run Excel/email report.

Two lists are built up over the life of a pytest session:

- TEST_RESULTS: one row per test item (see `record_test_result`).
- EXCHANGES:    one row per HTTP call made through HttpClient (see
                `record_exchange`, wired in as an extra `reporter` callback
                alongside `attach_exchange` in conftest.py's `http` /
                `unauthed_http` fixtures).

`start_test`/`end_test` track which test is "current" so an exchange can be
attributed to it, and purge any exchanges already recorded for a node_id -
pytest.ini's `--reruns 1` re-executes a flaky test from scratch, and without
this a rerun would leave two overlapping sets of rows for the same test.
"""
import re
from typing import Any, Optional

TEST_RESULTS: list[dict] = []
EXCHANGES: list[dict] = []

_current_node_id: Optional[str] = None
_current_test_name: Optional[str] = None

_OP_NAME_RE = re.compile(r"\b(?:query|mutation)\s+(\w+)")
_ANON_FIELD_RE = re.compile(r"\{\s*(\w+)\s*[\(\{]")

_GRAPHQL_ERROR_LIMIT = 200


def start_test(node_id: str, name: str) -> None:
    """Mark `node_id` as the currently-running test and drop any exchanges
    already recorded for it (a rerun starting over)."""
    global _current_node_id, _current_test_name
    _current_node_id = node_id
    _current_test_name = name
    EXCHANGES[:] = [e for e in EXCHANGES if e["node_id"] != node_id]


def end_test() -> None:
    global _current_node_id, _current_test_name
    _current_node_id = None
    _current_test_name = None


def record_test_result(node_id: str, name: str, status: str, duration: float, error: str = "") -> None:
    """Record (or replace, on rerun) the outcome of one test item."""
    existing = next((r for r in TEST_RESULTS if r["node_id"] == node_id), None)
    row = {
        "node_id": node_id,
        "name": name,
        "status": status,
        "duration": duration,
        "error": error,
    }
    if existing is not None:
        existing.update(row)
    else:
        TEST_RESULTS.append(row)


def _service_of(url: str) -> str:
    # e.g. https://pre-apis.ambak.com/finex/api/v1/graphql -> "finex"
    path = url.split("://", 1)[-1].split("/", 1)
    segments = path[1].split("/") if len(path) > 1 else []
    return segments[0] if segments and segments[0] else "(unknown)"


def _graphql_api_name(payload: dict) -> tuple[str, str]:
    """Return (kind, api name) for a GraphQL request body."""
    query_text = (payload.get("query") or "").strip()
    kind = "mutation" if query_text.lower().startswith("mutation") else "query"

    op_name = payload.get("operationName")
    if op_name:
        return kind, op_name

    match = _OP_NAME_RE.search(query_text)
    if match:
        return kind, match.group(1)

    match = _ANON_FIELD_RE.search(query_text)
    if match:
        return kind, match.group(1)

    return kind, "(anonymous)"


def record_exchange(response: Any) -> None:
    """HttpClient `reporter` callback: append one row per HTTP exchange.

    `response` is a src.core.response.ApiResponse. Only derived, non-secret
    fields (method/URL/status/latency/operation name) are stored - never the
    raw request/response bodies.
    """
    payload = response.request_json if isinstance(response.request_json, dict) else None
    is_graphql = bool(payload and "query" in payload)

    if is_graphql:
        kind, api = _graphql_api_name(payload)
        method = response.request_method
    else:
        kind = "REST"
        api = response.request_url.rstrip("/").rsplit("/", 1)[-1] or "(root)"
        method = response.request_method

    graphql_error = ""
    if response.graphql_errors:
        first = response.graphql_errors[0]
        message = first.get("message") if isinstance(first, dict) else str(first)
        graphql_error = (message or "")[:_GRAPHQL_ERROR_LIMIT]

    EXCHANGES.append({
        "node_id": _current_node_id or "",
        "test": _current_test_name or "(session setup)",
        "service": _service_of(response.request_url),
        "api": api,
        "kind": kind,
        "method": method,
        "path": response.request_url,
        "status": response.status,
        "graphql_errors": graphql_error,
        "duration_ms": response.duration_ms,
        "result": "PASS" if response.ok else "FAIL",
    })


def reset() -> None:
    """Clear all accumulated state - used by tests of this module."""
    global _current_node_id, _current_test_name
    TEST_RESULTS.clear()
    EXCHANGES.clear()
    _current_node_id = None
    _current_test_name = None
