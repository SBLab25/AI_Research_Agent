"""
Paper Writer Agent -- Generates a structured research report from all pipeline outputs.
Uses plain text mode (not JSON) to avoid truncation issues with long reports.
"""

import re
from backend.tools.llm_client import call_llm_text
from backend.models import (
    Paper, PaperSummary, ResearchGap, Hypothesis,
    ExperimentCode, EvaluationResult, ResearchReport,
)

SYSTEM_PROMPT = """You are a Research Paper Writer Agent. Generate a complete, well-structured 
research report using the provided data from the research pipeline.

Write the report using MARKDOWN with these EXACT section headers (use ## for each):

## Abstract
(200-300 words executive summary)

## Introduction
(Background, motivation, problem statement, 300-500 words)

## Literature Review
(Discuss key papers, findings, and gaps, 400-600 words)

## Methodology
(Proposed approach in detail, 400-600 words)

## Experiment Setup
(Configuration, dataset, hyperparameters, 200-400 words)

## Results
(Actual performance metrics and analysis, 300-500 words)

## Discussion
(Implications, comparison with prior work, 300-500 words)

## Conclusion
(Summary and future work, 200-300 words)

## References
(Formatted reference list)

IMPORTANT: Use academic language. Reference specific papers. Include actual metrics from experiments.
Do NOT use JSON format. Write natural flowing text."""


def _parse_sections(text: str) -> dict:
    """Parse a markdown report into sections by ## headers."""
    sections = {}
    current_section = None
    current_content = []

    for line in text.split("\n"):
        header_match = re.match(r'^##\s+(.+)$', line.strip())
        if header_match:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = header_match.group(1).strip().lower().replace(" ", "_")
            current_content = []
        else:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


async def run(
    topic: str,
    papers: list[Paper],
    summaries: list[PaperSummary],
    gaps: list[ResearchGap],
    hypothesis: Hypothesis,
    experiment: ExperimentCode,
    evaluation: EvaluationResult,
    execution_outputs: str = "",
) -> ResearchReport:
    """Generate a complete research report."""

    # Build context
    papers_info = ""
    for i, (p, s) in enumerate(zip(papers, summaries), 1):
        papers_info += f"[{i}] {p.title} ({p.published}) - Method: {s.proposed_method}, Results: {s.evaluation_results}\n"

    gaps_info = "\n".join([f"- {g.description}" for g in gaps])

    refs_list = []
    for i, p in enumerate(papers, 1):
        refs_list.append(f"[{i}] {', '.join(p.authors[:3])}. \"{p.title}\". arXiv:{p.arxiv_id}, {p.published}.")
    references_text = "\n".join(refs_list)

    exec_info = ""
    if execution_outputs:
        exec_info = f"\nACTUAL EXPERIMENT OUTPUTS:\n{execution_outputs[:3000]}\n"

    user_prompt = f"""Write a complete research report:

TOPIC: {topic}

PAPERS REVIEWED:
{papers_info}

RESEARCH GAPS:
{gaps_info}

HYPOTHESIS: {hypothesis.title}
- Description: {hypothesis.description}
- Approach: {hypothesis.proposed_approach}

EXPERIMENT: {experiment.explanation}
{exec_info}
EVALUATION:
- Accuracy: {evaluation.estimated_accuracy}
- F1: {evaluation.estimated_f1}
- Strengths: {evaluation.strengths}
- Limitations: {evaluation.limitations}
- Assessment: {evaluation.overall_assessment}
- Baselines: {evaluation.comparison_with_baselines}

Use these references:
{references_text}

Write the full report now with all sections."""

    text = await call_llm_text(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.5,
        max_tokens=8192,
    )

    # Parse sections from markdown
    sections = _parse_sections(text)

    # Also try to extract title from the text
    title_match = re.match(r'^#\s+(.+)$', text.strip(), re.MULTILINE)
    title = title_match.group(1) if title_match else f"Research Report: {topic}"

    return ResearchReport(
        title=title,
        abstract=sections.get("abstract", "Report generation in progress..."),
        introduction=sections.get("introduction", ""),
        literature_review=sections.get("literature_review", ""),
        methodology=sections.get("methodology", ""),
        experiment_setup=sections.get("experiment_setup", ""),
        results=sections.get("results", ""),
        discussion=sections.get("discussion", ""),
        conclusion=sections.get("conclusion", ""),
        references=sections.get("references", references_text),
    )
