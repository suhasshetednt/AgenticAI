"""Entry point alias — delegates to workflow.py (this file was originally adl_workflow.py)."""
import runpy, pathlib

runpy.run_path(
    str(pathlib.Path(__file__).parent / "workflow.py"),
    run_name="__main__",
)
