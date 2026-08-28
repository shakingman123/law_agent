"""管理员申请 ORM：用户申请成为某公司管理员，由平台开发者审批。

公司可能尚不存在于平台（此时仅记录 company_name，审批通过时由开发者创建公司）。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class AdminRequest(Base):
    __tablename__ = "admin_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # 申请管理的公司名（公司可能尚未在平台注册）
    company_name = Column(String(128), nullable=False, index=True)
    # 对应的公司 id（公司已存在则填其 id；批准创建新公司后回填）
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    # pending / approved / rejected
    status = Column(String(16), default="pending", index=True)
    reason = Column(String(512), nullable=True)
    # 营业执照 / 法人授权书文件 URL（/api/files/...）
    business_license_url = Column(String(512), nullable=True)
    legal_person_auth_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
