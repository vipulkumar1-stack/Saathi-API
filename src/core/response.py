"""Normalized wrapper around a requests.Response."""
from dataclasses import dataclass, field
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


@dataclass
class ApiResponse:
    status: int
    headers: dict
    data: Any
    raw_body: str
    duration_ms: float
    request_method: str
    request_url: str
    request_body: Optional[str] = None
    graphql_errors: Optional[list] = field(default=None)
    # Un-redacted request payload (the GraphQL query/operationName in particular) -
    # used only to derive a human-readable API name for reports. Never render this
    # into a report/attachment; use request_body (redacted) for that.
    request_json: Optional[Any] = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.graphql_errors

    @property
    def is_error(self) -> bool:
        return not self.ok

    def as_model(self, model: Type[M]) -> M:
        return model.model_validate(self.data)
