"""Search backends for DiscoveryAgent and ProfilerAgent."""

import os
from typing import Literal

import httpx

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar-pro"
SERPER_API_URL = "https://google.serper.dev/search"

SearchBackend = Literal["serper", "perplexity"]
DEFAULT_SEARCH_BACKEND: SearchBackend = "serper"


def search_web_query(query: str, backend: SearchBackend = DEFAULT_SEARCH_BACKEND) -> str:
    """Search the web using the selected backend. No automatic fallback."""
    if backend == "serper":
        return serper_search(query)
    if backend == "perplexity":
        return perplexity_search(query)
    return f"Error: unsupported search backend '{backend}'. Use 'serper' or 'perplexity'."


def serper_search(query: str) -> str:
    """
    Search the web using Serper and return normalized organic results.

    Serper returns raw search results rather than a synthesized answer, so this
    formats titles, URLs, snippets, dates, and sources for the agents to inspect.
    """
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return "Error: SERPER_API_KEY not configured. Set it in .env to enable Serper search."

    payload = {
        "q": query,
        "num": 10,
    }
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


def perplexity_search(query: str) -> str:
    """
    Search the web using Perplexity AI (sonar-pro) and return a summary with source URLs.

    Returns a text block containing the answer and all citation URLs.
    On error, returns a descriptive error string.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return "Error: PERPLEXITY_API_KEY not configured. Set it in .env to enable Perplexity search."

    payload = {
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
        "search_recency_filter": "year",
    }

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
