from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    invite_code = Column(String(64), nullable=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Company 与 User 之间有两个外键（admin_id / company_id）形成循环引用，
    # 用 primaryjoin 显式指定连接条件（SQLAlchemy 官方推荐的循环引用解法）
    members = relationship("User", back_populates="company", primaryjoin="Company.id == foreign(User.company_id)")
    admin = relationship("User", primaryjoin="Company.admin_id == User.id", post_update=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    email = Column(String(128), unique=True, nullable=False, index=True)
    phone = Column(String(32), nullable=True)
    avatar = Column(String(512), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    role = Column(String(64), default="员工")
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    # 平台开发者：可进入开发者控制台审批「成为公司管理员」申请
    is_developer = Column(Boolean, default=False)
    # 当前使用的 LLM 来源：company / personal
    llm_source = Column(String(16), default="company")
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="members", primaryjoin="User.company_id == Company.id")
