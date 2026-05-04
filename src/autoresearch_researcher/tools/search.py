"""Perplexity-powered web search tool for DiscoveryAgent."""

import os

import httpx

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar-pro"


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
