"""法律检索 Agent（RAG）。依据 docs/project-framework.md §5.2。"""
from app.agents.legal_search.graph import build_search_graph, SearchState

__all__ = ["build_search_graph", "SearchState"]
