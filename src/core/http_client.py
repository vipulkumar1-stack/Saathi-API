"""Thin requests.Session wrapper: default headers, auth injection, retries,
timing, and an optional exchange-reporter hook for report attachments.
"""
import time
from typing import Any, Callable, Optional

import requests

from src.auth.hmac_signer import build_hmac_headers
from src.auth.token_provider import ITokenProvider
from src.config.settings import Settings
from src.core.response import ApiResponse
from src.utils.logger import get_logger, safe_repr

log = get_logger(__name__)

RETRIABLE_STATUS = {429, 500, 502, 503, 504}

ExchangeReporter = Callable[[ApiResponse], None]


class HttpClient:
    """service_headers are extra per-call headers the collection captured
    for that service (e.g. api_source/app_type/apiv) - kept as data, not
    hardcoded per client, so the importer stays the single source of truth.
    """

    def __init__(
        self,
        settings: Settings,
        token_provider: Optional[ITokenProvider] = None,
        session: Optional[requests.Session] = None,
        reporter: Optional[ExchangeReporter] = None,
    ):
        self._settings = settings
        self._token_provider = token_provider
        self._session = session or requests.Session()
        self._reporter = reporter

    @property
    def base_url(self) -> str:
        return self._settings.base_url

    def _default_headers(self) -> dict:
        origin = self._settings.environment.frontend_origin
        return {
            "accept": "application/json, text/plain, */*",
            "origin": origin,
            "referer": origin + "/",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        extra_headers: Optional[dict] = None,
        requires_auth: bool = True,
        retries: Optional[int] = None,
    ) -> ApiResponse:
        url = path if path.startswith("http") else f"{self._settings.base_url}{path}"
        headers = self._default_headers()
        if extra_headers:
            headers.update(extra_headers)
        if json_body is not None:
            headers.setdefault("content-type", "application/json")

        if requires_auth and self._token_provider is not None:
            headers["authorization"] = f"Bearer {self._token_provider.get_token()}"

        if self._settings.send_hmac_headers and self._settings.hmac_secret:
            headers.update(build_hmac_headers(self._settings.hmac_secret))

        max_retries = self._settings.http_retries if retries is None else retries
        attempt = 0
        last_response: Optional[ApiResponse] = None

        while True:
            start = time.monotonic()
            raw = self._session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=self._settings.http_timeout,
            )
            duration_ms = (time.monotonic() - start) * 1000

            try:
                data = raw.json()
            except ValueError:
                data = None

            graphql_errors = None
            if isinstance(data, dict) and data.get("errors"):
                graphql_errors = data["errors"]

            response = ApiResponse(
                status=raw.status_code,
                headers=dict(raw.headers),
                data=data,
                raw_body=raw.text,
                duration_ms=duration_ms,
                request_method=method,
                request_url=url,
                request_body=safe_repr(json_body) if json_body is not None else None,
                graphql_errors=graphql_errors,
                request_json=json_body,
            )

            if self._settings.http_debug:
                log.info(
                    "%s %s -> %s in %.0fms body=%s",
                    method, url, response.status, duration_ms, safe_repr(response.raw_body, 500),
                )

            # One-shot retry on 401: token may have gone stale.
            if response.status == 401 and requires_auth and self._token_provider is not None and attempt == 0:
                self._token_provider.invalidate()
                headers["authorization"] = f"Bearer {self._token_provider.get_token(force_refresh=True)}"
                attempt += 1
                continue

            if response.status in RETRIABLE_STATUS and attempt < max_retries:
                retry_after = raw.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2 ** attempt, 8)
                attempt += 1
                last_response = response
                time.sleep(delay)
                continue

            if self._reporter is not None:
                try:
                    self._reporter(response)
                except Exception:  # noqa: BLE001 - reporting must never fail a request
                    log.exception("exchange reporter raised - ignoring")

            return response

    def get(self, path: str, **kwargs) -> ApiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, json_body: Any = None, **kwargs) -> ApiResponse:
        return self.request("POST", path, json_body=json_body, **kwargs)
