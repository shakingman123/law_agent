"""会话与消息 ORM。

- conversations  会话（按用户隔离，可关联案件）
- messages      会话内的消息（user/agent），含附件与 RAG 来源

对话历史持久化依据：切换页面/刷新不丢；后端取近 N 轮拼 LLM 上下文。
"""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Conversation(Base):
    """会话。每个用户可有多个会话（默认会话 + 按案件开新会话）。"""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(128), default="新对话")          # 会话标题（首条消息摘要）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    """会话消息。role: user / agent。"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)               # user / agent
    content = Column(Text, nullable=False)
    attachments = Column(JSON, default=list)                # [{fileName, url}]
    rag_sources = Column(JSON, default=list)                # ["民法典", ...]
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
