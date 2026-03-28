#!/usr/bin/env python3
"""
Brave Search Tool

Provides web and news search using the Brave Search API (AI plan).
Requires BRAVE_SEARCH_API_KEY in environment or ~/.hermes/.env.

Features:
- Web search with extra_snippets (rich text chunks per result — AI plan)
- News search with publication age
- Optional freshness filter, country/language targeting
"""

import json
import logging
import os
import subprocess
from typing import Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


# ─── Key Loading ─────────────────────────────────────────────────────────────

def _get_api_key() -> Optional[str]:
    """Load BRAVE_SEARCH_API_KEY from env or ~/.hermes/.env."""
    key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("BRAVE_SEARCH_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return None


def check_brave_requirements() -> bool:
    return bool(_get_api_key())


# ─── Core HTTP Helper ─────────────────────────────────────────────────────────

def _brave_request(endpoint: str, params: dict) -> dict:
    """Make a Brave Search API request using curl (avoids gzip decode issues)."""
    key = _get_api_key()
    if not key:
        return {"error": "BRAVE_SEARCH_API_KEY not configured."}

    url = f"https://api.search.brave.com/res/v1/{endpoint}?{urlencode(params)}"
    result = subprocess.run(
        ["curl", "-sL", url,
         "-H", "Accept: application/json",
         "-H", f"X-Subscription-Token: {key}"],
        capture_output=True,
        timeout=20,
    )
    if result.returncode != 0:
        return {"error": f"curl failed: {result.stderr.decode()[:200]}"}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": result.stdout.decode()[:300]}


# ─── Tool Functions ───────────────────────────────────────────────────────────

def brave_web_search(
    query: str,
    count: int = 5,
    freshness: Optional[str] = None,
    country: Optional[str] = None,
    search_lang: Optional[str] = None,
    task_id: str = None,
) -> str:
    """Search the web using Brave Search API with rich content snippets."""
    if not query or not query.strip():
        return json.dumps({"error": "query is required"})

    params = {
        "q": query.strip(),
        "count": min(max(1, count), 20),
        "extra_snippets": "1",
    }
    if freshness:
        params["freshness"] = freshness
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang

    data = _brave_request("web/search", params)
    if "error" in data:
        return json.dumps(data)

    raw_results = data.get("web", {}).get("results", [])
    results = []
    for r in raw_results:
        item = {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "description": r.get("description", ""),
        }
        snippets = r.get("extra_snippets", [])
        if snippets:
            item["snippets"] = snippets
        results.append(item)

    return json.dumps({
        "query": query,
        "results": results,
        "total": len(results),
    }, ensure_ascii=False)


def brave_news_search(
    query: str,
    count: int = 5,
    freshness: Optional[str] = None,
    country: Optional[str] = None,
    search_lang: Optional[str] = None,
    task_id: str = None,
) -> str:
    """Search recent news using Brave Search API."""
    if not query or not query.strip():
        return json.dumps({"error": "query is required"})

    params = {
        "q": query.strip(),
        "count": min(max(1, count), 20),
        "extra_snippets": "1",
    }
    if freshness:
        params["freshness"] = freshness
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang

    data = _brave_request("news/search", params)
    if "error" in data:
        return json.dumps(data)

    raw_results = data.get("results", [])
    results = []
    for r in raw_results:
        item = {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "description": r.get("description", ""),
            "age": r.get("age", ""),
        }
        snippets = r.get("extra_snippets", [])
        if snippets:
            item["snippets"] = snippets
        results.append(item)

    return json.dumps({
        "query": query,
        "results": results,
        "total": len(results),
    }, ensure_ascii=False)


# ─── Schemas ──────────────────────────────────────────────────────────────────

_FRESHNESS_DESC = (
    "Optional time filter: 'pd' = past day, 'pw' = past week, "
    "'pm' = past month, 'py' = past year."
)

BRAVE_WEB_SEARCH_SCHEMA = {
    "name": "brave_web_search",
    "description": (
        "Search the web using Brave Search API. Returns titles, URLs, descriptions, "
        "and rich text snippets per result (AI plan extra_snippets). "
        "Use this for general web research, factual queries, and finding sources."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (1–20, default 5).",
                "minimum": 1,
                "maximum": 20,
            },
            "freshness": {
                "type": "string",
                "description": _FRESHNESS_DESC,
                "enum": ["pd", "pw", "pm", "py"],
            },
            "country": {
                "type": "string",
                "description": "Country code to bias results (e.g. 'DE', 'US').",
            },
            "search_lang": {
                "type": "string",
                "description": "Language code for results (e.g. 'de', 'en').",
            },
        },
        "required": ["query"],
    },
}

BRAVE_NEWS_SEARCH_SCHEMA = {
    "name": "brave_news_search",
    "description": (
        "Search recent news articles using Brave Search API. Returns titles, URLs, "
        "descriptions, publication age, and text snippets. "
        "Use this for current events, recent developments, or time-sensitive topics."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The news search query.",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (1–20, default 5).",
                "minimum": 1,
                "maximum": 20,
            },
            "freshness": {
                "type": "string",
                "description": _FRESHNESS_DESC,
                "enum": ["pd", "pw", "pm", "py"],
            },
            "country": {
                "type": "string",
                "description": "Country code to bias results (e.g. 'DE', 'US').",
            },
            "search_lang": {
                "type": "string",
                "description": "Language code for results (e.g. 'de', 'en').",
            },
        },
        "required": ["query"],
    },
}


# ─── Registry ─────────────────────────────────────────────────────────────────

from tools.registry import registry

registry.register(
    name="brave_web_search",
    toolset="brave",
    schema=BRAVE_WEB_SEARCH_SCHEMA,
    handler=lambda args, **kw: brave_web_search(
        query=args.get("query", ""),
        count=args.get("count", 5),
        freshness=args.get("freshness"),
        country=args.get("country"),
        search_lang=args.get("search_lang"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_brave_requirements,
    requires_env=["BRAVE_SEARCH_API_KEY"],
    emoji="🔍",
)

registry.register(
    name="brave_news_search",
    toolset="brave",
    schema=BRAVE_NEWS_SEARCH_SCHEMA,
    handler=lambda args, **kw: brave_news_search(
        query=args.get("query", ""),
        count=args.get("count", 5),
        freshness=args.get("freshness"),
        country=args.get("country"),
        search_lang=args.get("search_lang"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_brave_requirements,
    requires_env=["BRAVE_SEARCH_API_KEY"],
    emoji="📰",
)
