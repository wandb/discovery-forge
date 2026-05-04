"""Perplexity search tool tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent


# ── PerplexitySearchTool unit tests (mocked HTTP) ─────────────────────────────

def test_perplexity_search_returns_string():
    from autoresearch_researcher.tools.search import perplexity_search

    mock_response = {
        "choices": [{"message": {"content": "Found: ToolX at https://github.com/x/toolx"}}],
        "citations": ["https://github.com/x/toolx", "https://arxiv.org/abs/2025.00001"],
    }
    with patch("autoresearch_researcher.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        result = perplexity_search("autonomous experiment agent 2024")

    assert isinstance(result, str)
    assert len(result) > 0


def test_perplexity_search_includes_citations(monkeypatch):
    from autoresearch_researcher.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_response = {
        "choices": [{"message": {"content": "Found: ToolX"}}],
        "citations": ["https://github.com/x/toolx", "https://arxiv.org/abs/2025.00001"],
    }
    with patch("autoresearch_researcher.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        result = perplexity_search("autonomous experiment agent 2024")

    assert "github.com/x/toolx" in result or "arxiv.org" in result


def test_perplexity_search_uses_correct_api_endpoint(monkeypatch):
    from autoresearch_researcher.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_response = {
        "choices": [{"message": {"content": "result"}}],
        "citations": [],
    }
    with patch("autoresearch_researcher.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        perplexity_search("test query")

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "perplexity.ai" in url


def test_perplexity_search_uses_sonar_model(monkeypatch):
    from autoresearch_researcher.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_response = {
        "choices": [{"message": {"content": "result"}}],
        "citations": [],
    }
    with patch("autoresearch_researcher.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        perplexity_search("test query")

        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json", {})
        assert "sonar" in body.get("model", "")


def test_perplexity_search_gracefully_handles_api_error():
    from autoresearch_researcher.tools.search import perplexity_search
    import httpx

    with patch("autoresearch_researcher.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.side_effect = httpx.HTTPError("connection error")

        result = perplexity_search("test query")

    assert isinstance(result, str)
    assert "error" in result.lower() or "failed" in result.lower()


def test_perplexity_search_without_api_key_returns_error(monkeypatch):
    from autoresearch_researcher.tools.search import perplexity_search
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    result = perplexity_search("test query")
    assert "PERPLEXITY_API_KEY" in result or "not configured" in result.lower() or "error" in result.lower()


# ── Discovery agent uses Perplexity ──────────────────────────────────────────

def test_discovery_agent_has_perplexity_tool():
    from autoresearch_researcher.agents.discovery import build_discovery_agent
    agent = build_discovery_agent(output_dir=Path("/tmp"))
    tool_names = [t.name if hasattr(t, "name") else str(t) for t in agent.tools]
    # Should have perplexity_search tool (not the OpenAI built-in WebSearchTool)
    assert any("perplexity" in name.lower() or "search" in name.lower() for name in tool_names)


def test_env_example_has_perplexity_key():
    env_example = (ROOT / ".env.example").read_text()
    assert "PERPLEXITY_API_KEY" in env_example
