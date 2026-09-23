"""Attaches every HTTP exchange to the running Allure test, redacted.

Wired in as HttpClient's `reporter` callback (see conftest.py's `http`
fixture) - every request this suite makes shows up in the report with
its method/URL/status/duration and bodies, without a token, OTP, or
HMAC secret ever appearing in the attachment.
"""
import json

import allure

from src.core.response import ApiResponse
from src.utils.logger import redact


def attach_exchange(response: ApiResponse) -> None:
    summary = (
        f"{response.request_method} {response.request_url} "
        f"-> {response.status} ({response.duration_ms:.0f}ms)"
    )
    with allure.step(summary):
        if response.request_body:
            allure.attach(
                redact(response.request_body),
                name="request body",
                attachment_type=allure.attachment_type.JSON,
            )
        allure.attach(
            redact(response.raw_body),
            name="response body",
            attachment_type=allure.attachment_type.JSON,
        )
        if response.graphql_errors:
            allure.attach(
                json.dumps(response.graphql_errors, indent=2),
                name="graphql errors",
                attachment_type=allure.attachment_type.JSON,
            )
