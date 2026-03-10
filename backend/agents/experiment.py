"""
Experiment Agent -- Generates executable notebook cells with real datasets.
Produces self-contained code that can be executed locally (small experiments).
"""

import uuid
from backend.tools.llm_client import call_llm_json
from backend.models import Hypothesis, ExperimentCode, NotebookCell

SYSTEM_PROMPT = """You are an ML Experiment Code Generator Agent. You generate EXECUTABLE Python 
notebook cells for a machine learning experiment based on a research hypothesis.

CRITICAL RULES:
1. Every code cell must be SELF-CONTAINED and EXECUTABLE as-is
2. Use sklearn or small built-in datasets (never assume external data files exist)
3. Use matplotlib for ALL visualizations
4. Keep experiments small: max 10 epochs, small batch sizes
5. Always print numerical results (accuracy, F1, loss values)
6. Include data visualization cells

You MUST respond with valid JSON in this exact format:
{
  "cells": [
    {
      "title": "Cell title",
      "description": "What this cell does",
      "code": "executable python code here"
    }
  ],
  "explanation": "Overall experiment design explanation",
  "requirements": "pip packages needed (one per line)"
}

Generate exactly these cells in order:
1. "Setup & Imports" - Import all libraries
2. "Dataset Loading & Exploration" - Load dataset, show shape, class distribution, sample visualization
3. "Data Preprocessing & Augmentation" - Feature engineering, normalization, train/test split
4. "Model Definition" - Define the model architecture
5. "Model Training" - Training loop with loss tracking
6. "Evaluation & Metrics" - Compute accuracy, F1, precision, recall, confusion matrix
7. "Results Visualization" - Plot training curves, confusion matrix, ROC curve

Each cell must print its results. Use plt.show() for all plots."""


async def run(hypothesis: Hypothesis, topic: str) -> ExperimentCode:
    """Generate executable experiment notebook cells."""

    user_prompt = f"""Generate a complete, EXECUTABLE ML experiment for:

Research Topic: {topic}

Hypothesis: {hypothesis.title}
Description: {hypothesis.description}
Proposed Approach: {hypothesis.proposed_approach}
Expected Outcome: {hypothesis.expected_outcome}

IMPORTANT REQUIREMENTS:
- Use sklearn datasets (e.g., load_digits, fetch_20newsgroups, make_classification) 
  OR generate synthetic data that matches the research domain
- All code must run WITHOUT any external files or GPU
- Use scikit-learn, PyTorch (CPU), or both
- Include comprehensive data exploration and visualization
- Print all metrics numerically
- Use matplotlib for all plots with plt.show()
- Keep training fast (< 2 minutes total)
- Show a clear comparison between a baseline and the proposed approach"""

    result = await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.4,
        max_tokens=8192,
    )

    cells = []
    for i, cell_data in enumerate(result.get("cells", [])):
        cells.append(NotebookCell(
            cell_id=f"cell_{i}_{uuid.uuid4().hex[:6]}",
            cell_type="code",
            title=cell_data.get("title", f"Cell {i + 1}"),
            code=cell_data.get("code", "# No code generated"),
            description=cell_data.get("description", ""),
        ))

    return ExperimentCode(
        cells=cells,
        explanation=result.get("explanation", ""),
        requirements=result.get("requirements", "scikit-learn\nmatplotlib\nnumpy"),
    )
