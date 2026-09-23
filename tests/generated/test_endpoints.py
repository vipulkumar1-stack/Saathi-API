"""Regression sweep over REST endpoints confirmed safe to replay.

Safety model: default-deny, not default-allow. All GET endpoints run
automatically (by convention, a GET should not mutate). Every POST
endpoint is EXCLUDED unless explicitly added to SAFE_READ_POST_NAMES below
with a one-line justification from reading its captured body.

Why this exists: an earlier version of this file used a keyword
blocklist ("save"/"create"/"update"/"validate"/"send_otp"/"upload" in the
name => excluded, everything else => run automatically). That missed
`send_e2e_whatsapp_communication` and `send_email_app` - both real,
external, side-effecting POSTs - and both actually fired during suite
verification on 2026-08-21 (a real WhatsApp message and, most likely, a
real email were sent). See AUTH_FINDINGS.md. Do not go back to a
blocklist here; add to the allowlist only after reading the body.
"""
import pytest

from src.spec.endpoints import ENDPOINTS
from src.validators.response_validator import validate

# name -> why it's safe to auto-replay (verified by reading its captured
# body in postman/collection_raw.json - pure lookups/calculators, no
# persistence, no external comms).
SAFE_READ_POST_NAMES = {
    "p_o_s_t_user_detail": "dealer/user-manager/user_detail - looks up a user by id, no write fields in body",
    "p_o_s_t_get_team_member_ids": "id lookup by parent_partner_id_hash",
    "p_o_s_t_details": "partner-api/details - a partner profile lookup",
    "p_o_s_t_get_team_member_list": "team listing by partner id/filters",
    "p_o_s_t_get_partner_fulfillment_type": "single-field lookup by partner_id",
    "p_o_s_t_get_bank_offers": "process-rule/get-bank-offers - a BRE calculator, no persistence",
    "p_o_s_t_get_bt_offers": "process-rule/get-bt-offers - a BRE calculator, no persistence",
    "p_o_s_t_project_data": "apf-controller/project-data - paginated project listing by city",
    "p_o_s_t_get_microsite_content": "microsite content lookup by partner_id",
    "p_o_s_t_get_role_mapped_user_details": "role->user lookup by role_ids list",
    "p_o_s_t_get_partner_yoddha": "sfa-proxy lookup, read-only proxy call",
    "p_o_s_t_state_city_pincode": "commonservice/state_city_pincode - reference data lookup",
}

# Deliberately NOT auto-run, even though they're POST-with-JSON-body and
# could plausibly look safe from the name alone. Confirmed or suspected
# to write data or trigger an external side effect (email/WhatsApp/etc.).
# Requires a human decision (and, for the comms ones, a controlled test
# recipient) before ever calling these from automation again.
EXCLUDED_WITH_REASON = {
    "p_o_s_t_send_otp": "OTP send - covered explicitly via the auth flow, not here",
    "p_o_s_t_validate_otp": "OTP validate - covered explicitly via the auth flow, not here",
    "p_o_s_t_docs_upload": "file upload - a write",
    "p_o_s_t_save_partner_designation": "a write (name says save)",
    "p_o_s_t_validate__p_a_n": "calls an external PAN-verification provider - real cost/side effect per call",
    "p_o_s_t_save_basic_details": "a write (name says save)",
    "p_o_s_t_send_email_app": "sends a REAL email (confirmed - fired during suite verification 2026-08-21)",
    "p_o_s_t_send_e2e_whatsapp_communication": "sends a REAL WhatsApp message (confirmed - fired 2026-08-21)",
    "p_o_s_t_validate": "central-service/pancard/validate - external PAN provider call",
    "g_e_t_10148": "hits partner/freshdesk-support - Freshdesk isn't configured on `pre` (known env gap)",
}


def _is_safe(ep):
    if ep.name in EXCLUDED_WITH_REASON:
        return False
    if ep.method == "GET":
        return True
    return ep.name in SAFE_READ_POST_NAMES


SAFE_ENDPOINTS = [ep for ep in ENDPOINTS if _is_safe(ep)]
IDS = [f"{ep.service}.{ep.name}" for ep in SAFE_ENDPOINTS]

_unclassified = [
    ep.name for ep in ENDPOINTS
    if not _is_safe(ep) and ep.name not in EXCLUDED_WITH_REASON
]
assert not _unclassified, (
    f"New REST endpoint(s) imported with no safety classification: {_unclassified}. "
    f"Read the captured body in postman/collection_raw.json and add each one to either "
    f"SAFE_READ_POST_NAMES or EXCLUDED_WITH_REASON in this file before running tests - "
    f"do not assume a new POST is safe."
)


@pytest.mark.parametrize("ep", SAFE_ENDPOINTS, ids=IDS)
def test_endpoint_does_not_error(api, ep):
    response = api.call_endpoint(ep.service, ep.name)
    validate(response).status_in(200, 201, 204)
