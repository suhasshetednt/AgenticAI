import sys
import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import threading
import queue
import builtins
import asyncio
import json

app = FastAPI()

# Message queues to bridge the sync Python code and the async WebSocket
input_queue = queue.Queue()
output_queue = queue.Queue()

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
        self.original_print(*args, **kwargs)

    def custom_input(self, prompt=""):
        # Send the prompt request to the UI
        output_queue.put({"type": "prompt", "message": prompt})
        self.original_print(prompt, end="", flush=True)
        # Block the Python thread until the UI sends a response back
        response = input_queue.get()
        self.original_print(response)
        return response

ws_io = WebSocketIO()

def run_pipeline():
    """Runs the main pipeline in a separate thread so it doesn't block FastAPI"""
    project_root = Path(__file__).parent.parent.parent.parent.parent
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    ws_io.enable()
    try:
        from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import main
        main()
    except Exception as e:
        output_queue.put({"type": "error", "message": f"Pipeline crashed: {str(e)}"})
    finally:
        ws_io.disable()
        output_queue.put({"type": "done", "message": "Workflow exited."})

@app.get("/")
def get_dashboard():
    """Serves the interactive dashboard HTML"""
    dashboard_path = Path(__file__).parent.parent.parent.parent.parent / "docs" / "ai_dashboard_prototype.html"
    return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Start the LangGraph pipeline in a background thread
    t = threading.Thread(target=run_pipeline, daemon=True)
    t.start()

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
            input_queue.put(data)
    except WebSocketDisconnect:
        sender_task.cancel()
        print("UI disconnected.")
