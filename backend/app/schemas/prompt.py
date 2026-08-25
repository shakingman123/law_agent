"""Prompt 模板相关 Pydantic 模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PromptCreate(BaseModel):
    name: str
    category: str
    key: str
    content: str
    variables: list[str] = []


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[list[str]] = None


class PromptOut(BaseModel):
    id: int
    name: str
    category: str
    key: str
    content: str
    variables: list[str] = []
    is_system: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
