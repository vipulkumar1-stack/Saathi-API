"""Bearer token acquisition: static AUTH_TOKEN takes priority, else OTP login.

The OTP flow uses account/user/send_otp then account/user/validate_otp.
The mobile+OTP pair configured by default in env.example.txt is a fixed
test account on `pre` (send_otp always succeeds, validate_otp accepts the
same OTP every time) - confirmed working during suite setup.
"""
import json
import time
from pathlib import Path
from typing import Optional

import jwt as pyjwt
import requests

from src.config.settings import Settings
from src.utils.logger import get_logger, safe_repr

log = get_logger(__name__)

# The pre environment's OTP endpoint enforces a ~15s cooldown between
# send_otp calls for the same mobile number, which back-to-back local
# `pytest` invocations trip easily. Cache the acquired token on disk
# (gitignored) so repeated runs reuse it instead of re-logging in every
# time - safe here because the test account's JWT is long-lived (~30yr
# expiry observed), not a short session token.
_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / ".cache" / "otp_token.json"


class TokenAcquisitionError(RuntimeError):
    pass


class ITokenProvider:
    def get_token(self, force_refresh: bool = False) -> str:
        raise NotImplementedError

    def invalidate(self) -> None:
        pass


class StaticTokenProvider(ITokenProvider):
    def __init__(self, token: str):
        self._token = token

    def get_token(self, force_refresh: bool = False) -> str:
        return self._token


class OtpTokenProvider(ITokenProvider):
    """Logs in via OTP once per process and caches the resulting JWT."""

    def __init__(self, settings: Settings, session: Optional[requests.Session] = None):
        self._settings = settings
        self._session = session or requests.Session()
        self._token: Optional[str] = None

    def invalidate(self) -> None:
        self._token = None
        _clear_cache()

    def get_token(self, force_refresh: bool = False) -> str:
        if self._token and not force_refresh:
            return self._token
        if not force_refresh:
            cached = _load_cached_token(self._settings.auth_mobile)
            if cached:
                self._token = cached
                return self._token
        self._token = self._login()
        _store_cached_token(self._settings.auth_mobile, self._token)
        return self._token

    def _common_headers(self) -> dict:
        origin = self._settings.environment.frontend_origin
        return {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": origin,
            "referer": origin + "/",
        }

    def _login(self) -> str:
        base = self._settings.base_url
        mobile = self._settings.auth_mobile
        otp = self._settings.auth_otp
        if not (mobile and otp):
            raise TokenAcquisitionError(
                "OTP login requires AUTH_MOBILE and AUTH_OTP to be set (see env.example.txt)."
            )

        send_resp = self._session.post(
            f"{base}/account/user/send_otp",
            headers=self._common_headers(),
            json={"source": "onboarding", "mobile": mobile},
            timeout=self._settings.http_timeout,
        )
        if send_resp.status_code != 200:
            raise TokenAcquisitionError(
                f"send_otp failed: {send_resp.status_code} {safe_repr(send_resp.text)}"
            )

        headers = self._common_headers()
        headers["source"] = "onboarding"
        validate_resp = self._session.post(
            f"{base}/account/user/validate_otp",
            headers=headers,
            json={"otp": otp, "kind": "1", "mobile": mobile},
            timeout=self._settings.http_timeout,
        )
        if validate_resp.status_code != 200:
            raise TokenAcquisitionError(
                f"validate_otp failed: {validate_resp.status_code} {safe_repr(validate_resp.text)}"
            )

        body = validate_resp.json()
        token = (body.get("data") or {}).get("token")
        if not token:
            raise TokenAcquisitionError(
                f"validate_otp succeeded but no data.token in response: {safe_repr(body)}"
            )
        log.info("OTP login succeeded for mobile=%s", mobile)
        return token


def _load_cached_token(mobile: Optional[str]) -> Optional[str]:
    if not mobile or not _CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if cache.get("mobile") != mobile:
        return None
    token = cache.get("token")
    if not token:
        return None
    try:
        assert_token_sane(token)
    except TokenAcquisitionError:
        return None
    return token


def _store_cached_token(mobile: Optional[str], token: str) -> None:
    if not mobile:
        return
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps({"mobile": mobile, "token": token}))
    except OSError:
        pass  # caching is a convenience, never fatal


def _clear_cache() -> None:
    try:
        _CACHE_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def decode_claims_unsafe(token: str) -> dict:
    """Decode JWT claims WITHOUT verifying signature - for sanity checks only,
    never for trust decisions."""
    return pyjwt.decode(token, options={"verify_signature": False})


def assert_token_sane(token: str) -> None:
    """Fail fast with a clear message rather than letting a bad token
    surface as dozens of unrelated-looking 401s across the suite."""
    try:
        claims = decode_claims_unsafe(token)
    except Exception as exc:  # noqa: BLE001 - want a clear message regardless of cause
        raise TokenAcquisitionError(f"AUTH token is not a decodable JWT: {exc!r}") from exc

    exp = claims.get("exp")
    if exp is not None and exp < time.time():
        raise TokenAcquisitionError(f"AUTH token is expired (exp={exp}).")

    if "user_id" not in claims or "dealer_id" not in claims:
        raise TokenAcquisitionError(
            f"AUTH token is missing expected claims (user_id/dealer_id). "
            f"Got claims: {safe_repr(claims)}. This looks like a token from a "
            f"different app."
        )
