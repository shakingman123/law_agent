"""法律检索库 ORM。

依据 docs/project-framework.md §5.3：
- legal_references 检索库（法条/判例/公司案例/公众号）
  字段：id, type, title, content, embedding_id, is_desensitized, source_url

归档流程脱敏后写入 type='公司案例' 的记录（is_desensitized=True），
embedding_id 留待 RAG 向量索引阶段回填。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class LegalReference(Base):
    """法律检索库条目。"""

    __tablename__ = "legal_references"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(32), nullable=False, index=True)   # 法条/判例/公司案例/公众号
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String(128), nullable=True)        # 向量库文档/集合 id（RAG 索引后回填）
    is_desensitized = Column(Boolean, default=False)
    source_url = Column(String(512), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
