"""
Paper Reader Agent — Retrieves 15+ papers, reads them one-at-a-time with RAG memory,
stores everything in SQLite, and builds progressive cumulative insights.
"""

import json
import re
from backend.tools.arxiv_client import search_papers as arxiv_search
from backend.tools.semantic_scholar import search_papers as scholar_search
from backend.tools.llm_client import call_llm_json, call_llm
from backend.tools import vector_store, memory_store
from backend.models import Paper, PaperSummary

# [prompts remain unchanged]
SUMMARY_PROMPT = """You are a Research Paper Analyst Agent with a running memory of papers you've already read.
Your job is to deeply analyze ONE paper at a time, connecting it to your accumulated knowledge.

You MUST respond with valid JSON in this exact format:
{
  "problem_statement": "The core problem the paper addresses",
  "proposed_method": "The method or approach proposed (be specific about architecture/algorithm)",
  "dataset_used": "All datasets used with sizes and characteristics",
  "evaluation_results": "Key results: specific metrics (accuracy, F1, etc.) and comparisons",
  "limitations": "Limitations noted or apparent gaps",
  "key_contributions": "Main novel contributions (be specific)",
  "connections_to_prior": "How this paper relates to previously read papers (common methods, contradictions, extensions)",
  "cumulative_insight": "Updated running synthesis: What do we now know from ALL papers read so far?"
}

Be thorough and extract ALL factual information. Pay special attention to methodology details,
hyperparameters, ablation studies, and comparison baselines."""

SYNTHESIS_PROMPT = """You are a Research Synthesis Agent. Based on all the papers read and their summaries,
create a comprehensive cross-paper analysis.

Respond with valid JSON:
{
  "common_methods": "Methods and architectures that appear across multiple papers",
  "conflicting_findings": "Any contradictory results or claims between papers",
  "dataset_landscape": "Overview of all datasets used, gaps in dataset coverage",
  "methodology_gaps": "Methodological approaches NOT explored in the literature",
  "key_metrics": "Best reported metrics across papers for common benchmarks",
  "research_frontier": "Where the current state-of-the-art is and what's next",
  "synthesis": "3-5 paragraph comprehensive synthesis of the entire literature"
}"""


async def retrieve_papers(queries: list[str], max_papers: int = 15) -> list[Paper]:
    """Retrieve papers by fusing arXiv (preprints) & Semantic Scholar (Peer-Reviewed)."""
    all_papers: list[Paper] = []
    seen_titles = set()

    per_query = max(3, max_papers // len(queries))
    half_query = max(1, per_query // 2)

    for query in queries:
        # Fetch from ArXiv
        try:
            arxiv_results = await arxiv_search(query, max_results=half_query)
            for paper in arxiv_results:
                title_lower = paper.title.lower()
                if title_lower not in seen_titles:
                    seen_titles.add(title_lower)
                    all_papers.append(paper)
        except Exception as e:
            print(f"ArXiv search failed for '{query}': {e}")
            
        # Fetch from Semantic Scholar
        try:
            scholar_results = await scholar_search(query, max_results=half_query)
            for paper in scholar_results:
                title_lower = paper.title.lower()
                if title_lower not in seen_titles:
                    seen_titles.add(title_lower)
                    all_papers.append(paper)
        except Exception as e:
            print(f"Scholar search failed for '{query}': {e}")

    return all_papers[:max_papers]


async def read_single_paper(paper: Paper, prior_context: str, paper_index: int,
                            total: int, session_id: str = "") -> PaperSummary:
    """Read one paper with full context of previously-read papers."""

    # Search vector store for related content
    rag_results = []
    try:
        rag_results = await vector_store.search(f"{paper.title} {paper.abstract[:200]}", k=3)
    except Exception:
        pass

    rag_context = ""
    if rag_results:
        rag_context = "\n\nRelated findings from vector database:\n"
        for r in rag_results:
            rag_context += f"- {r.get('title', '')}: {r.get('text', '')[:300]}\n"

    user_prompt = f"""You are reading paper {paper_index}/{total}.

CUMULATIVE KNOWLEDGE SO FAR:
{prior_context if prior_context else "This is the first paper being read."}
{rag_context}

NOW READING THIS PAPER:
Title: {paper.title}
Authors: {', '.join(paper.authors)}
Published: {paper.published}
Abstract: {paper.abstract}

Analyze this paper thoroughly. Connect it to your prior knowledge from papers already read.
Update your cumulative insight to reflect what we now know from ALL papers."""

    result = None
    for attempt in range(2):
        try:
            if attempt == 0:
                result = await call_llm_json(
                    system_prompt=SUMMARY_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.3,
                    max_tokens=2000,
                )
            else:
                raw = await call_llm(
                    system_prompt=SUMMARY_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.3,
                    max_tokens=2000,
                    json_mode=False,
                )
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                else:
                    result = {"problem_statement": raw[:500], "proposed_method": "See above",
                              "dataset_used": "N/A", "evaluation_results": "N/A",
                              "limitations": "N/A", "key_contributions": "N/A",
                              "connections_to_prior": "", "cumulative_insight": ""}
            break
        except Exception as e:
            print(f"[Paper Reader] Attempt {attempt + 1} failed for '{paper.title[:50]}': {e}")
            if attempt == 1:
                result = {"problem_statement": f"Parse error: {e}", "proposed_method": "N/A",
                          "dataset_used": "N/A", "evaluation_results": "N/A",
                          "limitations": "N/A", "key_contributions": "N/A",
                          "connections_to_prior": "", "cumulative_insight": ""}

    cumulative = result.get("cumulative_insight", "")

    # Store in SQLite
    if session_id:
        memory_store.update_paper_summary(session_id, paper.arxiv_id,
                                          json.dumps(result), cumulative)

    summary = PaperSummary(
        paper_title=paper.title,
        problem_statement=result.get("problem_statement", "Not specified"),
        proposed_method=result.get("proposed_method", "Not specified"),
        dataset_used=result.get("dataset_used", "Not specified"),
        evaluation_results=result.get("evaluation_results", "Not specified"),
        limitations=result.get("limitations", "Not specified"),
        key_contributions=result.get("key_contributions", "Not specified"),
    )

    return summary, cumulative


async def create_synthesis(summaries: list[PaperSummary], cumulative_context: str,
                           session_id: str = "") -> dict:
    """Create a cross-paper synthesis after reading all papers."""

    papers_text = ""
    for i, s in enumerate(summaries, 1):
        papers_text += f"\nPaper {i}: {s.paper_title}\n"
        papers_text += f"  Method: {s.proposed_method}\n"
        papers_text += f"  Dataset: {s.dataset_used}\n"
        papers_text += f"  Results: {s.evaluation_results}\n"
        papers_text += f"  Limitations: {s.limitations}\n"

    user_prompt = f"""Based on reading {len(summaries)} papers, create a comprehensive synthesis.

CUMULATIVE INSIGHTS:
{cumulative_context}

ALL PAPERS:
{papers_text}

Provide a thorough cross-paper analysis."""

    result = None
    for attempt in range(2):
        try:
            if attempt == 0:
                result = await call_llm_json(
                    system_prompt=SYNTHESIS_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.4,
                    max_tokens=3000,
                )
            else:
                raw = await call_llm(
                    system_prompt=SYNTHESIS_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.4,
                    max_tokens=3000,
                    json_mode=False,
                )
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                else:
                    result = {"synthesis": raw[:2000]}
            break
        except Exception as e:
            print(f"[Paper Reader] Synthesis attempt {attempt + 1} failed: {e}")
            if attempt == 1:
                result = {"synthesis": "Synthesis generation failed."}

    if session_id:
        memory_store.save_memory(session_id, "paper_reader", "synthesis",
                                 json.dumps(result))
        memory_store.save_context(session_id, "literature_synthesis",
                                  result.get("synthesis", ""))

    return result


async def run(queries: list[str], max_papers: int = 15,
              session_id: str = "", progress_callback=None) -> tuple:
    """
    Full pipeline: retrieve papers, read one-at-a-time with progressive memory,
    store in vector DB and SQLite, create synthesis.

    progress_callback(paper_index, total, paper_title) is called for each paper.
    """

    papers = await retrieve_papers(queries, max_papers)

    # Store all papers in SQLite immediately
    if session_id:
        for paper in papers:
            memory_store.save_paper(
                session_id, paper.arxiv_id, paper.title,
                ', '.join(paper.authors), paper.abstract,
                paper.published, paper.url, paper.pdf_url
            )

    summaries = []
    cumulative_context = ""
    texts_for_vs = []
    metadata_for_vs = []

    # Read papers ONE AT A TIME with progressive memory
    for i, paper in enumerate(papers, 1):
        if progress_callback:
            await progress_callback(i, len(papers), paper.title)

        try:
            summary, cumulative_context = await read_single_paper(
                paper, cumulative_context, i, len(papers), session_id
            )
            summaries.append(summary)

            # Add to vector store for deep RAG (chunking abstract + summary)
            detailed_text = (f"Paper: {paper.title}. Authors: {', '.join(paper.authors)}.\n"
                             f"Abstract: {paper.abstract}\n"
                             f"Problem: {summary.problem_statement}\n"
                             f"Method: {summary.proposed_method}\n"
                             f"Results: {summary.evaluation_results}\n"
                             f"Limitations: {summary.limitations}")
            
            texts_for_vs.append(detailed_text)
            metadata_for_vs.append({"source": "omni_reader_paper", "title": paper.title, "arxiv_id": paper.arxiv_id})

            # Update vector store after each paper for progressive RAG, using smaller chunks
            try:
                await vector_store.add_documents([detailed_text], [metadata_for_vs[-1]], chunk_size=200)
            except Exception as e:
                print(f"[Paper Reader] Failed adding to vector store: {e}")

        except Exception as e:
            summaries.append(PaperSummary(
                paper_title=paper.title,
                problem_statement=f"Error reading: {str(e)}",
                proposed_method="N/A", dataset_used="N/A",
                evaluation_results="N/A", limitations="N/A",
                key_contributions="N/A",
            ))

    # Create cross-paper synthesis
    synthesis = {}
    if summaries:
        try:
            synthesis = await create_synthesis(summaries, cumulative_context, session_id)
        except Exception:
            pass

    # Store final cumulative context in memory
    if session_id and cumulative_context:
        memory_store.save_memory(session_id, "paper_reader",
                                 "cumulative_insights", cumulative_context)

    return papers, summaries, synthesis
