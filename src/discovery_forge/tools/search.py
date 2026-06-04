"""Search backends for the ResearcherAgent.

Three backends are supported:
- ``serper`` (default): raw Google results via Serper (needs ``SERPER_API_KEY``).
  Intentionally exposes rawer result quality for the annotation/feedback demo.
- ``perplexity``: synthesized answer + citations (needs ``PERPLEXITY_API_KEY``).
- ``openai``: OpenAI's hosted ``WebSearchTool``. Needs only ``OPENAI_API_KEY``;
  the search runs server-side inside the model turn, so it is wired at the agent
  tool level (``build_researcher_agent``) rather than through ``search_web_query``.
"""

import os
from typing import Literal

import httpx

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar-pro"
SERPER_API_URL = "https://google.serper.dev/search"

SearchBackend = Literal["serper", "perplexity", "openai"]
DEFAULT_SEARCH_BACKEND: SearchBackend = "serper"

# Recency window applied to search results. None = no date filter (all time).
RecencyWindow = Literal["day", "week", "month", "year"]

# Serper `tbs=qdr:<x>` time filter codes.
_SERPER_QDR = {"day": "d", "week": "w", "month": "m", "year": "y"}


def search_web_query(
    query: str,
    backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    recency: RecencyWindow | None = None,
) -> str:
    """Search the web using the selected backend. No automatic fallback.

    ``recency`` limits results to the last day/week/month/year when set. It is
    honored by ``serper`` and ``perplexity``; the ``openai`` backend uses the
    hosted WebSearchTool, which has no date filter (nudge via the prompt instead).
    """
    if backend == "serper":
        return serper_search(query, recency=recency)
    if backend == "perplexity":
        return perplexity_search(query, recency=recency)
    if backend == "openai":
        return (
            "Error: the 'openai' backend uses the hosted WebSearchTool and is wired "
            "directly into the agent's tools, not through search_web_query."
        )
    return f"Error: unsupported search backend '{backend}'. Use 'serper', 'perplexity', or 'openai'."


def serper_search(query: str, recency: RecencyWindow | None = None) -> str:
    """
    Search the web using Serper and return normalized organic results.

    Serper returns raw search results rather than a synthesized answer, so this
    formats titles, URLs, snippets, dates, and sources for the agents to inspect.
    When ``recency`` is set, a `tbs=qdr:<x>` time filter restricts results.
    """
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return "Error: SERPER_API_KEY not configured. Set it in .env to enable Serper search."

    payload: dict = {
        "q": query,
        "num": 10,
    }
    if recency is not None:
        payload["tbs"] = f"qdr:{_SERPER_QDR[recency]}"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(SERPER_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return _format_serper_results(query, data)
    except httpx.HTTPError as e:
        return f"Search failed: {e}"
    except Exception as e:
        return f"Search error: {e}"


def _format_serper_results(query: str, data: dict) -> str:
    lines = [
        "Search backend: serper",
        f"Query: {query}",
        "",
    ]

    answer_box = data.get("answerBox")
    if isinstance(answer_box, dict):
        lines.extend(["Answer box:", _format_serper_answer_box(answer_box), ""])

    organic = data.get("organic_results") or []
    if not organic:
        organic = data.get("organic") or []
    if organic:
        lines.append("Organic results:")
        for idx, result in enumerate(organic[:10], start=1):
            title = result.get("title") or "unknown"
            link = result.get("link") or "unknown"
            snippet = result.get("snippet") or result.get("description") or "unknown"
            date = result.get("date") or "unknown"
            source = result.get("source") or result.get("displayedLink") or "unknown"
            lines.extend([
                f"{idx}. {title}",
                f"   URL: {link}",
                f"   Snippet: {snippet}",
                f"   Date: {date}",
                f"   Source: {source}",
                "",
            ])
    else:
        lines.extend(["Organic results:", "No organic results returned.", ""])

    related = data.get("peopleAlsoAsk") or data.get("related_questions") or []
    if related:
        lines.append("Related questions:")
        for idx, result in enumerate(related[:5], start=1):
            question = result.get("question") or "unknown"
            snippet = result.get("snippet") or "unknown"
            link = result.get("link") or "unknown"
            lines.extend([
                f"{idx}. {question}",
                f"   Snippet: {snippet}",
                f"   URL: {link}",
                "",
            ])

    return "\n".join(lines).strip()


def _format_serper_answer_box(answer_box: dict) -> str:
    parts = []
    for key in ("title", "answer", "snippet", "link"):
        value = answer_box.get(key)
        if value:
            parts.append(f"- {key}: {value}")
    return "\n".join(parts) if parts else "- unknown"


def perplexity_search(query: str, recency: RecencyWindow | None = None) -> str:
    """
    Search the web using Perplexity AI (sonar-pro) and return a summary with source URLs.

    Returns a text block containing the answer and all citation URLs.
    When ``recency`` is set, it is passed as Perplexity's `search_recency_filter`.
    On error, returns a descriptive error string.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return "Error: PERPLEXITY_API_KEY not configured. Set it in .env to enable Perplexity search."

    payload: dict = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a research assistant finding experiment-automation tools. "
                    "Return factual information with specific tool names, GitHub URLs, and paper links."
                ),
            },
            {"role": "user", "content": query},
        ],
        "return_citations": True,
    }
    if recency is not None:
        payload["search_recency_filter"] = recency

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(PERPLEXITY_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        citations = data.get("citations", [])

        if citations:
            citations_block = "\n\nSources:\n" + "\n".join(f"- {url}" for url in citations)
            return content + citations_block
        return content

    except httpx.HTTPError as e:
        return f"Search failed: {e}"
    except Exception as e:
        return f"Search error: {e}"
