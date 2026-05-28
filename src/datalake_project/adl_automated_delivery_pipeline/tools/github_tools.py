import subprocess
import os
from langchain.tools import tool
from typing import List, Optional

def _run_git(args: List[str]) -> str:
    """Helper to run a git command and return its output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
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
    return _run_git(["push", "-u", "origin", branch])


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
    return _run_git(["pull", "origin", branch])
