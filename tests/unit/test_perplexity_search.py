"""Search backend tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).parent.parent.parent


# ── PerplexitySearchTool unit tests (mocked HTTP) ─────────────────────────────


def test_default_search_backend_is_serper():
    from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND

    assert DEFAULT_SEARCH_BACKEND == "serper"


def test_serper_search_returns_normalized_results(monkeypatch):
    from discovery_forge.tools.search import serper_search

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    mock_response = {
        "organic": [{
            "title": "ToolX",
            "link": "https://github.com/x/toolx",
            "snippet": "ToolX runs ML experiments.",
            "date": "May 2026",
            "source": "GitHub",
        }],
        "peopleAlsoAsk": [{
            "question": "What is ToolX?",
            "snippet": "An experiment agent.",
            "link": "https://example.com/toolx",
        }],
    }
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        result = serper_search("ToolX autonomous experiment agent")

    assert "Search backend: serper" in result
    assert "ToolX" in result
    assert "https://github.com/x/toolx" in result
    assert "May 2026" in result


def test_serper_search_uses_serper_endpoint(monkeypatch):
    from discovery_forge.tools.search import serper_search

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = {"organic": []}
        mock_client.post.return_value.raise_for_status = MagicMock()

        serper_search("test query")

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        body = call_args.kwargs.get("json", {})
        headers = call_args.kwargs.get("headers", {})
        assert "google.serper.dev" in url
        assert body["q"] == "test query"
        assert body["num"] == 10
        assert headers["X-API-KEY"] == "test-key"


def test_serper_search_adds_tbs_when_recency_set(monkeypatch):
    from discovery_forge.tools.search import serper_search

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = {"organic": []}
        mock_client.post.return_value.raise_for_status = MagicMock()

        serper_search("test query", recency="month")

        body = mock_client.post.call_args.kwargs.get("json", {})
        assert body["tbs"] == "qdr:m"


def test_serper_search_omits_tbs_when_no_recency(monkeypatch):
    from discovery_forge.tools.search import serper_search

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = {"organic": []}
        mock_client.post.return_value.raise_for_status = MagicMock()

        serper_search("test query")

        body = mock_client.post.call_args.kwargs.get("json", {})
        assert "tbs" not in body


def test_serper_search_without_api_key_returns_error(monkeypatch):
    from discovery_forge.tools.search import serper_search

    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    result = serper_search("test query")
    assert "SERPER_API_KEY" in result


def test_search_web_query_routes_to_serper(monkeypatch):
    from discovery_forge.tools import search

    monkeypatch.setattr(search, "serper_search", lambda query, recency=None: f"serper:{query}:{recency}")
    assert search.search_web_query("abc", backend="serper") == "serper:abc:None"
    assert search.search_web_query("abc", backend="serper", recency="month") == "serper:abc:month"


def test_search_web_query_routes_to_perplexity(monkeypatch):
    from discovery_forge.tools import search

    monkeypatch.setattr(search, "perplexity_search", lambda query, recency=None: f"pplx:{query}:{recency}")
    assert search.search_web_query("abc", backend="perplexity") == "pplx:abc:None"
    assert search.search_web_query("abc", backend="perplexity", recency="year") == "pplx:abc:year"


def test_search_web_query_rejects_unknown_backend():
    from discovery_forge.tools.search import search_web_query

    result = search_web_query("abc", backend="unknown")
    assert "unsupported search backend" in result.lower()

def test_perplexity_search_returns_string():
    from discovery_forge.tools.search import perplexity_search

    mock_response = {
        "choices": [{"message": {"content": "Found: ToolX at https://github.com/x/toolx"}}],
        "citations": ["https://github.com/x/toolx", "https://arxiv.org/abs/2025.00001"],
    }
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        result = perplexity_search("autonomous experiment agent 2024")

    assert isinstance(result, str)
    assert len(result) > 0


def test_perplexity_search_includes_citations(monkeypatch):
    from discovery_forge.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_response = {
        "choices": [{"message": {"content": "Found: ToolX"}}],
        "citations": ["https://github.com/x/toolx", "https://arxiv.org/abs/2025.00001"],
    }
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        result = perplexity_search("autonomous experiment agent 2024")

    assert "github.com/x/toolx" in result or "arxiv.org" in result


def test_perplexity_search_sets_recency_filter_when_given(monkeypatch):
    from discovery_forge.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = {"choices": [{"message": {"content": "x"}}], "citations": []}
        mock_client.post.return_value.raise_for_status = MagicMock()

        perplexity_search("test query", recency="week")
        body = mock_client.post.call_args.kwargs.get("json", {})
        assert body["search_recency_filter"] == "week"


def test_perplexity_search_omits_recency_filter_when_none(monkeypatch):
    from discovery_forge.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = {"choices": [{"message": {"content": "x"}}], "citations": []}
        mock_client.post.return_value.raise_for_status = MagicMock()

        perplexity_search("test query")
        body = mock_client.post.call_args.kwargs.get("json", {})
        assert "search_recency_filter" not in body


def test_perplexity_search_uses_correct_api_endpoint(monkeypatch):
    from discovery_forge.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_response = {
        "choices": [{"message": {"content": "result"}}],
        "citations": [],
    }
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        perplexity_search("test query")

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "perplexity.ai" in url


def test_perplexity_search_uses_sonar_model(monkeypatch):
    from discovery_forge.tools.search import perplexity_search
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

    mock_response = {
        "choices": [{"message": {"content": "result"}}],
        "citations": [],
    }
    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        perplexity_search("test query")

        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json", {})
        assert "sonar" in body.get("model", "")


def test_perplexity_search_gracefully_handles_api_error():
    from discovery_forge.tools.search import perplexity_search
    import httpx

    with patch("discovery_forge.tools.search.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_client.post.side_effect = httpx.HTTPError("connection error")

        result = perplexity_search("test query")

    assert isinstance(result, str)
    assert "error" in result.lower() or "failed" in result.lower()


def test_perplexity_search_without_api_key_returns_error(monkeypatch):
    from discovery_forge.tools.search import perplexity_search
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    result = perplexity_search("test query")
    assert "PERPLEXITY_API_KEY" in result or "not configured" in result.lower() or "error" in result.lower()


# ── Discovery agent uses configured search backend ──────────────────────────

def test_researcher_agent_has_search_tool():
    from discovery_forge.agents.researcher import build_researcher_agent
    agent = build_researcher_agent(output_dir=Path("/tmp"))
    tool_names = [t.name if hasattr(t, "name") else str(t) for t in agent.tools]
    assert any("search" in name.lower() for name in tool_names)


def test_search_web_query_openai_backend_is_handled_at_agent_level():
    from discovery_forge.tools.search import search_web_query
    result = search_web_query("anything", backend="openai")
    assert "WebSearchTool" in result


def test_env_example_has_search_backend_keys():
    env_example = (ROOT / ".env.example").read_text()
    assert "SERPER_API_KEY" in env_example
    assert "PERPLEXITY_API_KEY" in env_example
