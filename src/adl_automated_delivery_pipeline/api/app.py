import sys
import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import threading
import queue
import builtins
import asyncio
import json

app = FastAPI()


def _find_docs_dir() -> Path | None:
    """Locate the optional ``docs`` directory by walking up from this file.

    The interactive dashboard assets (``docs/ai_dashboard_prototype.html`` and
    ``docs/images``) are optional and may live outside the package. Returns the
    first ``docs`` directory found, or ``None`` if absent.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs"
        if candidate.is_dir():
            return candidate
    return None


_DOCS_DIR = _find_docs_dir()

# Mount the image static dir only if it exists — the dashboard is optional.
_images_dir = (_DOCS_DIR / "images") if _DOCS_DIR else None
if _images_dir and _images_dir.is_dir():
    app.mount("/image", StaticFiles(directory=str(_images_dir)), name="image")

# Message queues to bridge the sync Python code and the async WebSocket
input_queue = queue.Queue()
output_queue = queue.Queue()

# Track the active pipeline thread to kill ghost threads when restarting
active_thread_id = None

class QueueStdout:
    def __init__(self, queue):
        self.queue = queue
        self.buffer = ""
        self.encoding = "utf-8"

    def write(self, text):
        self.buffer += text
        if "\n" in self.buffer:
            lines = self.buffer.splitlines()
            for line in lines[:-1]:
                self.queue.put({"type": "log", "message": line})
            self.buffer = lines[-1]

    def flush(self):
        pass

class WebSocketIO:
    """Intercepts built-in print() and input() to route them through WebSockets"""
    def __init__(self):
        self.original_print = builtins.print
        self.original_input = builtins.input
        self.enabled = False

    def enable(self):
        if not self.enabled:
            builtins.print = self.custom_print
            builtins.input = self.custom_input
            self.enabled = True

    def disable(self):
        if self.enabled:
            builtins.print = self.original_print
            builtins.input = self.original_input
            self.enabled = False

    def custom_print(self, *args, **kwargs):
        msg = " ".join(str(a) for a in args)
        # Send to UI as a log event
        output_queue.put({"type": "log", "message": msg})
        # Still print to actual console for debugging
        try:
            self.original_print(*args, **kwargs)
        except UnicodeEncodeError:
            encoding = getattr(sys.stdout, "encoding", "utf-8") or 'utf-8'
            safe_msg = msg.encode(encoding, errors='replace').decode(encoding)
            self.original_print(safe_msg, **kwargs)

    def custom_input(self, prompt=""):
        global active_thread_id
        current_id = threading.get_ident()
        
        # If this thread was replaced before even asking, die silently
        if active_thread_id and current_id != active_thread_id:
            raise SystemExit()

        # Send the prompt request to the UI
        output_queue.put({"type": "prompt", "message": prompt})
        try:
            self.original_print(prompt, end="", flush=True)
        except UnicodeEncodeError:
            encoding = getattr(sys.stdout, "encoding", "utf-8") or 'utf-8'
            safe_prompt = prompt.encode(encoding, errors='replace').decode(encoding)
            self.original_print(safe_prompt, end="", flush=True)
            
        # Block with a timeout so we can periodically check if we've been replaced (Ghost Thread Killer)
        while True:
            # Check if a new workflow was started while we were waiting
            if active_thread_id and current_id != active_thread_id:
                raise SystemExit()
            try:
                response = input_queue.get(timeout=0.5)
                break
            except queue.Empty:
                continue

        try:
            self.original_print(response)
        except UnicodeEncodeError:
            encoding = getattr(sys.stdout, "encoding", "utf-8") or 'utf-8'
            safe_response = response.encode(encoding, errors='replace').decode(encoding)
            self.original_print(safe_response)
        return response

ws_io = WebSocketIO()

def run_pipeline():
    """Runs the main pipeline in a separate thread so it doesn't block FastAPI"""
    # Ensure the project root (the package parent) is importable.
    module_dir = Path(__file__).resolve().parent.parent.parent  # project root
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    
    ws_io.enable()
    try:
        from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import main
        main()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        output_queue.put({"type": "error", "message": f"Pipeline crashed: {str(e)}\n{tb}"})
        print(f"Pipeline crashed:\n{tb}")
    finally:
        ws_io.disable()
        output_queue.put({"type": "done", "message": "Workflow exited."})

@app.get("/")
def get_dashboard():
    """Serves the interactive dashboard HTML, if the optional docs dir is present."""
    dashboard_path = (_DOCS_DIR / "ai_dashboard_prototype.html") if _DOCS_DIR else None
    if not dashboard_path or not dashboard_path.is_file():
        return HTMLResponse(
            "<h1>ADL Automated Delivery Pipeline</h1>"
            "<p>The interactive dashboard asset "
            "(<code>docs/ai_dashboard_prototype.html</code>) was not found. "
            "Copy the <code>docs/</code> directory into the project root to enable it.</p>",
            status_code=200,
        )
    return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Async task to continually push logs/prompts to the UI
    async def send_updates():
        while True:
            try:
                # Non-blocking get
                msg = output_queue.get_nowait()
                await websocket.send_json(msg)
            except queue.Empty:
                await asyncio.sleep(0.1)
                
    sender_task = asyncio.create_task(send_updates())

    try:
        while True:
            # When the UI submits an input response, push it to the input_queue to unblock custom_input()
            data = await websocket.receive_text()
            
            if data == "START_WORKFLOW":
                global active_thread_id
                
                # Clear queues to prevent ghost threads from stealing inputs if the user restarted
                while not input_queue.empty():
                    try: input_queue.get_nowait()
                    except queue.Empty: break
                while not output_queue.empty():
                    try: output_queue.get_nowait()
                    except queue.Empty: break
                    
                # Start the LangGraph pipeline in a background thread only on manual trigger
                t = threading.Thread(target=run_pipeline, daemon=True)
                t.start()
                active_thread_id = t.ident
                
                output_queue.put({"type": "log", "message": "Initiating workflow execution..."})
            else:
                input_queue.put(data)
    except WebSocketDisconnect:
        sender_task.cancel()
        print("UI disconnected.")
