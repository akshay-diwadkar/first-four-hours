"""Repository tests require the supervised runner; limits apply before bodies run."""
import os
import pytest

pytest_plugins = ["tools.validation.size_cap"]


def pytest_sessionstart(session):
    if os.environ.get("SKILLS_VALIDATION_ACTIVE") != "1":
        raise pytest.UsageError("Use python tools/validation/test_ownership.py run: repository verification must use the 120-second deadline.")
