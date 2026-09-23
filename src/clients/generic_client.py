"""A generic client over the imported spec.

Rather than one hand-written method per operation (79 GraphQL + 42 REST,
still growing as the collection is re-exported), tests call operations by
name against this client. It's still a real HTTP call with real
validation - "generic" describes how the call is dispatched, not how
thoroughly the response is checked.

Use src/clients/finex.py-style modules (see finex.py) when a test wants a
named, IDE-discoverable method instead of a string lookup.
"""
from typing import Any, Dict, Optional

from src.core.graphql import call_operation
from src.core.http_client import HttpClient
from src.core.response import ApiResponse
from src.spec.endpoints import ENDPOINTS
from src.spec.operations import OPERATIONS
from src.spec.types import EndpointDef, OperationDef

_OPERATIONS_BY_KEY = {(o.service, o.name): o for o in OPERATIONS}
_ENDPOINTS_BY_KEY = {(e.service, e.name): e for e in ENDPOINTS}


class GenericClient:
    def __init__(self, http: HttpClient):
        self.http = http

    def operation(self, service: str, name: str) -> OperationDef:
        try:
            return _OPERATIONS_BY_KEY[(service, name)]
        except KeyError:
            raise KeyError(
                f"No imported GraphQL operation {service}.{name}. "
                f"Known operations for {service}: "
                f"{sorted(n for (s, n) in _OPERATIONS_BY_KEY if s == service)}"
            ) from None

    def endpoint(self, service: str, name: str) -> EndpointDef:
        try:
            return _ENDPOINTS_BY_KEY[(service, name)]
        except KeyError:
            raise KeyError(
                f"No imported REST endpoint {service}.{name}. "
                f"Known endpoints for {service}: "
                f"{sorted(n for (s, n) in _ENDPOINTS_BY_KEY if s == service)}"
            ) from None

    def call_operation(
        self,
        service: str,
        name: str,
        variables_override: Optional[Dict[str, Any]] = None,
        requires_auth: bool = True,
    ) -> ApiResponse:
        op = self.operation(service, name)
        return call_operation(self.http, op, variables_override, requires_auth=requires_auth)

    def call_endpoint(
        self,
        service: str,
        name: str,
        body_override: Optional[Dict[str, Any]] = None,
        requires_auth: bool = True,
    ) -> ApiResponse:
        ep = self.endpoint(service, name)
        body = dict(ep.body) if ep.body else None
        if body_override:
            body = {**(body or {}), **body_override}
        return self.http.request(
            ep.method, ep.path, json_body=body, requires_auth=requires_auth,
        )
