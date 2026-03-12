"""
Semantic Scholar API client for retrieving research papers from IEEE, Springer, ACM, Nature, etc.
Provides a much broader scope than arXiv for peer-reviewed literature.
"""

import httpx
from backend.models import Paper

async def search_papers(query: str, max_results: int = 8) -> list[Paper]:
    """Search Semantic Scholar for papers matching the query."""
    papers = []
    
    # Semantic Scholar Graph API endpoint
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    # Requesting specific fields: title, authors, abstract, year, url, openAccessPdf
    params = {
        "query": query,
        "limit": max_results,
        "fields": "paperId,title,authors,abstract,year,url,openAccessPdf"
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                for item in data.get("data", []):
                    # Handle potentially missing fields gracefully
                    abstract = item.get("abstract") or "No abstract available."
                    authors = [a.get("name", "") for a in item.get("authors", [])][:5]
                    pdf_url = ""
                    if item.get("openAccessPdf"):
                        pdf_url = item["openAccessPdf"].get("url", "")
                        
                    papers.append(Paper(
                        arxiv_id=f"S2-{item.get('paperId', 'unknown')[:8]}", # Using S2 prefix to distinguish from arXiv
                        title=item.get("title", "Untitled").strip().replace("\n", " "),
                        authors=authors if authors else ["Unknown"],
                        abstract=abstract.strip().replace("\n", " "),
                        published=str(item.get("year", (""))),
                        url=item.get("url", ""),
                        pdf_url=pdf_url
                    ))
            else:
                print(f"[Semantic Scholar] Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[Semantic Scholar] Exception during search: {e}")
        
    return papers
