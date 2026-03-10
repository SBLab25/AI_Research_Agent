"""
Evaluation Agent -- Evaluates experiment using ACTUAL execution results.
When real outputs are available, uses them; otherwise provides analytical assessment.
"""

from backend.tools.llm_client import call_llm_json
from backend.models import (
    Hypothesis, ExperimentCode, PaperSummary, EvaluationResult
)

SYSTEM_PROMPT = """You are a Research Evaluation Agent. You analyze ML experiment results
and compare them against literature benchmarks.

You MUST respond with valid JSON in this exact format:
{
  "estimated_accuracy": "Actual or estimated accuracy with analysis",
  "estimated_f1": "Actual or estimated F1 score",
  "estimated_precision": "Actual or estimated precision",
  "estimated_recall": "Actual or estimated recall",
  "comparison_with_baselines": "Detailed comparison with methods from existing papers",
  "strengths": "Key strengths of the approach based on results",
  "limitations": "Limitations found during evaluation",
  "overall_assessment": "Overall assessment based on actual performance"
}

When actual execution results are provided, extract real metrics from the outputs.
When only estimated, clearly label them as estimates and explain reasoning."""


async def run(
    hypothesis: Hypothesis,
    experiment: ExperimentCode,
    summaries: list[PaperSummary],
    topic: str,
    execution_outputs: str = "",
) -> EvaluationResult:
    """Evaluate the experiment, using real execution results when available."""

    benchmarks_text = ""
    for s in summaries:
        benchmarks_text += f"- {s.paper_title}: {s.evaluation_results} (Method: {s.proposed_method})\n"

    exec_section = ""
    if execution_outputs:
        exec_section = f"""
ACTUAL EXECUTION OUTPUTS (from running the experiment code):
{execution_outputs}

IMPORTANT: Extract REAL metrics from the execution outputs above. Do NOT estimate -- use actual values.
"""
    else:
        exec_section = """
No execution outputs available. Provide analytical estimates based on the experiment design 
and literature benchmarks.
"""

    user_prompt = f"""Evaluate this ML experiment:

Topic: {topic}
Hypothesis: {hypothesis.title}
Approach: {hypothesis.proposed_approach}
Expected Outcome: {hypothesis.expected_outcome}

Experiment Design: {experiment.explanation}
{exec_section}
Existing Literature Benchmarks:
{benchmarks_text}

Provide a thorough evaluation with metrics, comparison with baselines, and overall assessment."""

    result = await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.4,
    )

    return EvaluationResult(
        estimated_accuracy=result.get("estimated_accuracy", "N/A"),
        estimated_f1=result.get("estimated_f1", "N/A"),
        estimated_precision=result.get("estimated_precision", "N/A"),
        estimated_recall=result.get("estimated_recall", "N/A"),
        comparison_with_baselines=result.get("comparison_with_baselines", "N/A"),
        strengths=result.get("strengths", "N/A"),
        limitations=result.get("limitations", "N/A"),
        overall_assessment=result.get("overall_assessment", "N/A"),
    )
