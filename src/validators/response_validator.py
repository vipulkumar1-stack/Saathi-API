"""Fluent, chainable assertions over an ApiResponse.

Each check raises AssertionError with a message that includes the actual
response body (redacted), so a failure is diagnosable from the pytest
output alone. Wrap in Allure steps at the call site (see conftest.py) if
you want each assertion to show individually in a report.
"""
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from src.core.response import ApiResponse
from src.utils.logger import safe_repr

M = TypeVar("M", bound=BaseModel)


class ResponseValidator:
    def __init__(self, response: ApiResponse):
        self.response = response

    def _fail(self, message: str) -> None:
        raise AssertionError(f"{message}\n-- response --\n{safe_repr(self.response.raw_body, 2000)}")

    def status(self, expected: int) -> "ResponseValidator":
        if self.response.status != expected:
            self._fail(f"expected status {expected}, got {self.response.status}")
        return self

    def status_in(self, *expected: int) -> "ResponseValidator":
        if self.response.status not in expected:
            self._fail(f"expected status in {expected}, got {self.response.status}")
        return self

    def responded_within(self, max_ms: float) -> "ResponseValidator":
        if self.response.duration_ms > max_ms:
            self._fail(f"expected response within {max_ms}ms, took {self.response.duration_ms:.0f}ms")
        return self

    def no_graphql_errors(self) -> "ResponseValidator":
        """A GraphQL endpoint returns HTTP 200 even for business errors -
        this is the check that actually catches those."""
        if self.response.graphql_errors:
            self._fail(f"expected no GraphQL errors, got {safe_repr(self.response.graphql_errors)}")
        return self

    def has_graphql_errors(self) -> "ResponseValidator":
        if not self.response.graphql_errors:
            self._fail("expected GraphQL errors, got none")
        return self

    def field_equals(self, path: str, expected: Any) -> "ResponseValidator":
        actual = _dig(self.response.data, path)
        if actual != expected:
            self._fail(f"expected {path}=={expected!r}, got {actual!r}")
        return self

    def field_exists(self, path: str) -> "ResponseValidator":
        sentinel = object()
        if _dig(self.response.data, path, sentinel) is sentinel:
            self._fail(f"expected field {path} to exist")
        return self

    def field_is_array(self, path: str, min_length: int = 0) -> "ResponseValidator":
        actual = _dig(self.response.data, path)
        if not isinstance(actual, list):
            self._fail(f"expected {path} to be an array, got {type(actual).__name__}")
        if len(actual) < min_length:
            self._fail(f"expected {path} to have >= {min_length} items, got {len(actual)}")
        return self

    def matches(self, model: Type[M]) -> M:
        try:
            return model.model_validate(self.response.data)
        except Exception as exc:  # noqa: BLE001 - want the pydantic error surfaced clearly
            self._fail(f"response did not match schema {model.__name__}: {exc}")
            raise  # unreachable, keeps type checkers happy


def _dig(data: Any, path: str, default: Any = None) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def validate(response: ApiResponse) -> ResponseValidator:
    return ResponseValidator(response)
