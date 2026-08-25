"""会话与消息 Pydantic 模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    attachments: list[dict] = []
    rag_sources: list[dict] = []    # [{index, title, source, content}]
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator('rag_sources', mode='before')
    @classmethod
    def normalize_rag_sources(cls, v):
        """兼容旧数据：将 string[] 转为结构化 dict 格式。"""
        if not v:
            return []
        result = []
        for i, item in enumerate(v):
            if isinstance(item, str):
                result.append({"index": i + 1, "title": item, "source": item, "content": ""})
            elif isinstance(item, dict):
                result.append(item)
            else:
                result.append({"index": i + 1, "title": str(item), "source": str(item), "content": ""})
        return result


class ConversationOut(BaseModel):
    id: int
    title: str
    user_id: int
    case_id: Optional[int] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationWithMessages(ConversationOut):
    """会话 + 历史消息（进入会话时一次性加载）。"""

    messages: list[MessageOut] = []


class ConversationCreate(BaseModel):
    title: str = "新对话"
    case_id: Optional[int] = None
