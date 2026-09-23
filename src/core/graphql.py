"""GraphQL POST helper.

Important: a GraphQL endpoint returns HTTP 200 even for business/validation
errors, with an `errors` array in the body. ApiResponse.ok already treats a
non-empty `errors` array as a failure (see src/core/response.py) - always
use `.ok` / `.graphql_errors`, never bare status-code checks, when asserting
on a GraphQL call.
"""
from typing import Any, Optional

from src.core.http_client import HttpClient
from src.core.response import ApiResponse
from src.spec.types import OperationDef


def graphql_call(
    http: HttpClient,
    path: str,
    query: str,
    variables: Optional[dict] = None,
    operation_name: Optional[str] = None,
    extra_headers: Optional[dict] = None,
    requires_auth: bool = True,
    retries: Optional[int] = None,
) -> ApiResponse:
    body: dict[str, Any] = {"query": query, "variables": variables or {}}
    if operation_name:
        body["operationName"] = operation_name
    return http.post(
        path, json_body=body, extra_headers=extra_headers, requires_auth=requires_auth,
        retries=retries,
    )


def call_operation(
    http: HttpClient,
    op: OperationDef,
    variables_override: Optional[dict] = None,
    requires_auth: bool = True,
    retries: Optional[int] = None,
) -> ApiResponse:
    """Replay a captured OperationDef, respecting whether its body declared
    a named operation. Anonymous captures (op.anonymous=True) must NOT be
    sent with an operationName - the query text never declared one, and
    the gateway rejects `operationName` referring to an operation that
    doesn't exist in the document (HTTP 400, "Unknown operation named
    ...") rather than just ignoring it.

    `retries` is passed straight through to HttpClient.request - pass
    retries=0 for mutations, so a commit-then-timeout is never replayed
    as a duplicate write (see tests/mutations/test_mutations.py).
    """
    variables = dict(op.variables)
    if variables_override:
        variables.update(variables_override)
    operation_name = None if op.anonymous else op.name
    return graphql_call(
        http, op.path, op.query, variables, operation_name=operation_name,
        requires_auth=requires_auth, retries=retries,
    )
