"""Prompt 模板库 ORM。

用于集中管理 Agent 的系统提示词，取代硬编码。
分类如：drafting（文书撰写）/ search（检索）/ chat（通用对话）。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class PromptTemplate(Base):
    """Prompt 模板。content 中可用 {{变量}} 占位。"""

    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False, index=True)   # drafting/search/chat
    key = Column(String(64), nullable=False, index=True)        # 同分类下唯一标识，如 intent/system
    content = Column(Text, nullable=False)
    variables = Column(JSON, default=list)                      # 变量名列表
    is_system = Column(Boolean, default=False)                   # 是否系统内置（不可删除）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
