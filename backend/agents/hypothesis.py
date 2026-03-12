"""
Hypothesis Generator Agent — Generates 5 detailed research hypotheses
using RAG from the vector store and paper insights. Asks user to choose.
"""

import json
import traceback
from backend.tools.llm_client import call_llm_json, call_llm
from backend.tools import vector_store, memory_store
from backend.models import PaperSummary, ResearchGap, Hypothesis

SYSTEM_PROMPT = """You are an expert Research Hypothesis Generator. Analyze paper summaries, research gaps,
and generate EXACTLY 5 high-quality, novel research hypotheses.

You MUST respond with valid JSON in this exact format:
{
  "gaps": [
    {
      "description": "Clear description of the research gap",
      "severity": "high",
      "source_papers": ["Paper Title 1"],
      "research_direction": "How to address this gap"
    }
  ],
  "hypotheses": [
    {
      "title": "Concise hypothesis title",
      "description": "Detailed description of the hypothesis",
      "proposed_approach": "Specific technical approach",
      "expected_outcome": "Concrete expected results",
      "justification": "Why this is worth investigating",
      "novelty_score": 8,
      "feasibility_score": 7,
      "impact_score": 9
    }
  ]
}

Guidelines:
- Generate EXACTLY 5 hypotheses
- Each hypothesis addresses a DIFFERENT gap or angle
- Range from safe/incremental to ambitious/novel
- Be specific about architecture, datasets, and expected metrics
- Score novelty, feasibility, and impact from 1-10"""


async def run(
    topic: str,
    summaries: list[PaperSummary],
    session_id: str = "",
    synthesis: dict = None,
) -> tuple[list[ResearchGap], list[Hypothesis], list[dict]]:
    """Generate 5 hypotheses using paper summaries and RAG-enhanced context."""

    # Truncate summaries to avoid token overflow — use at most 10
    truncated_summaries = summaries[:10]

    summaries_text = ""
    for i, s in enumerate(truncated_summaries, 1):
        summaries_text += f"""
Paper {i}: {s.paper_title}
- Problem: {s.problem_statement[:200]}
- Method: {s.proposed_method[:200]}
- Dataset: {s.dataset_used[:100]}
- Results: {s.evaluation_results[:150]}
- Limitations: {s.limitations[:150]}
"""

    # RAG: Deep Context Pull from Vector Store
    # Pulling up to 15 chunks (web searches, plans, and paper paragraphs)
    rag_context = ""
    try:
        rag_results = await vector_store.search(topic, k=15)
        if rag_results:
            rag_context = "\n--- DEEP CONTEXT MEMORY (Web Searches, Plans, and Full Paper Chunks) ---\n"
            for i, r in enumerate(rag_results, 1):
                source = r.get("source", "Memory")
                title = r.get("title", source)
                rag_context += f"[{i}] {title}: {r.get('text', '')}\n"
            rag_context += "--------------------------------------------------------------------\n"
    except Exception as e:
        print(f"[Hypothesis Agent] Failed to pull from Vector Store: {e}")

    # Prior cycle context (limited)
    prior_context = ""
    if session_id:
        ctx = memory_store.get_memory(session_id, "hypothesis", "feedback_context")
        if ctx:
            prior_context = f"\nPrior insights:\n{ctx[:300]}"

    synthesis_text = ""
    if synthesis:
        synthesis_text = f"""
Synthesis:
- Gaps: {str(synthesis.get('methodology_gaps', ''))[:200]}
- Frontier: {str(synthesis.get('research_frontier', ''))[:200]}
"""

    user_prompt = f"""Research Topic: {topic}

Paper summaries ({len(truncated_summaries)} of {len(summaries)} papers):
{summaries_text}
{synthesis_text}{rag_context}{prior_context}

Generate EXACTLY 5 novel, testable hypotheses based on this evidence.
Each should be implementable on a standard laptop with sklearn/PyTorch. Make heavy use of the "DEEP CONTEXT MEMORY" to ensure novelty and groundedness."""

    # Try with JSON mode first, then fallback to raw parsing
    result = None
    last_error = None

    for attempt in range(2):
        try:
            if attempt == 0:
                result = await call_llm_json(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.6,
                    max_tokens=4096,
                )
            else:
                # Fallback: no JSON mode, parse manually
                raw = await call_llm(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.6,
                    max_tokens=4096,
                    json_mode=False,
                )
                import re
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                else:
                    raise ValueError("No JSON found in LLM response")
            break
        except Exception as e:
            last_error = e
            print(f"[Hypothesis Agent] Attempt {attempt + 1} failed: {e}")
            traceback.print_exc()

    if result is None:
        raise ValueError(f"Hypothesis generation failed after retries: {last_error}")

    gaps = [
        ResearchGap(
            description=g.get("description", ""),
            severity=g.get("severity", "medium"),
            source_papers=g.get("source_papers", []),
            research_direction=g.get("research_direction", ""),
        )
        for g in result.get("gaps", [])
    ]

    hypotheses = [
        Hypothesis(
            title=h.get("title", ""),
            description=h.get("description", ""),
            proposed_approach=h.get("proposed_approach", ""),
            expected_outcome=h.get("expected_outcome", ""),
            justification=h.get("justification", ""),
        )
        for h in result.get("hypotheses", [])
    ]

    # Raw data for UI (includes scores)
    hypotheses_raw = result.get("hypotheses", [])

    # Store in SQLite
    if session_id:
        try:
            memory_store.save_hypotheses(session_id, hypotheses_raw)
            memory_store.save_memory(session_id, "hypothesis", "gaps",
                                     json.dumps([g.model_dump() for g in gaps]))
        except Exception:
            pass

    return gaps, hypotheses, hypotheses_raw
