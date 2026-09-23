"""Regression sweep over GraphQL queries confirmed safe to replay.

Safety model: default-deny for anything whose name suggests an action,
not "kind == query". `send_transunion_sms` is declared as a GraphQL
*query* (no `mutation` keyword) but is a real SMS-send action - it fired
a real SMS to a real number the first time this sweep ran automatically
(2026-08-21). The backend's query/mutation labeling is not trustworthy
for safety decisions; a name-pattern review is. See AUTH_FINDINGS.md.

Every query whose name matches ACTION_VERB_RE must be explicitly
reviewed and placed into SAFE_QUERY_NAMES (with justification, from
reading its resolver/query text) or EXCLUDED_QUERY_NAMES (with reason)
below - the assertion at import time enforces this for anything newly
imported.
"""
import re

import pytest

from src.core.graphql import call_operation
from src.spec.operations import OPERATIONS
from src.validators.response_validator import validate

QUERIES = [op for op in OPERATIONS if op.kind == "query"]

ACTION_VERB_RE = re.compile(
    r"send|notify|trigger|communicat|sms|email|whatsapp|create|update|save|upload|"
    r"submit|generat|issue|sync|link|calculate|apply|approve|reject|assign|invite|"
    r"register|verify|confirm",
    re.IGNORECASE,
)

# Reviewed and confirmed read-only despite matching ACTION_VERB_RE (their
# resolver just fetches/checks state - verified by reading the captured
# query text in src/spec/operations.py).
SAFE_QUERY_NAMES = {
    "get_tu_link_status": "checks an existing TransUnion link's status - no write",
    "indiashelter_getSavedData": "reads previously saved integration data for a lead",
    "GetEmailTemplates": "lists available email templates - does not send anything",
}

# Confirmed or suspected real side effects - never auto-run.
EXCLUDED_QUERY_NAMES = {
    "send_transunion_sms": (
        "sends a REAL SMS to a real mobile number (confirmed - fired during "
        "suite verification on 2026-08-21, despite being declared as a "
        "GraphQL query rather than a mutation)"
    ),
}

_unclassified = [
    op.name for op in QUERIES
    if ACTION_VERB_RE.search(op.name)
    and op.name not in SAFE_QUERY_NAMES
    and op.name not in EXCLUDED_QUERY_NAMES
]
assert not _unclassified, (
    f"New action-shaped query operation(s) imported with no safety review: "
    f"{_unclassified}. Read the captured query text in src/spec/operations.py "
    f"and add each one to either SAFE_QUERY_NAMES or EXCLUDED_QUERY_NAMES in "
    f"this file - do not assume a 'query'-typed operation is read-only."
)

SAFE_QUERIES = [op for op in QUERIES if op.name not in EXCLUDED_QUERY_NAMES]

# Real, reproducible backend issues found the first time this suite ran
# against `pre` (2026-08-21) - tracked as known_bug/xfail(strict=True) so
# the suite stays green without hiding them, and flips to a hard failure
# (XPASS) the moment a fix lands or they regress differently. See
# AUTH_FINDINGS.md for the original failure output.
#
# Resolved and retired from this dict (kept here for the record since the
# repo has no git history):
#   ("insurance", "GetMobileOffers") - INTERNAL_SERVER_ERROR: "Table
#   'ambak_insurance.ins_pb_city_alias' doesn't exist". Fixed on the
#   backend; confirmed 2026-09-02 returning populated offers with zero
#   GraphQL errors, which surfaced as the strict XPASS that retired it.
KNOWN_BUGS = {
    ("finex", "get_banker_records_by_id"): (
        "Captured request calls get_banker_records_by_id(city: \"Mumbai\"), "
        "but the current schema requires a bank_id: Float! argument instead "
        "- the capture is stale relative to the live schema (400 "
        "GRAPHQL_VALIDATION_FAILED)."
    ),
    ("finex", "get_feature_list"): (
        "Returns data alongside two GraphQL errors: "
        "{'message': 'Invalid time value', 'extensions': {'code': 'INTERNAL_SERVER_ERROR'}} "
        "- looks like a date-formatting bug in the resolver (likely a null/"
        "malformed created_date or updated_date on at least one row)."
    ),
}

IDS = [f"{op.service}.{op.name}" for op in SAFE_QUERIES]


def _params():
    for op in SAFE_QUERIES:
        key = (op.service, op.name)
        marks = []
        if key in KNOWN_BUGS:
            marks.append(pytest.mark.known_bug)
            marks.append(pytest.mark.xfail(reason=KNOWN_BUGS[key], strict=True))
        yield pytest.param(op, marks=marks)


@pytest.mark.parametrize("op", list(_params()), ids=IDS)
def test_query_operation_succeeds(api, op):
    response = call_operation(api.http, op)
    validate(response).status(200).no_graphql_errors()
