import subprocess
import os
from langchain_core.tools import tool
from typing import List, Optional

def _run_git(args: List[str], timeout: int = 30) -> str:
    """Helper to run a git command and return its output.

    Hardened so it can never hang the pipeline when launched under the dashboard
    server (uvicorn, no real console):
      - stdin=DEVNULL          : git can't block reading the inherited stdin.
      - GIT_TERMINAL_PROMPT=0 /
        GCM_INTERACTIVE=never  : credential prompts fail fast instead of hanging.
      - timeout                : any other stall is converted to a clean error.
    """
    from pathlib import Path

    current_path = Path(__file__).resolve()
    repo_root = None
    for p in [current_path] + list(current_path.parents):
        if (p / ".git").exists():
            repo_root = str(p)
            break

    if repo_root is None:
        return "Error: Could not find the .git repository root."

    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=env,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return (
            f"Error: git {' '.join(args)} timed out after {timeout}s "
            "(likely waiting on credentials/network). Configure a PAT / credential "
            "helper, or run the push manually."
        )
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"


@tool
def git_status() -> str:
    """Check the status of the local git repository (shows modified/untracked files)."""
    return _run_git(["status"])


@tool
def git_add(files: str) -> str:
    """
    Stage files for commit. 
    Args:
        files: A space-separated list of files, or '.' to stage all changes.
    """
    file_list = files.split()
    return _run_git(["add"] + file_list)


@tool
def git_commit(message: str) -> str:
    """
    Commit staged changes with a message.
    Args:
        message: The commit message.
    """
    return _run_git(["commit", "-m", message])


@tool
def git_push(branch: str = "main") -> str:
    """
    Push committed changes to the remote repository.
    Args:
        branch: The branch to push to (default: main).
    """
    return _run_git(["push", "-u", "origin", branch], timeout=120)


@tool
def git_checkout(branch: str, create: bool = False) -> str:
    """
    Switch to a branch.
    Args:
        branch: Branch name to checkout.
        create: If True, creates the branch if it doesn't exist (-b).
    """
    if create:
        return _run_git(["checkout", "-b", branch])
    return _run_git(["checkout", branch])


@tool
def git_pull(branch: str = "main") -> str:
    """
    Pull latest changes from the remote repository.
    Args:
        branch: The branch to pull from (default: main).
    """
    return _run_git(["pull", "origin", branch], timeout=120)
