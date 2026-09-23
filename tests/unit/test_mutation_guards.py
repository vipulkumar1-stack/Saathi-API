"""Guard tests for the mutation safety gate.

Pure-config, no network calls. Verifies the fix for the BASE_URL hole:
`allow_mutations` must be false whenever the *resolved host* isn't a known
mutation-safe host, even if ENV/the profile name would otherwise say yes.
See src/config/settings.py and src/config/environments.py.
"""
import pytest

from src.config.settings import get_settings, reset_settings_cache


@pytest.fixture(autouse=True)
def _clean_settings_cache():
    reset_settings_cache()
    yield
    reset_settings_cache()


def _set_base_env(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "test-token")


def test_pre_with_allow_mutations_is_allowed(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("ENV", "pre")
    monkeypatch.setenv("ALLOW_MUTATIONS", "1")

    assert get_settings().allow_mutations is True


def test_prod_profile_blocks_mutations_even_with_flag(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("ALLOW_MUTATIONS", "1")

    assert get_settings().allow_mutations is False


def test_base_url_override_to_prod_host_is_rejected(monkeypatch):
    """The hole: ENV=pre (allow_mutations=True profile) + BASE_URL pointed
    at the prod host + ALLOW_MUTATIONS=1 must NOT resolve to mutations
    being allowed. get_settings() must fail loudly rather than silently
    letting mutations target the wrong host."""
    _set_base_env(monkeypatch)
    monkeypatch.setenv("ENV", "pre")
    monkeypatch.setenv("BASE_URL", "https://apis.ambak.com")
    monkeypatch.setenv("ALLOW_MUTATIONS", "1")

    with pytest.raises(RuntimeError, match="mutation-safe host"):
        get_settings()


def test_base_url_override_without_allow_mutations_flag_is_fine(monkeypatch):
    """Pointing BASE_URL elsewhere for read-only runs must still work -
    the guard only fires when ALLOW_MUTATIONS=1 is actually requested."""
    _set_base_env(monkeypatch)
    monkeypatch.setenv("ENV", "pre")
    monkeypatch.setenv("BASE_URL", "https://apis.ambak.com")
    monkeypatch.delenv("ALLOW_MUTATIONS", raising=False)

    settings = get_settings()
    assert settings.allow_mutations is False


def test_allow_external_mutations_defaults_false(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("ENV", "pre")
    monkeypatch.setenv("ALLOW_MUTATIONS", "1")
    monkeypatch.delenv("ALLOW_EXTERNAL_MUTATIONS", raising=False)

    assert get_settings().allow_external_mutations is False


def test_allow_external_mutations_requires_both_flags(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("ENV", "pre")
    monkeypatch.setenv("ALLOW_MUTATIONS", "0")
    monkeypatch.setenv("ALLOW_EXTERNAL_MUTATIONS", "1")

    assert get_settings().allow_external_mutations is False


def test_allow_external_mutations_true_when_both_set(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("ENV", "pre")
    monkeypatch.setenv("ALLOW_MUTATIONS", "1")
    monkeypatch.setenv("ALLOW_EXTERNAL_MUTATIONS", "1")

    assert get_settings().allow_external_mutations is True
