"""Deeper, hand-crafted example for finex bank/role data: positive +
negative + schema validation, all against the real gateway. This is the
pattern to copy when a generated smoke test (tests/generated/) needs to
grow into a proper regression test for a specific operation.
"""
import pytest

from src.core.graphql import graphql_call
from src.validators.response_validator import validate


@pytest.mark.schema
def test_bank_list_matches_schema(finex):
    response = finex.bank_list(api_called_by="partner")
    validate(response).status(200).no_graphql_errors().field_is_array(
        "data.masterdata.bank_list", min_length=1
    )
    banks = response.data["data"]["masterdata"]["bank_list"]
    assert all(isinstance(b["id"], int) for b in banks), "every bank must have an integer id"


def test_bank_list_rejects_missing_required_variable(finex):
    # api_called_by is a required enum variable ($api_called_by: API_CALL_BY!)
    # - omitting it entirely must fail GraphQL variable validation, not
    # silently return data. (Note: GenericClient.call_operation merges
    # variable overrides into the captured defaults, so an empty dict
    # there would NOT omit an already-captured variable - go around it
    # here to send a genuinely empty variables map.)
    op = finex._generic.operation("finex", "BankList")
    response = graphql_call(finex._generic.http, op.path, op.query, variables={}, operation_name=op.name)
    validate(response).has_graphql_errors()


def test_get_role_access_features_rejects_invalid_role_id(finex):
    response = finex.get_role_access_features(role_id="not-a-number")
    validate(response).has_graphql_errors()
