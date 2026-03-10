"""
arXiv API client for retrieving research papers.
No API key required.
"""

import arxiv
import asyncio
from typing import Optional
from backend.models import Paper


async def search_papers(query: str, max_results: int = 8) -> list[Paper]:
    """Search arXiv for papers matching the query."""

    def _search():
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
            sort_order=arxiv.SortOrder.Descending,
        )
        papers = []
        for result in client.results(search):
            papers.append(Paper(
                arxiv_id=result.entry_id.split("/")[-1],
                title=result.title.strip().replace("\n", " "),
                authors=[a.name for a in result.authors[:5]],
                abstract=result.summary.strip().replace("\n", " "),
                published=result.published.strftime("%Y-%m-%d") if result.published else "",
                url=result.entry_id,
                pdf_url=result.pdf_url or "",
            ))
        return papers

    return await asyncio.to_thread(_search)
