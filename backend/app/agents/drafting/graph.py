"""文书撰写 Agent — LangGraph 状态图。

依据 docs/implementation-guide.md §3.1：
    intent → template → case → collect → draft → review(interrupt) → finalize

review 节点用 interrupt() 暂停，前端弹「文书预览 + 微调/确认」，
用户确认后通过 Command(resume={"confirmed": True}) 继续。
所有 LLM 调用通过 LLMGateway，不直接接触 API Key。
"""
from __future__ import annotations

import json
import logging
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.gateway import QuotaExceeded, gateway
from app.models.case import Case
from app.models.user import User

from app.agents.drafting.tools import (
    generate_docx,
    generate_pdf,
    get_template_by_id,
    get_template_by_type,
    render_template,
    template_to_dict,
)

logger = logging.getLogger("app.agents.drafting")


def _create_checkpointer():
    """根据 CHECKPOINTER_TYPE 环境变量创建检查点保存器。

    - memory: MemorySaver（默认，开发环境，进程内存，重启后丢失）
    - sqlite: SqliteSaver（本地文件持久化，适合单机部署）
    - postgres: PostgresSaver（生产环境，多实例共享，自动建表）

    任意类型初始化失败时自动回退 MemorySaver，保证服务可用。
    """
    cp_type = settings.CHECKPOINTER_TYPE.lower().strip()

    if cp_type == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            pg_url = settings.CHECKPOINTER_PG_URL or settings.DATABASE_URL
            if not pg_url.startswith("postgresql"):
                logger.warning(
                    "[checkpointer] 连接串非 PostgreSQL（%s...），回退 MemorySaver",
                    pg_url[:50],
                )
                return MemorySaver()
            checkpointer = PostgresSaver.from_conn_string(pg_url)
            # setup() 创建检查点表（幂等，已存在则跳过）
            checkpointer.setup()
            logger.info("[checkpointer] 使用 PostgresSaver 持久化检查点")
            return checkpointer
        except Exception as e:  # noqa: BLE001
            logger.warning("[checkpointer] PostgresSaver 初始化失败，回退 MemorySaver: %s", e)
            return MemorySaver()

    if cp_type == "sqlite":
        try:
            import sqlite3

            from langgraph.checkpoint.sqlite import SqliteSaver

            db_path = settings.CHECKPOINTER_SQLITE_PATH
            conn = sqlite3.connect(db_path, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
            checkpointer.setup()
            logger.info("[checkpointer] 使用 SqliteSaver 持久化检查点: %s", db_path)
            return checkpointer
        except Exception as e:  # noqa: BLE001
            logger.warning("[checkpointer] SqliteSaver 初始化失败，回退 MemorySaver: %s", e)
            return MemorySaver()

    # 默认 memory
    logger.info("[checkpointer] 使用 MemorySaver（内存检查点，重启后丢失）")
    return MemorySaver()


# 共享检查点：跨请求保持图状态（resume 时能找到 thread_id）
# 通过 CHECKPOINTER_TYPE 环境变量配置：memory(默认)/sqlite/postgres
SHARED_CHECKPOINTER = _create_checkpointer()


# 案件字段 → 模板占位符的映射
CASE_FIELD_MAP = {
    "原告": "plaintiff",
    "被告": "defendant",
    "上诉人": "plaintiff",
    "被上诉人": "defendant",
    "答辩人": "plaintiff",
    "被答辩人": "defendant",
    "委托人": "plaintiff",
    "法院": "court",
    "此致": "court",
}


class DraftState(TypedDict, total=False):
    """文书撰写流程的状态。"""

    user_input: str
    doc_type: str                    # 上诉状/答辩状/起诉状...
    template_id: Optional[int]       # 指定模板 id
    template_content: str            # 模板原文
    case_id: Optional[int]
    case_name: str
    collected: dict                   # 已收集的信息
    missing_fields: list[str]        # 缺失字段
    draft: str                        # 生成的草稿
    confirmed: bool
    user_feedback: str               # 用户微调反馈
    file_url: str                     # 定稿后的 docx URL
    pdf_url: str                      # 定稿后的 pdf URL
    error: str


def build_draft_graph(user: User, db: Session):
    """构造编译好的文书撰写图。

    每次对话请求构造一个图实例，节点闭包捕获 user/db，
    通过 LLMGateway 取 ChatModel（不直接接触 Key）。
    """
    logger.info("[build_draft_graph] 构造图实例: user_id=%s", user.id)
    cfg = gateway.resolve_config(user, db)
    llm = gateway.get_chat_model(user, db, temperature=0.4)
    logger.info("[build_draft_graph] ChatModel 就绪: model=%s", llm.model_name)

    # -------- 节点 --------

    async def intent_node(state: DraftState) -> dict:
        """① 意图识别：判断用户要写的文书类型。"""
        user_input_preview = (state["user_input"] or "")[:50]
        logger.info("[intent_node] 入口: user_id=%s, input_preview=%r", user.id, user_input_preview)
        try:
            logger.debug("[intent_node] 调用 LLM 识别文书类型")
            resp = await llm.ainvoke([
                SystemMessage(
                    content=(
                        "你是法律文书助手。根据用户输入，识别要写的文书类型，"
                        "只能从以下选项中选：起诉状/答辩状/反诉状/上诉状/代理词/"
                        "再审申请书/申请书/异议书/授权委托书/身份证明书。"
                        "只返回类型名，不要其他内容。若无法判断返回 unknown。"
                    )
                ),
                HumanMessage(content=state["user_input"]),
            ])
            doc_type = resp.content.strip()
            logger.info(
                "[intent_node] LLM 返回 doc_type=%r, usage_metadata=%s",
                doc_type, resp.usage_metadata,
            )
            # 用量记账
            if resp.usage_metadata:
                gateway.record_usage(
                    user, cfg,
                    llm.model_name,
                    resp.usage_metadata.get("input_tokens", 0),
                    resp.usage_metadata.get("output_tokens", 0),
                    db,
                )
            return {"doc_type": doc_type}
        except QuotaExceeded:
            logger.warning("[intent_node] 额度已用尽: user_id=%s", user.id)
            return {"error": "额度已用尽", "doc_type": "unknown"}
        except Exception as e:  # noqa: BLE001
            logger.exception("[intent_node] 意图识别失败: user_id=%s, error=%s", user.id, e)
            return {"error": f"意图识别失败：{e}", "doc_type": "unknown"}

    def template_node(state: DraftState) -> dict:
        """② 模板选择：优先按 template_id 取，否则按文书类型取公共模板。"""
        doc_type = state.get("doc_type", "")
        template_id = state.get("template_id")
        logger.info("[template_node] 入口: doc_type=%r, template_id=%s", doc_type, template_id)
        tpl = get_template_by_id(db, template_id) or get_template_by_type(db, doc_type)
        tpl_dict = template_to_dict(tpl)
        if not tpl_dict:
            logger.warning("[template_node] 未找到匹配模板: doc_type=%r", doc_type)
            return {"template_content": "", "missing_fields": []}
        placeholders = list(tpl_dict["placeholders"])
        logger.info(
            "[template_node] 命中模板: id=%s, doc_type=%r, placeholders=%s",
            getattr(tpl, "id", None), doc_type, placeholders,
        )
        return {
            "template_content": tpl_dict["content"],
            "missing_fields": placeholders,
        }

    async def case_node(state: DraftState) -> dict:
        """③ 案件关联：从 DB 取案件信息，映射到模板占位符。"""
        case_id = state.get("case_id")
        case_name = state.get("case_name", "")
        logger.info("[case_node] 入口: case_id=%s, case_name=%r", case_id, case_name)

        collected: dict = {}
        if case_id:
            case = db.get(Case, case_id)
            if case:
                logger.info(
                    "[case_node] 命中案件: id=%s, name=%r, plaintiff=%r, court=%r",
                    case.id, case.name, case.plaintiff, case.court,
                )
                case_name = case.name or case_name
                # 把案件字段映射到模板占位符
                placeholder_to_value = {
                    "原告": case.plaintiff,
                    "被告": case.defendant,
                    "上诉人": case.plaintiff,
                    "被上诉人": case.defendant,
                    "答辩人": case.plaintiff,
                    "被答辩人": case.defendant,
                    "委托人": case.plaintiff,
                    "对方当事人": case.defendant,
                    "法院": case.court,
                    "此致": case.court,
                    "事实与理由": case.summary,
                }
                for ph, val in placeholder_to_value.items():
                    if val:
                        collected[ph] = val
                # 把已收集的从 missing_fields 移除
                missing = state.get("missing_fields", [])
                still_missing = [f for f in missing if f not in collected]
                return {
                    "case_name": case_name,
                    "collected": collected,
                    "missing_fields": still_missing,
                }
        return {"case_name": case_name}

    async def collect_node(state: DraftState) -> dict:
        """④ 信息收集：LLM 判断缺失字段并尝试补全（与案件已有信息合并）。"""
        missing = state.get("missing_fields", [])
        # 已有案件信息（case_node 写入），不可被覆盖
        existing = dict(state.get("collected", {}))
        logger.info(
            "[collect_node] 入口: doc_type=%r, missing_fields=%s, existing_keys=%s",
            state.get("doc_type", ""), missing, list(existing.keys()),
        )
        if not missing:
            logger.debug("[collect_node] 无缺失字段，跳过 LLM 调用")
            return {"collected": existing, "missing_fields": []}

        try:
            prompt = (
                f"用户要写一份《{state['doc_type']}》，模板需要的字段有：{missing}。\n"
                f"用户输入：{state['user_input']}\n"
                f"案件名称：{state.get('case_name', '未指定')}\n"
                "请从用户输入中尽量提取这些字段，以 JSON 返回，"
                "键为字段名，值为提取到的内容（提取不到的不要写）。只返回 JSON。"
            )
            logger.debug("[collect_node] 调用 LLM 提取字段")
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            logger.info(
                "[collect_node] LLM 返回: content_preview=%r, usage_metadata=%s",
                (resp.content or "")[:80], resp.usage_metadata,
            )
            if resp.usage_metadata:
                gateway.record_usage(
                    user, cfg,
                    llm.model_name,
                    resp.usage_metadata.get("input_tokens", 0),
                    resp.usage_metadata.get("output_tokens", 0),
                    db,
                )
            try:
                extracted = json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())
                logger.info("[collect_node] JSON 解析成功: keys=%s", list(extracted.keys()) if isinstance(extracted, dict) else "非字典")
            except Exception as e:  # noqa: BLE001
                logger.warning("[collect_node] JSON 解析失败，extracted 置空: error=%s", e)
                extracted = {}
            # 合并：案件已有信息优先，LLM 提取的补充缺失项
            collected = {**extracted, **existing}
            still_missing = [f for f in missing if f not in collected]
            logger.info(
                "[collect_node] 完成: collected_keys=%s, still_missing=%s",
                list(collected.keys()), still_missing,
            )
            return {"collected": collected, "missing_fields": still_missing}
        except Exception as e:  # noqa: BLE001
            logger.exception("[collect_node] 信息收集失败: error=%s", e)
            return {"error": f"信息收集失败：{e}", "collected": {}, "missing_fields": missing}

    async def draft_node(state: DraftState) -> dict:
        """⑤ 生成草稿：模板 + 案件信息 → 文书。"""
        template_content = state.get("template_content", "")
        collected = state.get("collected", {})

        # 若有用户微调反馈，让 LLM 据此修改草稿
        feedback = state.get("user_feedback")
        if feedback and state.get("draft"):
            logger.info(
                "[draft_node] 微调模式: feedback_preview=%r, 原草稿长度=%d",
                feedback[:80], len(state["draft"]),
            )
            try:
                logger.debug("[draft_node] 调用 LLM 按反馈微调")
                resp = await llm.ainvoke([
                    SystemMessage(content="根据用户反馈修改文书草稿，直接返回修改后的完整文书。"),
                    HumanMessage(content=f"原草稿：\n{state['draft']}\n\n用户反馈：{feedback}"),
                ])
                logger.info(
                    "[draft_node] 微调完成: 新草稿长度=%d, usage_metadata=%s",
                    len(resp.content or ""), resp.usage_metadata,
                )
                if resp.usage_metadata:
                    gateway.record_usage(
                        user, cfg,
                        llm.model_name,
                        resp.usage_metadata.get("input_tokens", 0),
                        resp.usage_metadata.get("output_tokens", 0),
                        db,
                    )
                return {"draft": resp.content}
            except Exception as e:  # noqa: BLE001
                logger.exception("[draft_node] 微调失败: error=%s", e)
                return {"error": f"微调失败：{e}", "draft": state["draft"]}

        # 首次生成：填模板 + LLM 格式规范与润色
        logger.info(
            "[draft_node] 首次生成: template_len=%d, collected_keys=%s, missing=%s",
            len(template_content),
            list(collected.keys()) if isinstance(collected, dict) else [],
            state.get("missing_fields", []),
        )
        rendered = render_template(template_content, collected)
        logger.debug("[draft_node] 模板已填充: rendered_len=%d", len(rendered))
        try:
            logger.debug("[draft_node] 调用 LLM 生成文书")
            resp = await llm.ainvoke([
                SystemMessage(
                    content=(
                        "你是资深律师。请仅对已提供的文书内容进行格式规范、"
                        "语言润色与结构整理，使表达专业、通顺。"
                        "严禁编造、补充或猜测任何缺失的事实、理由、当事人、日期等案件信息；"
                        "文中标注“（此处待补充）”的内容保持原样，不得自行填写。"
                        "直接返回完整文书内容，不要解释。"
                    )
                ),
                HumanMessage(content=f"当前文书：\n{rendered}"),
            ])
            logger.info(
                "[draft_node] 生成完成: 草稿长度=%d, usage_metadata=%s",
                len(resp.content or ""), resp.usage_metadata,
            )
            if resp.usage_metadata:
                gateway.record_usage(
                    user, cfg,
                    llm.model_name,
                    resp.usage_metadata.get("input_tokens", 0),
                    resp.usage_metadata.get("output_tokens", 0),
                    db,
                )
            return {"draft": resp.content, "user_feedback": ""}
        except Exception as e:  # noqa: BLE001
            logger.exception("[draft_node] 生成草稿失败: error=%s", e)
            return {"error": f"生成草稿失败：{e}", "draft": rendered}

    def review_node(state: DraftState) -> dict:
        """⑥ 预览确认节点。

        使用 interrupt_before=["review"] 机制：图在执行到本节点前暂停，
        前端拿到草稿后弹「预览 + 微调/确认」。
        用户确认后通过 aupdate_state 写入 confirmed/user_feedback，再 ainvoke(None) 继续。
        本节点只做日志，决策值已在状态中（由 resume 端点写入）。
        """
        logger.info(
            "[review_node] 进入预览确认: doc_type=%r, 草稿长度=%d, missing=%s, confirmed=%s",
            state.get("doc_type", ""),
            len(state.get("draft", "")),
            state.get("missing_fields", []),
            state.get("confirmed"),
        )
        # confirmed / user_feedback 由 resume 端点通过 aupdate_state 写入状态
        return {}

    def finalize_node(state: DraftState) -> dict:
        """⑦ 确认定稿：生成 .docx + .pdf 并返回下载 URL。"""
        logger.info(
            "[finalize_node] 定稿: doc_type=%r, case_id=%s, 草稿长度=%d",
            state.get("doc_type", ""),
            state.get("case_id"),
            len(state.get("draft", "")),
        )
        doc_type = state.get("doc_type", "文书")
        draft = state.get("draft", "")
        case_id = state.get("case_id")
        file_url = generate_docx(doc_type, draft, case_id)
        pdf_url = generate_pdf(doc_type, draft, case_id)
        logger.info("[finalize_node] 文件已生成: docx=%s, pdf=%s", file_url, pdf_url)
        return {"file_url": file_url, "pdf_url": pdf_url}

    # -------- 路由 --------

    def review_router(state: DraftState) -> str:
        """确认 → finalize；微调 → draft 重生成。"""
        if state.get("error"):
            logger.warning("[review_router] 检测到 error，结束流程: error=%s", state.get("error"))
            return END
        next_node = "finalize" if state.get("confirmed") else "draft"
        logger.info(
            "[review_router] 路由决策: confirmed=%s -> %s",
            state.get("confirmed"), next_node,
        )
        return next_node

    def entry_router(state: DraftState) -> str:
        """出错时直接结束。"""
        if state.get("error"):
            logger.warning("[entry_router] 检测到 error，跳过后续: error=%s", state.get("error"))
            return END
        return "template"

    # -------- 构图 --------

    logger.debug("[build_draft_graph] 注册节点与边")
    builder = StateGraph(DraftState)
    builder.add_node("intent", intent_node)
    builder.add_node("template", template_node)
    builder.add_node("case", case_node)
    builder.add_node("collect", collect_node)
    builder.add_node("draft", draft_node)
    builder.add_node("review", review_node)
    builder.add_node("finalize", finalize_node)

    builder.set_entry_point("intent")
    builder.add_conditional_edges("intent", entry_router, {"template": "template", END: END})
    builder.add_edge("template", "case")
    builder.add_edge("case", "collect")
    builder.add_edge("collect", "draft")
    builder.add_edge("draft", "review")
    builder.add_conditional_edges("review", review_router, {"finalize": "finalize", "draft": "draft"})
    builder.add_edge("finalize", END)

    logger.info("[build_draft_graph] 图编译完成: user_id=%s", user.id)
    return builder.compile(checkpointer=SHARED_CHECKPOINTER, interrupt_before=["review"])
