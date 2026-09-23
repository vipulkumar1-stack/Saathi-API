"""Regression sweep over every imported GraphQL mutation.

Gated: skipped entirely unless ALLOW_MUTATIONS=1 AND the active
environment profile allows it AND the resolved host is in
MUTATION_SAFE_HOSTS (see conftest.py's pytest_collection_modifyitems and
src/config/settings.py - the profile guard blocks it regardless of the
flag, as a second line of defense; the host check blocks a BASE_URL
override from silently pointing mutations at prod).

Each mutation only runs if it has a profile in
src/testdata/mutation_profiles.py (default-deny: an unclassified
mutation stays skipped even with ALLOW_MUTATIONS=1). A profile's
overrides replace the captured PII (real-looking name/mobile/PAN from
the Postman import) with synthetic data before the call goes out.
"external"-tier mutations - the ones that reach a real lender or credit
bureau and are categorically irreversible - need a second opt-in,
ALLOW_EXTERNAL_MUTATIONS=1, on top of ALLOW_MUTATIONS.

These still write real, uncleaned-up data on `pre` (see each profile's
cleanup_reason) - never enable this against prod.
"""
import pytest

from src.core.graphql import call_operation
from src.spec.operations import OPERATIONS
from src.testdata.mutation_profiles import get_profile
from src.validators.response_validator import validate

MUTATIONS = [op for op in OPERATIONS if op.kind == "mutation"]
IDS = [f"{op.service}.{op.name}" for op in MUTATIONS]


@pytest.mark.mutation
@pytest.mark.parametrize("op", MUTATIONS, ids=IDS)
def test_mutation_operation_succeeds(api, settings, mutation_ledger, op):
    key = f"{op.service}.{op.name}"
    profile = get_profile(key)
    if profile is None:
        pytest.skip(f"{key} has no entry in src/testdata/mutation_profiles.py - default-deny")
    if profile.tier == "external" and not settings.allow_external_mutations:
        pytest.skip(
            f"{key} is tier=external - set ALLOW_EXTERNAL_MUTATIONS=1 (in addition to "
            f"ALLOW_MUTATIONS=1) to run mutations that reach a real lender/bureau/provider"
        )

    override = profile.overrides(op)
    # retries=0: a mutation must never be silently replayed as a
    # duplicate write on a timeout/5xx (see src/core/http_client.py).
    response = call_operation(api.http, op, variables_override=override, retries=0)

    cleaned = profile.cleanup is not None
    if cleaned:
        profile.cleanup(op, override)

    mutation_ledger.append(
        {
            "operation": key,
            "tier": profile.tier,
            "status": response.status,
            "cleaned": cleaned,
            "cleanup_reason": None if cleaned else profile.cleanup_reason,
        }
    )

    validate(response).status(200).no_graphql_errors()
