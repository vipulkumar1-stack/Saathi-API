"""Named environment profiles for the Saathi API gateway.

`pre-saathi.ambak.com` is the frontend the tests are exercising, but every
request actually goes to the API gateway host below (pre-apis.ambak.com).
The frontend origin is still sent as `origin`/`referer`, since the gateway
appears to key some behavior off it.
"""
from dataclasses import dataclass
from typing import Dict, FrozenSet


@dataclass(frozen=True)
class EnvironmentProfile:
    name: str
    base_url: str
    frontend_origin: str
    allow_mutations: bool


# Hosts mutations are allowed to target, independent of ENV/profile name.
# BASE_URL can override the profile's host (see settings.py) - this is the
# second, host-based check that closes that hole. Add a host here only when
# it is genuinely safe to write test data to.
MUTATION_SAFE_HOSTS: FrozenSet[str] = frozenset({"pre-apis.ambak.com"})


ENVIRONMENTS: Dict[str, EnvironmentProfile] = {
    "pre": EnvironmentProfile(
        name="pre",
        base_url="https://pre-apis.ambak.com",
        frontend_origin="https://pre-saathi.ambak.com",
        allow_mutations=True,
    ),
    "prod": EnvironmentProfile(
        name="prod",
        base_url="https://apis.ambak.com",
        frontend_origin="https://saathi.ambak.com",
        allow_mutations=False,
    ),
}


def get_environment(name: str) -> EnvironmentProfile:
    try:
        return ENVIRONMENTS[name]
    except KeyError:
        known = ", ".join(sorted(ENVIRONMENTS))
        raise ValueError(f"Unknown environment {name!r}. Known environments: {known}") from None
