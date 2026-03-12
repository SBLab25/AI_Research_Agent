"""
Internet Search Client — Uses DuckDuckGo to scrape the web for real-time information.
"""

import asyncio
from duckduckgo_search import DDGS

async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the internet for real-time information.
    Returns a list of dicts with 'title', 'href', and 'body' (snippet).
    """
    def _do_search():
        results = []
        try:
            with DDGS() as ddgs:
                # text() yields dictionaries
                for r in ddgs.text(query, max_results=max_results):
                    results.append(r)
        except Exception as e:
            print(f"[Search Client] Error searching '{query}': {e}")
        return results

    # Run blocking network call in a thread pool
    return await asyncio.to_thread(_do_search)

async def search_news(query: str, max_results: int = 5) -> list[dict]:
    """
    Search specifically for recent news articles.
    Returns a list of dicts with 'title', 'url', 'body' (snippet), 'source', and 'date'.
    """
    def _do_search():
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.news(query, max_results=max_results):
                    results.append(r)
        except Exception as e:
            print(f"[Search Client] Error searching news '{query}': {e}")
        return results

    return await asyncio.to_thread(_do_search)
