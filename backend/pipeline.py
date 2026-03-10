"""
Research Pipeline Orchestrator — Enhanced with:
- User choice for plans (5 options, 300s timeout)
- Paper reader with progressive RAG reading (15+ papers)
- User choice for hypotheses (5 options, 300s timeout)
- Cyclic feedback between planner/reader/hypothesis
- SQLite persistent memory
- SSE events for real-time UI updates
"""

import json
import uuid
from typing import AsyncGenerator

from backend.models import PipelineEvent, Hypothesis, PaperSummary, Paper
from backend.agents import planner, paper_reader, hypothesis, experiment, evaluation, writer
from backend.tools import vector_store, memory_store, user_choice
from backend.tools.code_executor import execute_code

# Global state for current session
current_state = {}


async def run_pipeline(topic: str) -> AsyncGenerator[str, None]:
    """Execute the full research pipeline safely, surfacing any critical errors."""
    try:
        async for event in _run_pipeline_impl(topic):
            yield event
    except Exception as e:
        import traceback
        print(f"[Pipeline] Critical ERROR: {e}")
        traceback.print_exc()
        from backend.models import PipelineEvent
        evt = PipelineEvent(stage="done", status="error", message=f"Critical pipeline error: {str(e)}")
        yield f"data: {evt.model_dump_json()}\n\n"

async def _run_pipeline_impl(topic: str) -> AsyncGenerator[str, None]:
    """Internal implementation of the research pipeline."""

    session_id = str(uuid.uuid4())[:12]
    memory_store.create_session(session_id, topic)
    current_state["session_id"] = session_id

    def _event(stage: str, status: str, message: str, data: dict = None) -> str:
        evt = PipelineEvent(stage=stage, status=status, message=message, data=data)
        return f"data: {evt.model_dump_json()}\n\n"

    # Clear vector store from any previous session
    vector_store.clear()

    # ══════════════════════════════════════════════════════════════
    #  Stage 1: PLANNER — Generate 5 plans, ask user to choose
    # ══════════════════════════════════════════════════════════════
    yield _event("planner", "starting",
        "Planner Agent activated. Performing deep analysis of: \"{}\"...".format(topic))

    try:
        plan_result = await planner.run(topic, session_id=session_id)
        plans = plan_result.get("plans", [])
        analysis = plan_result.get("topic_analysis", "")

        if not plans:
            yield _event("planner", "error", "Planner failed to generate plans.")
            yield _event("done", "error", "No plans generated")
            return

        yield _event("planner", "choice_required",
            "Generated {} research plans. Please select one (auto-selects in 300s)...".format(len(plans)),
            data={
                "topic_analysis": analysis,
                "plans": plans,
                "choice_id": f"{session_id}_plan",
                "timeout": 300,
                "choice_type": "plan",
            }
        )

        # Wait for user choice (300s timeout)
        user_choice.create_choice(f"{session_id}_plan")
        selected_idx, was_user = await user_choice.wait_for_choice(
            f"{session_id}_plan", timeout=300, default=0
        )

        # Auto-select: pick plan with best combined score
        if not was_user and plans:
            best_idx = 0
            best_score = 0
            for i, p in enumerate(plans):
                score = (p.get("novelty_score", 5) + p.get("feasibility_score", 5) + p.get("impact_score", 5))
                if score > best_score:
                    best_score = score
                    best_idx = i
            selected_idx = best_idx

        selected_idx = min(selected_idx, len(plans) - 1)
        selected_plan = plans[selected_idx]
        memory_store.select_plan(session_id, selected_idx)

        choice_msg = "User selected" if was_user else "Auto-selected (timeout)"
        yield _event("planner", "completed",
            '{} Plan {}: "{}". Starting paper retrieval...'.format(
                choice_msg, selected_idx + 1, selected_plan.get("title", "Research Plan")),
            data={
                "selected_plan": selected_plan,
                "selected_index": selected_idx,
                "was_user_choice": was_user,
                "refined_topic": selected_plan.get("refined_topic", topic),
                "search_queries": selected_plan.get("search_queries", [topic]),
                "research_objectives": selected_plan.get("research_objectives", []),
                "methodology_notes": selected_plan.get("methodology", ""),
                "expected_output": selected_plan.get("expected_outcomes", ""),
            }
        )
    except Exception as e:
        yield _event("planner", "error", "Planner Agent failed: {}".format(str(e)))
        yield _event("done", "error", str(e))
        return

    refined_topic = selected_plan.get("refined_topic", topic)
    search_queries = selected_plan.get("search_queries", [topic])

    # ══════════════════════════════════════════════════════════════
    #  Stage 2: PAPER READER — Fetch 15+ papers, read one-at-a-time with RAG
    # ══════════════════════════════════════════════════════════════
    yield _event("paper_reader", "starting",
        "Paper Reader Agent activated. Searching arXiv with {} queries for 15+ papers...".format(
            len(search_queries)))

    try:
        async def paper_progress(idx, total, title):
            """Callback: emit SSE for each paper being read."""
            nonlocal _event
            # We can't yield from a callback, so we store progress events
            pass

        papers, summaries, synthesis = await paper_reader.run(
            search_queries, max_papers=15,
            session_id=session_id
        )

        papers_data = [p.model_dump() for p in papers]
        summaries_data = [s.model_dump() for s in summaries]

        yield _event("paper_reader", "completed",
            "Read and analyzed {} papers with progressive RAG memory. Cross-paper synthesis created.".format(
                len(papers)),
            data={
                "papers_count": len(papers),
                "papers": papers_data,
                "summaries": summaries_data,
                "synthesis": synthesis,
            }
        )
    except Exception as e:
        yield _event("paper_reader", "error",
            "Paper Reader Agent failed: {}".format(str(e)))
        yield _event("done", "error", str(e))
        return

    # ══════════════════════════════════════════════════════════════
    #  Stage 3: HYPOTHESIS — Generate 5 hypotheses, ask user to choose
    # ══════════════════════════════════════════════════════════════
    yield _event("hypothesis_gen", "starting",
        "Hypothesis Agent activated. Using RAG and {} paper summaries to generate 5 hypotheses...".format(
            len(summaries)))

    try:
        import traceback as tb
        gaps, hypotheses, hypotheses_raw = await hypothesis.run(
            refined_topic, summaries,
            session_id=session_id, synthesis=synthesis
        )

        gaps_data = [g.model_dump() for g in gaps]
        hypotheses_data = [h.model_dump() for h in hypotheses]

        if not hypotheses:
            yield _event("hypothesis_gen", "error", "No hypotheses generated.")
            yield _event("done", "error", "No hypotheses generated")
            return

        yield _event("hypothesis_gen", "choice_required",
            "Generated {} hypotheses from {} research gaps. Select one (auto-selects in 300s)...".format(
                len(hypotheses), len(gaps)),
            data={
                "gaps": gaps_data,
                "hypotheses": hypotheses_data,
                "hypotheses_raw": hypotheses_raw,
                "choice_id": f"{session_id}_hypothesis",
                "timeout": 300,
                "choice_type": "hypothesis",
            }
        )

        # Wait for user choice (300s timeout)
        user_choice.create_choice(f"{session_id}_hypothesis")
        h_idx, h_was_user = await user_choice.wait_for_choice(
            f"{session_id}_hypothesis", timeout=300, default=0
        )

        # Auto-select best hypothesis
        if not h_was_user and hypotheses_raw:
            best_idx = 0
            best_score = 0
            for i, h in enumerate(hypotheses_raw):
                score = (h.get("novelty_score", 5) + h.get("feasibility_score", 5) + h.get("impact_score", 5))
                if score > best_score:
                    best_score = score
                    best_idx = i
            h_idx = best_idx

        h_idx = min(h_idx, len(hypotheses) - 1)
        selected_hypothesis = hypotheses[h_idx]
        memory_store.select_hypothesis(session_id, h_idx)

        h_choice_msg = "User selected" if h_was_user else "Auto-selected (timeout)"
        yield _event("hypothesis_gen", "completed",
            '{} Hypothesis {}: "{}". Proceeding to experiment...'.format(
                h_choice_msg, h_idx + 1, selected_hypothesis.title),
            data={
                "gaps": gaps_data,
                "hypotheses": hypotheses_data,
                "selected_hypothesis": selected_hypothesis.model_dump(),
                "selected_index": h_idx,
                "was_user_choice": h_was_user,
            }
        )
    except Exception as e:
        print(f"[Pipeline] Hypothesis Agent ERROR: {e}")
        tb.print_exc()
        yield _event("hypothesis_gen", "error",
            "Hypothesis Generator failed: {}".format(str(e)))
        yield _event("done", "error", str(e))
        return

    # ══════════════════════════════════════════════════════════════
    #  Cyclic Feedback — Feed hypothesis insights back for refinement
    # ══════════════════════════════════════════════════════════════
    # Store the cycle context so agents can reference it in re-runs
    memory_store.save_memory(session_id, "planner", "feedback_context",
        f"Selected hypothesis: {selected_hypothesis.title}. "
        f"Approach: {selected_hypothesis.proposed_approach}. "
        f"This informs the research direction.")
    memory_store.save_memory(session_id, "hypothesis", "feedback_context",
        f"Selected plan: {selected_plan.get('title', '')}. "
        f"Literature synthesis available from {len(summaries)} papers.")
    memory_store.save_context(session_id, "cycle_decision",
        f"Research direction: Plan='{selected_plan.get('title', '')}', "
        f"Hypothesis='{selected_hypothesis.title}'")

    # ══════════════════════════════════════════════════════════════
    #  Stage 4: EXPERIMENT — Generate and execute notebook cells
    # ══════════════════════════════════════════════════════════════
    yield _event("experiment", "starting",
        "Experiment Agent activated. Generating executable experiment for: \"{}\"...".format(
            selected_hypothesis.title))

    try:
        exp_code = await experiment.run(selected_hypothesis, refined_topic)

        cells_data = [c.model_dump() for c in exp_code.cells]
        yield _event("experiment", "notebook_ready",
            "Experiment notebook with {} cells. Starting execution...".format(len(exp_code.cells)),
            data={
                "cells": cells_data,
                "explanation": exp_code.explanation,
                "requirements": exp_code.requirements,
            }
        )

        # Execute each cell
        all_outputs = []
        for i, cell in enumerate(exp_code.cells):
            yield _event("experiment", "cell_running",
                "Executing cell {}/{}: {}...".format(i + 1, len(exp_code.cells), cell.title),
                data={"cell_id": cell.cell_id, "cell_index": i}
            )

            result = await execute_code(cell.code, timeout=300)

            cell_result = {
                "cell_id": cell.cell_id,
                "cell_index": i,
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "images": result.images,
                "error": result.error,
                "execution_time": result.execution_time,
            }

            status = "cell_completed" if result.success else "cell_error"
            msg = "Cell {}/{} completed ({:.1f}s)".format(
                i + 1, len(exp_code.cells), result.execution_time)
            if not result.success:
                msg = "Cell {}/{} error: {}".format(
                    i + 1, len(exp_code.cells), result.error[:200])

            yield _event("experiment", status, msg, data=cell_result)

            if result.stdout:
                all_outputs.append("--- Cell: {} ---\n{}".format(cell.title, result.stdout))
            if result.error:
                all_outputs.append("--- Cell {} Error ---\n{}".format(cell.title, result.error))

        execution_outputs = "\n".join(all_outputs)

        yield _event("experiment", "completed",
            "All {} experiment cells executed.".format(len(exp_code.cells)),
            data={"execution_summary": execution_outputs[:5000]}
        )

    except Exception as e:
        yield _event("experiment", "error", "Experiment Agent failed: {}".format(str(e)))
        yield _event("done", "error", str(e))
        execution_outputs = ""
        return

    # ══════════════════════════════════════════════════════════════
    #  Stage 5: EVALUATION
    # ══════════════════════════════════════════════════════════════
    yield _event("evaluation", "starting",
        "Evaluation Agent activated. Analyzing experiment results...")

    try:
        eval_result = await evaluation.run(
            selected_hypothesis, exp_code, summaries, refined_topic,
            execution_outputs=execution_outputs,
        )
        yield _event("evaluation", "completed",
            "Evaluation complete. {}".format(eval_result.overall_assessment[:150]),
            data=eval_result.model_dump(),
        )
    except Exception as e:
        yield _event("evaluation", "error", "Evaluation failed: {}".format(str(e)))
        yield _event("done", "error", str(e))
        return

    # ══════════════════════════════════════════════════════════════
    #  Stage 6: WRITER
    # ══════════════════════════════════════════════════════════════
    yield _event("writer", "starting",
        "Paper Writer Agent activated. Generating research report...")

    try:
        report = await writer.run(
            topic=refined_topic,
            papers=papers,
            summaries=summaries,
            gaps=gaps,
            hypothesis=selected_hypothesis,
            experiment=exp_code,
            evaluation=eval_result,
            execution_outputs=execution_outputs,
        )
        yield _event("writer", "completed",
            "Report generated: \"{}\"".format(report.title),
            data=report.model_dump(),
        )
    except Exception as e:
        yield _event("writer", "error", "Writer failed: {}".format(str(e)))
        yield _event("done", "error", str(e))
        return

    # ── Done ──────────────────────────────────────────────────────
    yield _event("done", "completed",
        "Research pipeline completed! All 6 agents finished. Session: {}".format(session_id),
        data={"session_id": session_id})


# ══════════════════════════════════════════════════════════════════
#  Re-run Agent (unchanged logic, updated for new agent signatures)
# ══════════════════════════════════════════════════════════════════

async def rerun_agent(stage: str, feedback: str, current_state_data: dict) -> dict:
    """Re-run a specific agent stage with user feedback."""
    from backend.models import (
        PaperSummary, Hypothesis, ExperimentCode, NotebookCell, ResearchGap, Paper
    )

    topic = current_state_data.get("topic", "")
    session_id = current_state.get("session_id", "")

    if stage == "planner":
        if feedback:
            memory_store.save_memory(session_id, "planner", "feedback_context", feedback)
        result = await planner.run(topic, session_id=session_id)
        return result

    elif stage == "paper_reader":
        queries = current_state_data.get("search_queries", [topic])
        papers, summaries, synthesis = await paper_reader.run(
            queries, max_papers=15, session_id=session_id
        )
        return {
            "papers": [p.model_dump() for p in papers],
            "summaries": [s.model_dump() for s in summaries],
            "papers_count": len(papers),
            "synthesis": synthesis,
        }

    elif stage == "hypothesis_gen":
        summaries_data = current_state_data.get("summaries", [])
        summaries = [PaperSummary(**s) for s in summaries_data]
        refined_topic = current_state_data.get("refined_topic", topic)
        if feedback:
            memory_store.save_memory(session_id, "hypothesis", "feedback_context", feedback)
        synthesis = current_state_data.get("synthesis")
        gaps, hypotheses, hypo_raw = await hypothesis.run(
            refined_topic, summaries, session_id=session_id, synthesis=synthesis
        )
        selected = hypotheses[0] if hypotheses else None
        return {
            "gaps": [g.model_dump() for g in gaps],
            "hypotheses": [h.model_dump() for h in hypotheses],
            "hypotheses_raw": hypo_raw,
            "selected_hypothesis": selected.model_dump() if selected else None,
        }

    elif stage == "experiment":
        hypo_data = current_state_data.get("selected_hypothesis", {})
        if not hypo_data:
            raise ValueError("No hypothesis available.")
        hypo = Hypothesis(**hypo_data)
        if feedback:
            hypo = Hypothesis(
                title=hypo.title,
                description=hypo.description + f"\n\nUser feedback: {feedback}",
                proposed_approach=hypo.proposed_approach,
                expected_outcome=hypo.expected_outcome,
                justification=hypo.justification,
            )
        exp = await experiment.run(hypo, current_state_data.get("refined_topic", topic))
        return {
            "cells": [c.model_dump() for c in exp.cells],
            "explanation": exp.explanation,
            "requirements": exp.requirements,
        }

    elif stage == "evaluation":
        hypo_data = current_state_data.get("selected_hypothesis", {})
        hypo = Hypothesis(**hypo_data) if hypo_data else None
        exp_data = current_state_data.get("experiment", {})
        cells = [NotebookCell(**c) for c in exp_data.get("cells", [])]
        exp = ExperimentCode(cells=cells, explanation=exp_data.get("explanation", ""))
        summaries_data = current_state_data.get("summaries", [])
        summaries = [PaperSummary(**s) for s in summaries_data]
        exec_outputs = current_state_data.get("execution_outputs", "")
        if feedback:
            exec_outputs += f"\n\nUser notes: {feedback}"
        eval_result = await evaluation.run(
            hypo, exp, summaries, current_state_data.get("refined_topic", topic),
            execution_outputs=exec_outputs,
        )
        return eval_result.model_dump()

    elif stage == "writer":
        papers_data = current_state_data.get("papers", [])
        papers = [Paper(**p) for p in papers_data]
        summaries = [PaperSummary(**s) for s in current_state_data.get("summaries", [])]
        gaps = [ResearchGap(**g) for g in current_state_data.get("gaps", [])]
        hypo = Hypothesis(**current_state_data.get("selected_hypothesis", {}))
        exp_data = current_state_data.get("experiment", {})
        cells = [NotebookCell(**c) for c in exp_data.get("cells", [])]
        exp = ExperimentCode(cells=cells, explanation=exp_data.get("explanation", ""))
        eval_data = current_state_data.get("evaluation", {})
        from backend.models import EvaluationResult
        eval_result = EvaluationResult(**eval_data) if eval_data else None
        exec_outputs = current_state_data.get("execution_outputs", "")
        report = await writer.run(
            topic=current_state_data.get("refined_topic", topic),
            papers=papers, summaries=summaries, gaps=gaps,
            hypothesis=hypo, experiment=exp, evaluation=eval_result,
            execution_outputs=exec_outputs,
        )
        return report.model_dump()

    else:
        raise ValueError(f"Unknown stage: {stage}")
