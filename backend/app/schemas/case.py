"""案件相关 Pydantic 模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CaseCreate(BaseModel):
    """新建案件（名称/原告/被告/管辖法院 必填）。"""

    name: str
    plaintiff: str
    defendant: str
    court: str
    summary: Optional[str] = ""
    scope: str = "private"


class CaseOut(BaseModel):
    id: int
    name: str
    plaintiff: str
    defendant: str
    court: str
    summary: Optional[str] = ""
    scope: str
    owner_id: int
    company_id: Optional[int] = None
    last_opened_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    documents: list["CaseDocumentOut"] = []

    class Config:
        from_attributes = True


class CaseDocumentOut(BaseModel):
    id: int
    case_id: int
    file_name: str
    file_url: str
    file_type: Optional[str] = None
    file_size: int = 0
    uploaded_by: int
    created_at: datetime

    class Config:
        from_attributes = True


CaseOut.model_rebuild()


class DocCaseItem(BaseModel):
    """文档库案件卡片所需的精简结构（含文件类型聚合）。"""

    id: int
    title: str
    updatedAt: str
    scope: str  # private / public / locked
    fileTypes: list[str] = []
