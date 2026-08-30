"""法律检索 Agent — LangGraph 状态图。

依据 docs/project-framework.md §5.2：
    问题 → 查询改写 → 多路检索(并行: 法条/判例/公众号) → 重排 → 过滤≤10条 → 总分结构输出

多路检索通过 Qdrant 向量库实现（法条库/判例库/公众号），详见 app/rag/qdrant_store.py。
Qdrant 不可用时自动回退到 ChromaDB。
所有 LLM 调用通过 LLMGateway。
"""
from __future__ import annotations

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.llm.gateway import gateway
from app.models.user import User
from app.rag.qdrant_store import search_multi


class SearchState(TypedDict, total=False):
    query: str
    rewritten_query: str
    raw_results: list[dict]      # 多路检索原始结果
    reranked: list[dict]         # 重排后结果
    answer: str                  # 总分结构输出
    citations: list[dict]        # 引用（≤10 条）


def build_search_graph(user: User, db: Session, _report=None):
    """构建法律检索图。

    _report: 可选 StageReport，逐节点计时（rewrite/retrieve/synthesize）。
    """
    llm = gateway.get_chat_model(user, db, temperature=0.2)

    async def rewrite_node(state: SearchState) -> dict:
        """查询改写：生成更利于检索的法律查询。"""
        if _report:
            async with _report.stage("LLM改写"):
                resp = await llm.ainvoke([
                    SystemMessage(content="改写用户法律问题为更精准的检索查询，只返回查询语句。"),
                    HumanMessage(content=state["query"]),
                ])
        else:
            resp = await llm.ainvoke([
                SystemMessage(content="改写用户法律问题为更精准的检索查询，只返回查询语句。"),
                HumanMessage(content=state["query"]),
            ])
        return {"rewritten_query": resp.content.strip()}

    async def retrieve_node(state: SearchState) -> dict:
        """多路检索（并行）：法条库 / 判例库 / 公众号观点。

        通过 Qdrant 向量检索 3 个集合，合并后按相似度排序。
        Qdrant 不可用时自动回退到 ChromaDB。
        """
        query = state.get("rewritten_query") or state.get("query", "")
        if _report:
            # search_multi 是同步阻塞调用，放到线程里避免卡事件循环
            import asyncio

            results = await asyncio.to_thread(search_multi, query, None, _report)
        else:
            results = search_multi(query)
        return {"raw_results": results}

    async def rerank_node(state: SearchState) -> dict:
        """重排 + 过滤：保留 ≤10 条最相关结果。"""
        results = state.get("raw_results", [])[:10]
        return {"reranked": results}

    async def synthesize_node(state: SearchState) -> dict:
        """总分结构输出：先结论后展开，引用可点击跳转。"""
        refs = state.get("reranked", [])
        refs_text = "\n".join(f"[{i+1}] {r['title']}: {r['content']}" for i, r in enumerate(refs))
        messages = [
            SystemMessage(
                content=(
                    "你是法律检索助手。根据检索结果回答问题。\n"
                    "输出格式要求：\n"
                    "1. 先给结论，再展开说明；\n"
                    "2. 使用 **加粗** 标注关键词和重点结论；\n"
                    "3. 必要时使用层级标题组织内容（## 二级标题、### 三级标题）；\n"
                    "4. 对比观点用 Markdown 表格呈现；\n"
                    "5. 引用参考资料时用 [序号] 标注（如 [1]、[2]）；\n"
                    "6. 使用有序或无序列表使要点清晰易读。\n"
                    "引用≤10条。"
                )
            ),
            HumanMessage(content=f"问题：{state['query']}\n\n检索结果：\n{refs_text}"),
        ]
        if _report:
            async with _report.stage("LLM综合生成"):
                resp = await llm.ainvoke(messages)
        else:
            resp = await llm.ainvoke(messages)
        return {
            "answer": resp.content,
            "citations": [{"index": i + 1, **r} for i, r in enumerate(refs)],
        }

    builder = StateGraph(SearchState)
    builder.add_node("rewrite", rewrite_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("rerank", rerank_node)
    builder.add_node("synthesize", synthesize_node)
    builder.set_entry_point("rewrite")
    builder.add_edge("rewrite", "retrieve")
    builder.add_edge("retrieve", "rerank")
    builder.add_edge("rerank", "synthesize")
    builder.add_edge("synthesize", END)

    return builder.compile()
