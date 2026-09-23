"""Process-wide settings, loaded once from the environment / .env file.

Auth findings (see AUTH_FINDINGS.md at the repo root): the gateway accepts
plain bearer-token auth on every service probed (finex, insurance, payout -
queries, and mutation input validation). The x-hmac-meta/x-hmac-signature
headers the Postman collection sends are NOT required; HMAC signing exists
in src/auth/hmac_signer.py but is disabled unless SEND_HMAC_HEADERS=1.
"""
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

from src.config.environments import EnvironmentProfile, MUTATION_SAFE_HOSTS, get_environment

load_dotenv()


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name}={raw!r} is not a valid integer") from None


@dataclass(frozen=True)
class Settings:
    environment: EnvironmentProfile
    base_url: str

    auth_token: Optional[str]
    auth_mobile: Optional[str]
    auth_otp: Optional[str]

    hmac_secret: Optional[str]
    send_hmac_headers: bool

    http_timeout: int
    http_retries: int
    http_debug: bool

    allow_mutations_flag: bool
    allow_external_mutations_flag: bool

    @property
    def allow_mutations(self) -> bool:
        """Three things must agree: the operator's flag, the environment
        profile, AND the resolved host actually being one we trust with
        writes. The host check exists because BASE_URL can override the
        profile's own host (see get_settings below) - without it,
        ENV=pre + BASE_URL=<prod host> + ALLOW_MUTATIONS=1 would still
        read as "allowed"."""
        hostname = urlparse(self.base_url).hostname
        return (
            self.allow_mutations_flag
            and self.environment.allow_mutations
            and hostname in MUTATION_SAFE_HOSTS
        )

    @property
    def allow_external_mutations(self) -> bool:
        """A second, stricter opt-in for mutations that reach a real
        external party (lender, credit bureau, paid provider) and can
        never be cleaned up. Requires allow_mutations to already be true -
        ALLOW_EXTERNAL_MUTATIONS=1 alone does nothing."""
        return self.allow_mutations and self.allow_external_mutations_flag

    def has_usable_auth(self) -> bool:
        return bool(self.auth_token) or bool(self.auth_mobile and self.auth_otp)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env_name = os.getenv("ENV", "pre")
    profile = get_environment(env_name)
    base_url = os.getenv("BASE_URL") or profile.base_url

    auth_token = os.getenv("AUTH_TOKEN") or None
    auth_mobile = os.getenv("AUTH_MOBILE") or None
    auth_otp = os.getenv("AUTH_OTP") or None

    settings = Settings(
        environment=profile,
        base_url=base_url,
        auth_token=auth_token,
        auth_mobile=auth_mobile,
        auth_otp=auth_otp,
        hmac_secret=os.getenv("HMAC_SECRET") or None,
        send_hmac_headers=_read_bool("SEND_HMAC_HEADERS", False),
        http_timeout=_read_int("HTTP_TIMEOUT", 20),
        http_retries=_read_int("HTTP_RETRIES", 2),
        http_debug=_read_bool("HTTP_DEBUG", False),
        allow_mutations_flag=_read_bool("ALLOW_MUTATIONS", False),
        allow_external_mutations_flag=_read_bool("ALLOW_EXTERNAL_MUTATIONS", False),
    )

    if not settings.has_usable_auth():
        raise RuntimeError(
            "No usable authentication configured. Set AUTH_TOKEN, or both "
            "AUTH_MOBILE and AUTH_OTP, in .env (see env.example.txt)."
        )

    if settings.allow_mutations_flag and profile.allow_mutations:
        hostname = urlparse(base_url).hostname
        if hostname not in MUTATION_SAFE_HOSTS:
            raise RuntimeError(
                f"ALLOW_MUTATIONS=1 was requested but BASE_URL resolves to "
                f"{hostname!r}, which is not a mutation-safe host "
                f"({sorted(MUTATION_SAFE_HOSTS)}). Refusing to start rather "
                f"than silently skipping mutation tests or, worse, running "
                f"them against the wrong host."
            )
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
