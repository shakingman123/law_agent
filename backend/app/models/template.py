"""文书模板 ORM。

- scope=public  公共模板（系统内置，所有用户可用）
- scope=private 私有模板（用户自建）

模板内容用 {{占位符}} 标记，生成时由案件信息 + 用户输入填充。
"""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)          # 模板名称，如「民事起诉状」
    doc_type = Column(String(32), nullable=False, index=True)  # 起诉状/答辩状/反诉状/上诉状/申请书等
    content = Column(Text, nullable=False)               # 模板正文（含 {{占位符}}）
    placeholders = Column(JSON, default=list)             # ["原告","被告",...]
    scope = Column(String(16), default="public")          # public / private
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # private 模板归属
    created_at = Column(DateTime, default=datetime.utcnow)
