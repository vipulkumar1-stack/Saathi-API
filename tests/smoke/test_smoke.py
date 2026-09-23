"""CI-safe subset: auth + one read per GraphQL service. Fast, and safe to
run with real credentials in a scheduled/CI context (still no writes).
"""
import pytest

from src.auth.token_provider import assert_token_sane
from src.core.graphql import call_operation
from src.spec.operations import OPERATIONS
from src.validators.response_validator import validate

_ONE_QUERY_PER_SERVICE = {}
for op in OPERATIONS:
    if op.kind == "query" and op.service not in _ONE_QUERY_PER_SERVICE:
        _ONE_QUERY_PER_SERVICE[op.service] = op

REPRESENTATIVE_QUERIES = list(_ONE_QUERY_PER_SERVICE.values())
IDS = [op.service for op in REPRESENTATIVE_QUERIES]


@pytest.mark.smoke
def test_login_produces_a_sane_token(token_provider):
    assert_token_sane(token_provider.get_token())


@pytest.mark.smoke
@pytest.mark.parametrize("op", REPRESENTATIVE_QUERIES, ids=IDS)
def test_one_read_per_service_succeeds(api, op):
    response = call_operation(api.http, op)
    validate(response).status(200).no_graphql_errors()
