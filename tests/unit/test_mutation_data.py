"""Synthetic data for mutation tests must never leak the hardcoded PII
captured in src/spec/operations.py (real-looking names/mobiles from the
Postman import), and must be unique per call so reruns don't collide."""
from src.testdata.mutation_data import fake_mobile, fake_name, fake_pan

CAPTURED_MOBILE = "9869469832"
CAPTURED_FIRST_NAMES = {"JAY", "TUSHAR"}
CAPTURED_PAN = "DQPPG6092G"


def test_fake_name_is_marked_synthetic_and_unique():
    a, b = fake_name(), fake_name()
    assert a != b
    assert a.startswith("AUTOTEST_")
    assert a.split("_", 1)[1].upper() not in CAPTURED_FIRST_NAMES


def test_fake_mobile_never_matches_captured_number():
    for _ in range(20):
        assert fake_mobile() != CAPTURED_MOBILE


def test_fake_mobile_is_ten_digits():
    assert len(fake_mobile()) == 10
    assert fake_mobile().isdigit()


def test_fake_pan_never_matches_captured_pan_and_is_well_formed():
    import re

    pan = fake_pan()
    assert pan != CAPTURED_PAN
    assert re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan)
