"""Shared pytest fixtures and configuration."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_weave():
    """Mock weave to avoid real W&B calls in unit tests."""
    with patch("weave.init") as mock_init, \
         patch("weave.attributes") as mock_attrs:
        mock_attrs.return_value.__enter__ = MagicMock(return_value=None)
        mock_attrs.return_value.__exit__ = MagicMock(return_value=False)
        yield {"init": mock_init, "attributes": mock_attrs}


@pytest.fixture
def mock_runner():
    """Mock OpenAI Agents Runner to avoid real API calls."""
    with patch("agents.Runner.run") as mock_run:
        yield mock_run
