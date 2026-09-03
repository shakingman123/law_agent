"""案件与案件文档 ORM。

依据 docs/implementation-guide.md §2：
- cases          案件主表（名称/原告/被告/管辖法院/基本情况，owner 维护）
- case_documents 案件资料文档（上传的文件）
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class Case(Base):
    """案件。scope：private 私库 / public 公库协作。同一用户下名称唯一。"""

    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_case_owner_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    plaintiff = Column(String(128), nullable=False)          # 原告
    defendant = Column(String(128), nullable=False)         # 被告
    court = Column(String(128), nullable=False)             # 管辖法院
    summary = Column(Text, nullable=True)                   # 案件基本情况
    scope = Column(String(16), default="private")            # private / public
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    last_opened_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship("CaseDocument", back_populates="case", cascade="all, delete-orphan")


class CaseDocument(Base):
    """案件资料文档（上传的文件）。"""

    __tablename__ = "case_documents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    file_name = Column(String(256), nullable=False)
    file_url = Column(String(512), nullable=False)
    file_type = Column(String(32), nullable=True)            # docx/pdf/image/video/...
    file_size = Column(Integer, default=0)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="documents")
