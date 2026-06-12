"""Shared pytest fixtures and configuration."""

import os

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def isolate_autoresearch_db(monkeypatch):
    """Keep unit tests offline by removing any configured Turso feed target.

    ``run_research`` loads ``.env`` (which may point at a real ``libsql://`` URL),
    so without this guard an orchestrator run inside a test would try to open a
    remote connection and hang. Tests that need a database set it explicitly.
    """
    for name in (
        "DB_DISCOVERY_FORGE_URL",
        "DB_DISCOVERY_FORGE_AUTH_TOKEN",
    ):
        # Use an empty value instead of deleting it because ``run_research``
        # calls ``load_dotenv()`` and would otherwise repopulate real local
        # credentials from ``.env``.
        monkeypatch.setenv(name, "")


@pytest.fixture
def wandb_project_env(monkeypatch):
    """Set required W&B project env vars for observability tests."""
    monkeypatch.setenv("WANDB_ENTITY", "test-entity")
    monkeypatch.setenv("WANDB_PROJECT", "test-project")


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
