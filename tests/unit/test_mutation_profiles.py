"""The mutation-profile registry is the core safety mechanism for the
gated mutation sweep: default-deny (unregistered mutations stay skipped),
per-mutation synthetic-data overrides, and an explicit, reviewable
admission when no cleanup is possible - see the plan at
~/.claude/plans/i-want-to-be-steady-whistle.md.
"""
import pytest

from src.spec.operations import OPERATIONS
from src.testdata.mutation_profiles import PROFILES, get_profile

ALL_MUTATION_KEYS = [f"{op.service}.{op.name}" for op in OPERATIONS if op.kind == "mutation"]


def test_unregistered_mutation_returns_none():
    assert get_profile("no-such-service.no-such-mutation") is None


def test_every_captured_mutation_has_a_profile():
    """Default-deny: a newly-imported mutation must be explicitly
    classified before it can ever run - it should never silently start
    running just because it showed up in a Postman re-import."""
    missing = [key for key in ALL_MUTATION_KEYS if get_profile(key) is None]
    assert missing == [], f"unclassified mutations (will stay skipped): {missing}"


def test_every_profile_key_corresponds_to_a_real_captured_mutation():
    """Catches typos/stale entries the other direction."""
    stale = [key for key in PROFILES if key not in ALL_MUTATION_KEYS]
    assert stale == [], f"profile entries for mutations that no longer exist: {stale}"


@pytest.mark.parametrize("key", ALL_MUTATION_KEYS)
def test_profile_tier_is_valid(key):
    profile = get_profile(key)
    assert profile.tier in ("isolated", "external")


@pytest.mark.parametrize("key", ALL_MUTATION_KEYS)
def test_profile_without_cleanup_documents_why(key):
    """A missing cleanup callable must always come with a reason - an
    explicit, reviewable admission beats a silent leak."""
    profile = get_profile(key)
    if profile.cleanup is None:
        assert profile.cleanup_reason, f"{key} has no cleanup and no cleanup_reason"


@pytest.mark.parametrize(
    "key",
    [
        "bank-integration.indiashelter_createLead",
        "bank-integration.indiashelter_saveData",
        "finex.get_stored_transunion_cibil_report",
        "finex.save_tu_link_status",
    ],
)
def test_external_party_mutations_are_tier_external(key):
    assert get_profile(key).tier == "external"


def test_overrides_never_contain_captured_pii():
    """Applying every profile's overrides to its operation's real
    variables must fully replace the captured PII - never leave the
    Postman-captured name/mobile/PAN in the outgoing payload."""
    import json

    captured_needles = ["9869469832", "JAY", "TUSHAR", "DQPPG6092G"]

    by_key = {f"{op.service}.{op.name}": op for op in OPERATIONS if op.kind == "mutation"}
    for key, op in by_key.items():
        profile = get_profile(key)
        override = profile.overrides(op)
        merged = dict(op.variables)
        merged.update(override)
        blob = json.dumps(merged)
        for needle in captured_needles:
            assert needle not in blob, f"{key} still leaks captured value {needle!r}"
