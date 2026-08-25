"""LLM 相关 ORM。

依据 docs/project-framework.md §4 的 4 张 LLM 表：
- company_llm_configs 公司共享 LLM 配置
- user_llm_configs    员工个人 LLM 配置
- llm_usage_records   每次 LLM 调用用量明细
- llm_quotas          员工月度额度

另增 llm_access_requests：员工申请使用公司 API 的审批流（路由需要）。
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.core.database import Base


class CompanyLlmConfig(Base):
    __tablename__ = "company_llm_configs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="openai")
    base_url = Column(String(512), nullable=True)
    # AES(Fernet) 加密后的 API Key
    api_key_enc = Column(Text, nullable=True)
    # 可用模型列表（JSON 数组）
    models = Column(JSON, default=list)
    monthly_budget = Column(Float, default=0.0)
    is_active = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserLlmConfig(Base):
    __tablename__ = "user_llm_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="deepseek")
    base_url = Column(String(512), nullable=True)
    api_key_enc = Column(Text, nullable=True)
    models = Column(JSON, default=list)
    is_active = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LlmUsageRecord(Base):
    __tablename__ = "llm_usage_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    # company / personal
    source = Column(String(16), nullable=False)
    provider = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class LlmQuota(Base):
    __tablename__ = "llm_quotas"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # 年月，格式 YYYY-MM
    period = Column(String(7), nullable=False)
    quota_limit = Column(Float, default=0.0)
    used = Column(Float, default=0.0)
    # active / exceeded / frozen
    status = Column(String(16), default="active")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LlmAccessRequest(Base):
    """员工申请使用公司 API 的审批记录。"""

    __tablename__ = "llm_access_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    # pending / approved / rejected
    status = Column(String(16), default="pending")
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
