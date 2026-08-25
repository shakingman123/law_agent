"""文书模板 Pydantic 模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TemplateOut(BaseModel):
    id: int
    name: str
    doc_type: str
    content: str
    placeholders: list[str] = []
    scope: str
    user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TemplateCreate(BaseModel):
    name: str
    doc_type: str
    content: str
    placeholders: list[str] = []
    scope: str = "private"
