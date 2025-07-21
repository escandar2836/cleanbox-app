import os
import pytest


@pytest.fixture
def base_url():
    return os.environ.get("CLEANBOX_URL", "http://localhost:5000")
