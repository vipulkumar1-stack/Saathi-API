"""Synthetic data generators for mutation test payloads.

Every value here is deliberately obviously-fake and unique per call, so
mutation runs never replay the real-looking PII captured in
src/spec/operations.py (a real name/mobile pulled in via the Postman
import) and reruns don't collide on uniqueness constraints (e.g. a
duplicate role name).
"""
import random
import string
from uuid import uuid4

# NOTE: there is no confirmed "reserved, non-routable" prefix for Indian
# mobile numbers (unlike e.g. US 555-01xx test numbers). This prefix is a
# placeholder chosen to look obviously synthetic, not a verified-safe
# range - confirm the correct reserved range with the backend/telecom
# team before relying on it to guarantee no real subscriber is ever
# reached. See the plan's open questions.
_MOBILE_PREFIX = "99999"

# A fixed pincode/city pair used across mutation payloads - doesn't need
# to be unique per run, just obviously not a real applicant's address.
SYNTHETIC_CITY = "Autotestpur"
SYNTHETIC_PINCODE = "999999"
SYNTHETIC_LOAN_AMOUNT = "100000"


def fake_name() -> str:
    """An obviously-synthetic first name, unique per call."""
    return f"AUTOTEST_{uuid4().hex[:8]}"


def fake_last_name() -> str:
    return f"AUTOTEST_LEAD_{uuid4().hex[:6]}"


def fake_mobile() -> str:
    """A 10-digit, obviously-synthetic mobile number, unique per call."""
    suffix = "".join(random.choices(string.digits, k=5))
    return f"{_MOBILE_PREFIX}{suffix}"


def fake_email() -> str:
    return f"autotest.{uuid4().hex[:8]}@example.invalid"


def fake_pan() -> str:
    """A syntactically valid but non-existent PAN (5 letters, 4 digits, 1
    letter), unique per call. Only for mutations that don't hit a real
    credit bureau - see src/testdata/mutation_profiles.py tiers."""
    letters = "".join(random.choices(string.ascii_uppercase, k=5))
    digits = "".join(random.choices(string.digits, k=4))
    checksum = random.choice(string.ascii_uppercase)
    return f"{letters}{digits}{checksum}"


def fake_role_name() -> str:
    return f"autotest_role_{uuid4().hex[:8]}"


def fake_remark() -> str:
    return f"AUTOTEST remark {uuid4().hex[:8]} - safe to delete"
