"""
Jupyter Kernel Manager — Handles stateful interactive Python execution.
Integrates with `jupyter_client` to spawn an IPython kernel and communicate via ZMQ.
"""

import sys
import asyncio
import base64
import uuid
import queue
from typing import AsyncGenerator, Dict, Any
from jupyter_client.manager import KernelManager
from dataclasses import dataclass

@dataclass
class KernelState:
    manager: KernelManager
    client: Any
    is_alive: bool = True

class JupyterKernelService:
    def __init__(self):
        self.kernel: KernelState | None = None

    def start_kernel(self):
        """Start a new IPython kernel for a stateful session."""
        if self.kernel and self.kernel.is_alive:
            return  # Already running

        # Start a local IPython kernel
        km = KernelManager(kernel_name='python3')
        km.start_kernel()
        kc = km.client()
        kc.start_channels()
        kc.wait_for_ready()

        self.kernel = KernelState(manager=km, client=kc)
        
        # Inject standard setup (e.g., matplotlib to base64) to make it work flawlessly via sockets
        setup_code = """
import sys
import os
import base64
import io
from IPython.display import display, Image

# Patch matplotlib to display inline rather than popping up windows
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def _patched_show(*args, **kwargs):
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('ascii')
        display(Image(data=base64.b64decode(img_b64), format='png'))
    plt.close("all")

plt.show = _patched_show
"""
        self._execute_sync(setup_code)

    def stop_kernel(self):
        """Shut down the active kernel completely."""
        if self.kernel:
            self.kernel.client.stop_channels()
            self.kernel.manager.shutdown_kernel(now=True)
            self.kernel = None

    def is_running(self) -> bool:
        return self.kernel is not None and self.kernel.is_alive

    def _execute_sync(self, code: str):
        """Internal synchronous execution just for initialization."""
        if not self.kernel:
            return
        msg_id = self.kernel.client.execute(code)
        while True:
            try:
                msg = self.kernel.client.get_iopub_msg(timeout=1)
                if msg['parent_header'].get('msg_id') == msg_id:
                    if msg['msg_type'] == 'status' and msg['content']['execution_state'] == 'idle':
                        break
            except queue.Empty:
                break

    async def execute_cell(self, code: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute code asynchronously and yield events in real-time.
        Yields {type: 'stdout'|'stderr'|'image'|'result'|'error', data: ...}
        """
        if not self.kernel:
            yield {"type": "error", "data": "Kernel is not running. Please start the runtime first."}
            return

        # Request execution (non-blocking)
        msg_id = self.kernel.client.execute(code)

        # Poll the IOPub channel for output messages
        while True:
            try:
                # Use asyncio.to_thread to avoid blocking the FastAPI event loop during ZMQ polling
                msg = await asyncio.to_thread(self.kernel.client.get_iopub_msg, timeout=0.1)
                
                # Make sure the message belongs to our execution request
                if msg['parent_header'].get('msg_id') != msg_id:
                    continue

                msg_type = msg['header']['msg_type']
                content = msg['content']

                if msg_type == 'stream':
                    yield {"type": content['name'], "data": content['text']}
                
                elif msg_type == 'execute_result' or msg_type == 'display_data':
                    # Rich output (like text/plain or image/png)
                    data = content.get('data', {})
                    if 'image/png' in data:
                        yield {"type": "image", "data": data['image/png']}
                    if 'text/plain' in data and msg_type == 'execute_result':
                        yield {"type": "result", "data": data['text/plain']}
                
                elif msg_type == 'error':
                    # Capture traceback
                    traceback_str = "\\n".join(content.get('traceback', []))
                    if not traceback_str:
                        traceback_str = f"{content.get('ename', 'Error')}: {content.get('evalue', '')}"
                    yield {"type": "error", "data": traceback_str}
                
                elif msg_type == 'status':
                    if content['execution_state'] == 'idle':
                        break # Execution finished

            except queue.Empty:
                # We can do a tiny sleep or just continue checking
                await asyncio.sleep(0.01)

# Global singleton instance
jupyter_service = JupyterKernelService()
