"""Auth negative cases: verifies the gateway actually rejects unauthorized
calls, rather than passing tests vacuously.

Confirmed during suite setup: the gateway ignores x-hmac-meta/signature
entirely and enforces auth purely via the bearer token, so these tests
cover the real gate. See AUTH_FINDINGS.md.

SECURITY: bank-integration is a confirmed exception, not a suite
artifact - it enforces NO authentication at all. An unauthenticated,
zero-header request to /bank-integration/api/v1 returns real customer
PII (name, address, income, loan amount) by lead_id, independently
reproduced with `curl`-equivalent plain requests outside this framework
on 2026-08-21. This looks like a genuine, currently-unpatched
unauthenticated data-exposure / IDOR issue on `pre` and should be
reported to the backend team - see AUTH_FINDINGS.md's SECURITY section.
It is NOT suppressed as a routine known_bug precisely so it stays
visible; it's isolated to its own xfail so the rest of the suite can
stay green while this gets fixed.
"""
import pytest

from src.core.graphql import call_operation
from src.spec.operations import OPERATIONS
from src.validators.response_validator import validate

# One representative read per GraphQL service is enough to prove the auth
# gate is enforced service-wide - no need to repeat this 79 times.
_ONE_QUERY_PER_SERVICE = {}
for op in OPERATIONS:
    if op.kind == "query" and op.service not in _ONE_QUERY_PER_SERVICE:
        _ONE_QUERY_PER_SERVICE[op.service] = op

REPRESENTATIVE_QUERIES = list(_ONE_QUERY_PER_SERVICE.values())
IDS = [op.service for op in REPRESENTATIVE_QUERIES]

# service -> reason, for services confirmed (not assumed) to skip auth
# entirely. Independently re-verified with a bare `requests.post`, no
# auth/HMAC headers of any kind, outside this framework.
UNAUTHENTICATED_SERVICES = {
    "bank-integration": (
        "SECURITY: confirmed unauthenticated - returns real lead PII "
        "with zero auth headers. Checked across 3 of its operations "
        "(indiashelter_getSavedData, indiashelter_timeline_steps, "
        "getBankIntegrationFieldsV2), all unauthenticated. Report to "
        "backend; do not silently accept this as expected behavior."
    ),
}


def _negative_params():
    for op in REPRESENTATIVE_QUERIES:
        marks = []
        if op.service in UNAUTHENTICATED_SERVICES:
            marks.append(pytest.mark.xfail(reason=UNAUTHENTICATED_SERVICES[op.service], strict=True))
        yield pytest.param(op, marks=marks)


@pytest.mark.negative
@pytest.mark.parametrize("op", list(_negative_params()), ids=IDS)
def test_unauthenticated_request_is_rejected(api_unauthed, op):
    response = call_operation(api_unauthed.http, op, requires_auth=False)
    validate(response).status(401)


@pytest.mark.negative
def test_bad_bearer_token_is_rejected(settings):
    from src.core.http_client import HttpClient
    from src.auth.token_provider import StaticTokenProvider

    http = HttpClient(settings, token_provider=StaticTokenProvider("not-a-real-token"))
    op = REPRESENTATIVE_QUERIES[0]
    response = call_operation(http, op)
    validate(response).status_in(401, 403)
