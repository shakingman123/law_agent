"""认证路由：注册 / 登录 / 当前用户 / 管理员申请。"""
import secrets
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import Company, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------- 内联 Schema ----------------
class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "员工"
    # 注册时不涉及公司，公司在设置页中加入或申请成为管理员


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    company: Optional[str] = None
    company_id: Optional[int] = None
    role: str
    avatar: Optional[str] = None
    is_admin: bool
    llm_source: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AdminRequestIn(BaseModel):
    """申请成为公司管理员。"""
    company_name: str  # 申请管理的公司名
    reason: Optional[str] = None
    # 营业执照与法人授权书的文件 URL（前端上传后获得）
    business_license_url: Optional[str] = None
    legal_person_auth_url: Optional[str] = None


class AdminRequestOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    company_id: int
    company_name: str
    status: str  # pending / approved / rejected
    reason: Optional[str] = None
    business_license_url: Optional[str] = None
    legal_person_auth_url: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[int] = None


class CompanyAdminStatus(BaseModel):
    """公司管理员状态查询结果。"""
    company_id: int
    company_name: str
    has_admin: bool
    admin_name: Optional[str] = None


# ---------------- 辅助 ----------------
def _gen_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _user_out(user: User, db: Session) -> UserOut:
    company_name: Optional[str] = None
    if user.company_id:
        company = db.get(Company, user.company_id)
        if company:
            company_name = company.name
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        company=company_name,
        company_id=user.company_id,
        role=user.role,
        avatar=user.avatar,
        is_admin=user.is_admin,
        llm_source=user.llm_source or "company",
    )


# ---------------- 路由 ----------------
@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """注册。不涉及公司，注册后在设置页中加入公司或申请成为管理员。"""
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    user = User(
        name=payload.name,
        email=payload.email,
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_admin=False,
        company_id=None,
        llm_source="company",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=_user_out(user, db))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    token = create_access_token(user.id)
    return TokenOut(access_token=token, user=_user_out(user, db))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_out(user, db)


# ---------------- 管理员申请 ----------------
# 简单的内存存储（后续可迁移到数据库表）
_admin_requests: list[dict] = []
_req_counter = {"n": 0}


@router.get("/company-admin-status", response_model=CompanyAdminStatus)
def get_company_admin_status(
    company_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询指定公司是否已有管理员。用户输入公司名后调用此接口判断。"""
    company = db.query(Company).filter(Company.name == company_name).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"公司「{company_name}」不存在")
    admin_name = None
    if company.admin_id:
        admin = db.get(User, company.admin_id)
        admin_name = admin.name if admin else None
    return CompanyAdminStatus(
        company_id=company.id,
        company_name=company.name,
        has_admin=company.admin_id is not None,
        admin_name=admin_name,
    )


@router.post("/admin-request", response_model=AdminRequestOut)
def create_admin_request(
    payload: AdminRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """申请成为公司管理员。需上传营业执照和法人授权书。

    条件：
    - 公司存在且当前无管理员
    - 用户非管理员
    - 无重复 pending 申请
    """
    if user.is_admin:
        raise HTTPException(status_code=400, detail="您已是管理员")

    company = db.query(Company).filter(Company.name == payload.company_name).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"公司「{payload.company_name}」不存在")
    if company.admin_id is not None:
        admin = db.get(User, company.admin_id)
        admin_name = admin.name if admin else "未知"
        raise HTTPException(
            status_code=400,
            detail=f"公司「{payload.company_name}」已有管理员（{admin_name}），无需申请",
        )

    if not payload.business_license_url or not payload.legal_person_auth_url:
        raise HTTPException(
            status_code=400,
            detail="需上传营业执照和法人授权签字文件",
        )

    # 查重
    for r in _admin_requests:
        if (
            r["user_id"] == user.id
            and r["company_id"] == company.id
            and r["status"] == "pending"
        ):
            raise HTTPException(status_code=400, detail="已有待审核的管理员申请")

    _req_counter["n"] += 1
    req = {
        "id": _req_counter["n"],
        "user_id": user.id,
        "user_name": user.name,
        "company_id": company.id,
        "company_name": company.name,
        "status": "pending",
        "reason": payload.reason,
        "business_license_url": payload.business_license_url,
        "legal_person_auth_url": payload.legal_person_auth_url,
        "created_at": datetime.utcnow(),
        "reviewed_at": None,
        "reviewed_by": None,
    }
    _admin_requests.append(req)
    return AdminRequestOut(**req)


@router.get("/admin-request", response_model=Optional[AdminRequestOut])
def get_my_admin_request(
    user: User = Depends(get_current_user),
):
    """查询当前用户的最新管理员申请状态。"""
    for r in reversed(_admin_requests):
        if r["user_id"] == user.id:
            return AdminRequestOut(**r)
    return None
