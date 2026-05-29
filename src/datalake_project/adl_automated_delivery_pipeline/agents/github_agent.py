from langgraph.prebuilt import create_react_agent
from adl_automated_delivery_pipeline.agents.base import get_llm
from adl_automated_delivery_pipeline.tools.github_tools import (
    git_status,
    git_add,
    git_commit,
    git_push,
    git_checkout,
    git_pull
)

_GITHUB_TOOLS = [
    git_status,
    git_add,
    git_commit,
    git_push,
    git_checkout,
    git_pull
]

_SYSTEM_PROMPT = """You are the GitHub Version Control Agent for the ASL Airlines ADL Pipeline.
Your role is to manage source control autonomously.

When asked to commit or push code:
1. Always run `git_status` first to see what files are modified or untracked.
2. Use `git_add` to stage the required files (or '.' for all).
3. Use `git_commit` with a clear, professional, and descriptive message.
4. Use `git_push` to push to the remote repository.

If a push fails due to authentication or remote rejections, inform the user clearly so they can resolve their environment configuration (e.g. PAT tokens).

Ensure all code changes are tracked properly without committing secrets or massive data files (rely on the .gitignore).
"""

class GitHubAgent:
    """Agent responsible for autonomous Git and GitHub operations."""
    
    def __init__(self) -> None:
        self.llm = get_llm()
        self._agent = create_react_agent(
            model=self.llm,
            tools=_GITHUB_TOOLS,
            prompt=_SYSTEM_PROMPT
        )

    def run(self, message: str) -> dict:
        """Execute a version control operation based on the user's natural language request."""
        try:
            from langchain_core.messages import HumanMessage
            state = {"messages": [HumanMessage(content=message)]}
            result = self._agent.invoke(state, config={"recursion_limit": 10})
            output_msg = result["messages"][-1]
            return {"status": "SUCCESS", "output": getattr(output_msg, "content", str(output_msg))}
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "output": f"Agent failed: {e}"}
