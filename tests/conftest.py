import pytest

import yoinkc.baseline as baseline_mod


@pytest.fixture(autouse=True)
def _reset_nsenter_cache():
    """Reset the global nsenter probe cache between every test."""
    baseline_mod._nsenter_available = None
    yield
    baseline_mod._nsenter_available = None
