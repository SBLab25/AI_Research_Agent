"""
Planner Agent — Deep research planning with 5 distinct research plans.
Asks the user to choose, auto-selects after 300 seconds.
"""

from backend.tools.llm_client import call_llm_json
from backend.tools import memory_store, search_client

SYSTEM_PROMPT = """You are an expert Research Planner Agent. Your task is to deeply analyze a research topic
and generate EXACTLY 5 distinct, high-quality research plans. Each plan should explore a DIFFERENT angle,
methodology, or sub-problem of the given topic.

You MUST respond with valid JSON in this exact format:
{
  "topic_analysis": "Deep 3-5 sentence analysis of the research landscape for this topic",
  "plans": [
    {
      "title": "Short descriptive title for this plan",
      "description": "Detailed 3-4 sentence description of the research direction",
      "refined_topic": "A more precise, focused version of the research topic for this plan",
      "search_queries": ["query1", "query2", "query3", "query4", "query5", "query6"],
      "research_objectives": ["objective1", "objective2", "objective3", "objective4"],
      "methodology": "Specific ML/AI methodology to use (e.g., transformer-based, GAN, reinforcement learning)",
      "expected_outcomes": "Concrete expected results and contributions",
      "pros": "Advantages of this plan",
      "cons": "Potential challenges or limitations",
      "novelty_score": 8,
      "feasibility_score": 7,
      "impact_score": 9
    }
  ]
}

Guidelines:
- Generate EXACTLY 5 plans, each exploring a genuinely DIFFERENT angle
- search_queries must be specific enough for arXiv (6 queries per plan)
- Include diverse methodologies across plans (e.g., one with transformers, one with GANs, one with RL)
- Score novelty, feasibility, and impact from 1-10
- Plans should range from incremental improvements to ambitious novel approaches
- Be specific about datasets, models, and evaluation metrics in each plan"""


async def run(topic: str, session_id: str = "") -> dict:
    """Generate 5 detailed research plans for the given topic, augmented by live web search."""

    # 1. Fetch real-time context from the internet
    web_results = await search_client.search_web(f"{topic} state of the art research", max_results=10)
    web_context = ""
    if web_results:
        web_context = "\n\n--- REAL-TIME INTERNET SEARCH RESULTS ---\n"
        for i, res in enumerate(web_results, 1):
            web_context += f"Result {i}: {res.get('title')}\nSnippet: {res.get('body')}\n\n"
        web_context += "-----------------------------------------\n"
        
        # Save search results to persistent memory
        if session_id:
            try:
                memory_store.save_memory(session_id, "planner", "web_search", web_context)
            except Exception:
                pass

    # Check for existing context from previous cycles
    prior_context = ""
    if session_id:
        ctx = memory_store.get_memory(session_id, "planner", "feedback_context")
        if ctx:
            prior_context = f"\n\nPrior research insights from previous analysis cycle:\n{ctx}"

    user_prompt = f"""Perform a deep, thorough analysis of this research topic and generate 5 distinct research plans:

Topic: {topic}
{prior_context}
{web_context}

Think carefully about:
1. What are the major sub-problems within this topic?
2. What methodologies have been explored vs what's missing?
3. What datasets and evaluation benchmarks are relevant?
4. Where are the biggest opportunities for novel contributions?
5. Reference the real-time internet search results if applicable to ensure state-of-the-art methodology.

Generate 5 DISTINCT plans that cover different angles, from safe incremental work to ambitious novel approaches."""

    result = await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.7,
        max_tokens=6000,
    )

    plans = result.get("plans", [])
    topic_analysis = result.get("topic_analysis", "")

    # Store in database and Vector RAM
    if session_id:
        memory_store.save_plans(session_id, plans)
        memory_store.save_memory(session_id, "planner", "topic_analysis", topic_analysis)
        memory_store.save_context(session_id, "planner_analysis", topic_analysis)
        
        # Deep RAG Memory Injection
        try:
            from backend.tools import vector_store
            
            # Embed web context
            if web_context:
                await vector_store.add_documents(
                    [web_context], 
                    [{"source": "planner_web_search", "topic": topic}]
                )
            # Embed the generated plans
            for i, p in enumerate(plans):
                plan_text = f"Plan {i+1}: {p.get('title')}. Objective: {', '.join(p.get('research_objectives', []))}. Method: {p.get('methodology')}"
                await vector_store.add_documents(
                    [plan_text], 
                    [{"source": "planner_generated_plan", "topic": topic, "plan_index": i}]
                )
        except Exception as e:
            print(f"[Planner] Failed to embed to vector store: {e}")

    return {
        "topic_analysis": topic_analysis,
        "plans": plans,
    }
