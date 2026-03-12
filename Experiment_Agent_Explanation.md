# How the Experiment Agent Works

The **Experiment Agent** is responsible for taking a theoretical hypothesis and translating it into executable Python code, similar to what a data scientist would do in a Jupyter Notebook. 

Here is a deep dive into its architecture, execution logic, and the common reasons why executions might fail or show errors.

---

## 1. Code Generation Phase (`backend/agents/experiment.py`)

When the pipeline reaches the Experiment stage, the Agent acts as a code generator.

### Architecture & Logic
- **Input:** It receives the specific `Hypothesis` selected in the previous stage, along with the main research `topic`.
- **System Prompt:** It uses a highly engineered prompt instructing the LLM to behave as an "ML Experiment Code Generator Agent."
- **Constraints applied:**
  - Code must be **self-contained** and executable as-is.
  - It must use standard datasets (e.g., `sklearn.datasets`) rather than assuming an external CSV or database exists.
  - It must use `matplotlib.pyplot` for all interactive visualizations.
  - The experiment must be kept small (e.g., max 10 epochs, quick training) to fit within execution timeouts.
- **Output:** The LLM returns a strictly formatted JSON array defining sequential "Notebook Cells" (e.g., *1. Setup & Imports, 2. Dataset Loading, 3. Model Definition, etc.*), along with pip requirements and an overall text explanation.

---

## 2. Code Execution Phase (`backend/tools/code_executor.py`)

Once the code string is generated for a cell, the application attempts to run it natively on your machine file system.

### Architecture & Logic
- **Isolation via Subprocess:** The system does *not* run the AI's code directly inside the main server process (FastAPI). Doing so would be dangerous and could crash the entire application. Instead, it utilizes `asyncio.create_subprocess_exec()` to spawn a brand new, isolated Python subprocess.
- **Temporary Sandboxing:** 
  1. A temporary directory (`tempfile.mkdtemp`) is created in your OS.
  2. A subdirectory named `plots/` is created inside it.
- **Matplotlib Wrapping Technique:** The raw AI-generated code is wrapped in a special preamble script. This preamble overrides (`monkey-patches`) the standard `matplotlib.pyplot.show()` function. Instead of trying to open a pop-up window on your screen (which fails in background processes), the patch forces the code to silently save all generated plots as `.png` images into the temporary `plots/` directory.
- **Execution & Capture:** 
  - The patched Python code is executed.
  - Standard output (`stdout`, like `print()` statements) and Standard error (`stderr`, like stack traces) are actively captured.
  - An absolute timeout of **300 seconds (5 minutes)** is enforced. If the code takes longer, the executor forcefully kills the subprocess.
- **Result Aggregation:** Once the subprocess exits, the executor reads any `.png` files created in the `plots/` folder, Base64 encodes them, and bundles them alongside the `stdout` text to send back to the frontend UI.

---

## 3. Why Does the Execution Show Errors?

Because the AI is attempting to write real, functional Python code completely autonomously, several things can cause the local execution to throw an error:

1. **Missing Dependencies (ModuleNotFoundError):**
   - The AI might generate code that requires a library (e.g., `tensorflow`, `xgboost`, `networkx`) that is not currently installed in your Python environment (`venv`). 
   - *Fix:* Check the error trace on the canvas, stop the server, run `pip install [package]`, and rerun.

2. **Data Hallucinations (FileNotFoundError):**
   - Despite instructions to use synthetic data, the LLM sometimes hallucinates and writes code like `df = pd.read_csv('dataset.csv')` or `Image.open('sample.jpg')`. Because these files don't actually exist on your hard drive, the execution instantly crashes.

3. **Subprocess Timeout (TimeoutError):**
   - If the AI writes a deep learning logic block with a massive epoch count (`epochs=100`) or complex grid search, it might easily exceed the 5-minute timeout enforced by the `code_executor.py`. The system will terminate it and return an error.

4. **Logical or Syntax Errors in AI Output:**
   - LLMs are not perfect compilers. They might mismatch matrix shapes (e.g., in a PyTorch forward pass), mix up variable names across different cells, or fail to correctly import a required utility class.

5. **Pathing & OS Issues:**
   - The AI might generate Linux-specific file path syntax (`/tmp/data/`) that immediately errors out when running on a Windows OS.
