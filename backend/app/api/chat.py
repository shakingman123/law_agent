"""对话接口：文书撰写 Agent 的 HTTP 入口。

依据 docs/implementation-guide.md §3.2「生成预览→用户确认」：
- POST /api/chat/draft        启动流程，运行到 review 节点 interrupt，返回草稿
- POST /api/chat/draft/{tid}/resume   用户确认/微调后恢复执行

LangGraph 的 interrupt 在 review 节点暂停，invoke 自动返回当前状态；
通过 graph.get_state(config).next 判断是否仍在等待。
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, logger
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.database import SessionLocal
from app.models.user import User
from app.agents.drafting import build_draft_graph
from app.api.prompts import get_prompt
from app.llm.gateway import gateway, QuotaExceeded
from app.rag import retrieve
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    DraftRequest,
    DraftResponse,
    ResumeRequest,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _build_response(thread_id: str, state: dict, graph, config) -> DraftResponse:
    """根据图执行后的状态构造响应。"""
    # 是否仍在 interrupt 暂停（next 非空表示有节点等待执行）
    state_obj = graph.get_state(config)
    awaiting = bool(state_obj.next)

    return DraftResponse(
        thread_id=thread_id,
        doc_type=state.get("doc_type", ""),
        draft=state.get("draft", ""),
        missing_fields=state.get("missing_fields", []),
        awaiting_review=awaiting,
        done=bool(state.get("file_url")),
        file_url=state.get("file_url", ""),
        pdf_url=state.get("pdf_url", ""),
        error=state.get("error", ""),
    )


@router.post("/draft", response_model=DraftResponse)
async def start_draft(
    payload: DraftRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """启动文书撰写流程。

    运行图直到 review 节点的 interrupt 暂停，返回草稿供前端预览。
    若中途出错（如额度不足、无可用 LLM 配置），直接返回错误。
    """
    try:
        graph = build_draft_graph(user, db)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "user_input": payload.user_input,
        "case_id": payload.case_id,
        "case_name": payload.case_name or "",
        "template_id": payload.template_id,
        "collected": {},
        "missing_fields": [],
        "confirmed": False,
    }

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"流程执行失败：{e}")

    return _build_response(thread_id, result, graph, config)


@router.post("/draft/{thread_id}/resume", response_model=DraftResponse)
async def resume_draft(
    thread_id: str,
    payload: ResumeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户确认定稿或提交微调意见后恢复执行。

    使用 interrupt_before=["review"] 机制：
    - 通过 aupdate_state 写入 confirmed/user_feedback
    - 再 ainvoke(None) 继续执行 review → finalize（或 draft 重生成）
    """
    try:
        graph = build_draft_graph(user, db)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    config = {"configurable": {"thread_id": thread_id}}

    # 校验该 thread 确实存在且仍在等待（next 含 review）
    state_obj = graph.get_state(config)
    if not state_obj or not state_obj.next:
        raise HTTPException(status_code=404, detail="会话不存在或已结束")

    # 写入用户决策到状态
    graph.update_state(
        config,
        {"confirmed": payload.confirmed, "user_feedback": payload.feedback or ""},
    )

    try:
        result = await graph.ainvoke(None, config=config)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"恢复执行失败：{e}")

    return _build_response(thread_id, result, graph, config)


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(
    payload: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """通用对话：存库 → 取近 N 轮历史 → RAG 检索 → 拼 LLM 上下文 → 回复并存库。

    上下文保存规则：
    - 每条 user/agent 消息都落 messages 表（永久持久化，切换页面不丢）
    - 调 LLM 时只拼最近 CHAT_HISTORY_ROUNDS 轮（1 轮=user+agent），超出截断
    - 截断的旧消息仍在 DB 与 UI 中可见，只是不进 LLM 上下文
    - LLM 未配置时仍存用户消息并返回 RAG 来源
    """
    from datetime import datetime

    from app.core.config import settings
    from app.models.conversation import Conversation, Message

    # ① 解析/创建会话
    conv = None
    if payload.conversation_id:
        conv = db.get(Conversation, payload.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(status_code=404, detail="会话不存在")
    if conv is None:
        conv = (
            db.query(Conversation)
            .filter_by(user_id=user.id)
            .order_by(Conversation.last_message_at.desc())
            .first()
        )
        if conv is None:
            conv = Conversation(user_id=user.id, title=payload.message[:20] or "新对话")
            db.add(conv)
            db.commit()
            db.refresh(conv)

    # ② 存用户消息（无论 LLM 是否可用都先存）
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=payload.message,
        attachments=[{"url": u} for u in payload.attachments],
    )
    db.add(user_msg)
    # 首条消息更新会话标题
    if conv.title in ("新对话", "") and payload.message:
        conv.title = payload.message[:20]
    conv.last_message_at = datetime.utcnow()
    db.commit()
    db.refresh(user_msg)

    # ③ RAG 检索（先于 LLM 检查，确保即使无 LLM 也能返回检索结果）
    # rag_sources 存结构化引用：[{index, title, source, content}]
    rag_sources: list[dict] = []
    context_block = ""
    if payload.use_rag:
        try:
            hits = retrieve(payload.message)
            if hits:
                context_block = "\n\n【知识库参考资料】\n" + "\n---\n".join(
                    f"[{i+1}] 来源：{h.get('source', '未知')}\n{h.get('content', '')}"
                    for i, h in enumerate(hits)
                )
                rag_sources = [
                    {
                        "index": i + 1,
                        "title": h.get("source", "未知来源"),
                        "source": h.get("source", ""),
                        "content": h.get("content", ""),
                    }
                    for i, h in enumerate(hits)
                ]
        except Exception:  # noqa: BLE001
            pass

    # ④ 附件提示
    user_content = payload.message
    if payload.attachments:
        user_content += f"\n\n（用户已上传附件：{', '.join(payload.attachments)}）"
    if payload.case_name:
        user_content += f"\n（当前案件：{payload.case_name}）"

    # ⑤ 获取 LLM（未配置时返回错误 + RAG 来源，不抛 HTTP 异常）
    try:
        cfg = gateway.resolve_config(user, db)
        llm = gateway.get_chat_model(user, db, temperature=0.4)
    except RuntimeError as e:
        return ChatMessageResponse(
            reply="",
            rag_sources=rag_sources,
            conversation_id=conv.id,
            error=str(e),
        )

    # ⑥ 取近 N 轮历史拼 LLM 上下文（1 轮=user+agent，共 2 条）
    rounds = settings.CHAT_HISTORY_ROUNDS
    history = (
        db.query(Message)
        .filter_by(conversation_id=conv.id)
        .filter(Message.id < user_msg.id)  # 排除刚存的当前消息
        .order_by(Message.created_at.desc())
        .limit(rounds * 2)
        .all()
    )
    history.reverse()  # 恢复时间正序
    history_msgs = []
    for m in history:
        if m.role == "user":
            history_msgs.append(HumanMessage(content=m.content))
        else:
            from langchain_core.messages import AIMessage
            history_msgs.append(AIMessage(content=m.content))

    # ⑦ 系统提示词：优先取 prompts 库（chat/system），用 {{context}} 占位
    sys_tpl = get_prompt(db, "chat", "system") or (
        "你是一位专业的法律助手。请基于已知信息和知识库内容回答用户问题。\n"
        "输出格式要求：\n"
        "1. 先给结论，再展开说明，确保条理清晰；\n"
        "2. 使用 **加粗** 标注关键词和重点结论；\n"
        "3. 必要时使用层级标题组织内容（## 二级标题、### 三级标题）；\n"
        "4. 对比类信息用 Markdown 表格呈现；\n"
        "5. 引用参考资料时用 [序号] 标注（如 [1]、[2]），序号对应知识库参考资料编号；\n"
        "6. 使用有序或无序列表使要点清晰易读。\n"
        "{{context}}"
    )
    system_content = sys_tpl.replace("{{context}}", context_block)

    # ⑧ 调 LLM：system + 历史 N 轮 + 当前用户消息
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=system_content),
            *history_msgs,
            HumanMessage(content=user_content),
        ])
        # 用量记账（失败不阻断对话回复）
        if resp.usage_metadata:
            try:
                gateway.record_usage(
                    user, cfg,
                    llm.model_name,
                    resp.usage_metadata.get("input_tokens", 0),
                    resp.usage_metadata.get("output_tokens", 0),
                    db,
                )
            except Exception:  # noqa: BLE001
                logger.warning("[chat_message] 用量记账失败，不影响对话回复", exc_info=True)
        # ⑨ 存 agent 回复
        agent_msg = Message(
            conversation_id=conv.id,
            role="agent",
            content=resp.content,
            rag_sources=rag_sources,
        )
        db.add(agent_msg)
        conv.last_message_at = datetime.utcnow()
        db.commit()
        db.refresh(agent_msg)
        return ChatMessageResponse(
            reply=resp.content,
            rag_sources=rag_sources,
            conversation_id=conv.id,
            message_id=agent_msg.id,
        )
    except QuotaExceeded as e:
        return ChatMessageResponse(
            error=str(e), rag_sources=rag_sources, conversation_id=conv.id
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("[chat_message] 对话调用失败: %s", e)
        raise HTTPException(status_code=500, detail=f"对话失败：{e}")
