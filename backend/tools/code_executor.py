"""
Code Executor — Runs Python code in a sandboxed subprocess.
Captures stdout, stderr, and generated image files (matplotlib plots).
"""

import os
import sys
import asyncio
import tempfile
import base64
import uuid
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    """Result of executing a code cell."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    images: list[str] = field(default_factory=list)  # base64-encoded PNGs
    error: str = ""
    execution_time: float = 0.0


async def execute_code(code: str, timeout: int = 300) -> ExecutionResult:
    """
    Execute Python code in an isolated subprocess.
    
    - Captures stdout/stderr
    - Detects and captures matplotlib plots saved to a temp directory
    - Enforces a timeout (default 5 minutes)
    """
    
    # Create a temp directory for plot outputs
    work_dir = tempfile.mkdtemp(prefix="ai_research_")
    plot_dir = os.path.join(work_dir, "plots")
    os.makedirs(plot_dir, exist_ok=True)
    
    # Wrap the code to auto-save matplotlib figures
    wrapped_code = f'''
import sys
import os
os.makedirs(r"{plot_dir}", exist_ok=True)

# Patch matplotlib to save figures instead of showing them
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
_orig_show = plt.show
_fig_counter = [0]
def _patched_show(*args, **kwargs):
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        path = os.path.join(r"{plot_dir}", f"fig_{{_fig_counter[0]}}.png")
        fig.savefig(path, dpi=100, bbox_inches="tight", facecolor="white")
        _fig_counter[0] += 1
    plt.close("all")
plt.show = _patched_show

# Run the actual code
{code}

# Auto-save any remaining open figures
if plt.get_fignums():
    _patched_show()
'''

    # Write code to temp file
    code_file = os.path.join(work_dir, "cell.py")
    with open(code_file, "w", encoding="utf-8") as f:
        f.write(wrapped_code)
    
    import time
    start_time = time.time()
    
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, code_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ExecutionResult(
                success=False,
                error=f"Execution timed out after {timeout} seconds.",
                execution_time=time.time() - start_time,
            )
        
        stdout = stdout_bytes.decode("utf-8", errors="replace")[:50000]  # Cap output
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:10000]
        
        # Collect generated images
        images = []
        if os.path.exists(plot_dir):
            for fname in sorted(os.listdir(plot_dir)):
                if fname.endswith(".png"):
                    fpath = os.path.join(plot_dir, fname)
                    with open(fpath, "rb") as img_file:
                        img_b64 = base64.b64encode(img_file.read()).decode("ascii")
                        images.append(img_b64)
        
        elapsed = time.time() - start_time
        
        return ExecutionResult(
            success=(proc.returncode == 0),
            stdout=stdout,
            stderr=stderr,
            images=images,
            error=stderr if proc.returncode != 0 else "",
            execution_time=elapsed,
        )
    
    except Exception as e:
        return ExecutionResult(
            success=False,
            error=str(e),
            execution_time=time.time() - start_time,
        )
    finally:
        # Clean up temp code file (keep plots dir briefly for debugging)
        try:
            os.remove(code_file)
        except OSError:
            pass
