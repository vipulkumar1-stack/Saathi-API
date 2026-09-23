"""Fixtures specific to the mutation sweep.

Belt-and-suspenders host check: src/config/settings.py already refuses to
construct Settings at all if ALLOW_MUTATIONS=1 targets a host outside
MUTATION_SAFE_HOSTS. This re-asserts the same thing right before the
mutation tests actually run, so a future change to how `settings` gets
built can't silently drop the guard.

mutation_ledger records every mutation actually executed this session -
its profile's cleanup outcome included - and persists the list at
session end. Nearly every profile in src/testdata/mutation_profiles.py
has no cleanup available (the captured spec has no delete/revert
mutations), so this file is how a leaked record on `pre` stays
traceable instead of just disappearing.
"""
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from src.config.environments import MUTATION_SAFE_HOSTS

UNCLEANED_LOG_PATH = Path("mutations-uncleaned.json")


@pytest.fixture(scope="session", autouse=True)
def _assert_mutation_safe_host(settings):
    hostname = urlparse(settings.base_url).hostname
    assert hostname in MUTATION_SAFE_HOSTS, (
        f"refusing to run the mutation sweep against {hostname!r} - not in "
        f"MUTATION_SAFE_HOSTS ({sorted(MUTATION_SAFE_HOSTS)})"
    )


@pytest.fixture(scope="session")
def mutation_ledger():
    entries = []
    yield entries
    if not entries:
        return
    existing = []
    if UNCLEANED_LOG_PATH.exists():
        try:
            existing = json.loads(UNCLEANED_LOG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []
    UNCLEANED_LOG_PATH.write_text(json.dumps(existing + entries, indent=2))
