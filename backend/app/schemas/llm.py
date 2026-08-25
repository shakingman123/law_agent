"""LLM 相关 Pydantic 模型。

约定：API Key 输入用明文（字段名 api_key），输出仅回掩码（字段名 api_key_masked，
格式 sk-••••f2a）。后端永不回传明文 Key。
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Provider = Literal["openai", "azure", "qwen", "deepseek", "zhipu"]
LlmSource = Literal["company", "personal"]


# ---------------- 公司配置 ----------------
class CompanyLlmConfigIn(BaseModel):
    """管理员保存公司配置（API Key 明文入参）。"""

    is_active: bool = False
    provider: Provider = "openai"
    base_url: str = ""
    api_key: str = Field("", description="明文 API Key，落库前 AES 加密")
    models: list[str] = []
    monthly_budget: float = 0.0


class CompanyLlmConfigOut(BaseModel):
    """管理员视角：完整配置（Key 仍为掩码）。"""

    is_active: bool
    provider: Provider
    base_url: str
    api_key_masked: str
    models: list[str]
    monthly_budget: float


class CompanyLlmConfigPublic(BaseModel):
    """员工视角：仅启用状态与掩码（及 provider 上下文）。"""

    is_active: bool
    api_key_masked: str
    provider: Optional[Provider] = None


# ---------------- 个人配置 ----------------
class PersonalLlmConfigIn(BaseModel):
    is_active: bool = False
    provider: Provider = "deepseek"
    base_url: str = ""
    api_key: str = ""
    models: list[str] = []


class PersonalLlmConfigOut(BaseModel):
    is_active: bool
    provider: Provider
    base_url: str
    api_key_masked: str
    models: list[str]


# ---------------- 使用方式切换 ----------------
class LlmSourceOut(BaseModel):
    source: LlmSource


class LlmSourceIn(BaseModel):
    source: LlmSource


# ---------------- 公司 API 访问申请 ----------------
class AccessRequestCreate(BaseModel):
    reason: Optional[str] = None


class AccessRequestOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    company_id: int
    status: Literal["pending", "approved", "rejected"]
    reason: Optional[str] = None
    created_at: datetime
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None


class AccessRequestReview(BaseModel):
    action: Literal["approve", "reject"]


# ---------------- 用量统计 ----------------
class UsageRecordOut(BaseModel):
    user_id: int
    user_name: str
    source: LlmSource
    provider: Provider
    model: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost: float
    quota_limit: float


class MyUsageOut(BaseModel):
    records: list[UsageRecordOut]
    totals: dict
    quota: Optional[dict] = None


# ---------------- 额度 ----------------
class QuotaUpdate(BaseModel):
    quota_limit: float


class QuotaOut(BaseModel):
    user_id: int
    company_id: int
    period: str
    quota_limit: float
    used: float
    status: str
