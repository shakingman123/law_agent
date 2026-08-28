"""认证路由：注册 / 登录 / 当前用户 / 管理员申请。"""
import secrets
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.admin_request import AdminRequest
from app.models.user import Company, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------- 内联 Schema ----------------
class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "员工"
    # 注册时不涉及公司，公司在设置页中加入或申请成为管理员

    @field_validator("password")
    @classmethod
    def password_max_72_bytes(cls, v: str) -> str:
        # bcrypt 上限 72 字节（UTF-8 汉字每字 3 字节）；明确拒绝而非静默截断
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码过长：最多 72 字节（约 24 个汉字或 72 个英文字符）")
        return v


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
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_admin: bool
    is_developer: bool = False
    llm_source: str


class ProfileUpdateIn(BaseModel):
    """基本信息修改：姓名/手机号可改，邮箱、职级不可改。"""
    name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None


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
    user_email: str = ""
    company_id: Optional[int] = None
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


class InviteCodeOut(BaseModel):
    """公司邀请码。"""
    company_id: int
    company_name: str
    invite_code: Optional[str] = None


class JoinRequestIn(BaseModel):
    """员工凭邀请码申请加入公司。"""
    invite_code: str


class JoinRequestOut(BaseModel):
    """员工加入公司申请记录。"""
    id: int
    user_id: int
    user_name: str
    user_email: str
    company_id: int
    company_name: str
    status: str  # pending / approved / rejected
    created_at: datetime
    reviewed_at: Optional[datetime] = None


# ---------------- 辅助 ----------------
def _gen_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _user_out(user: User, db: Session) -> UserOut:
    company_name: Optional[str] = None
    company_id = user.company_id
    if user.company_id:
        company = db.get(Company, user.company_id)
        if company:
            company_name = company.name
        else:
            # 公司记录不存在（孤儿引用），清空 company_id 避免前端显示矛盾
            company_id = None
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        company=company_name,
        company_id=company_id,
        role=user.role,
        phone=user.phone,
        avatar=user.avatar,
        is_admin=user.is_admin,
        is_developer=bool(user.is_developer),
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


@router.put("/me", response_model=UserOut)
def update_profile(
    payload: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改基本信息：姓名/手机号/头像；邮箱、职级、上级不可修改。"""
    changed = False
    if payload.name is not None and payload.name.strip():
        user.name = payload.name.strip()
        changed = True
    if payload.phone is not None:
        user.phone = payload.phone.strip() or None
        changed = True
    if payload.avatar is not None:
        user.avatar = payload.avatar or None
        changed = True
    if changed:
        db.commit()
        db.refresh(user)
    return _user_out(user, db)


# ---------------- 管理员申请（数据库存储，由平台开发者审批） ----------------
def _admin_request_out(req: AdminRequest, db: Session) -> AdminRequestOut:
    applicant = db.get(User, req.user_id)
    company = db.get(Company, req.company_id) if req.company_id else None
    return AdminRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=applicant.name if applicant else "未知",
        user_email=applicant.email if applicant else "",
        company_id=req.company_id,
        company_name=req.company_name,
        status=req.status,
        reason=req.reason,
        business_license_url=req.business_license_url,
        legal_person_auth_url=req.legal_person_auth_url,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
        reviewed_by=req.reviewed_by,
    )


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
    """申请成为公司管理员。需上传营业执照和法人授权书，由平台开发者审批。

    条件：
    - 用户非管理员；公司可以不存在（审批通过时由开发者创建）
    - 若公司存在则必须尚无管理员
    - 无重复 pending 申请
    """
    if user.is_admin:
        raise HTTPException(status_code=400, detail="您已是管理员")

    if not payload.business_license_url or not payload.legal_person_auth_url:
        raise HTTPException(
            status_code=400,
            detail="需上传营业执照和法人授权签字文件",
        )

    company = db.query(Company).filter(Company.name == payload.company_name).first()
    if company and company.admin_id is not None:
        admin = db.get(User, company.admin_id)
        admin_name = admin.name if admin else "未知"
        raise HTTPException(
            status_code=400,
            detail=f"公司「{payload.company_name}」已有管理员（{admin_name}），无需申请",
        )

    dup = (
        db.query(AdminRequest)
        .filter(
            AdminRequest.user_id == user.id,
            AdminRequest.company_name == payload.company_name,
            AdminRequest.status == "pending",
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail="已有待审核的管理员申请")

    req = AdminRequest(
        user_id=user.id,
        company_name=payload.company_name,
        status="pending",
        reason=payload.reason,
        business_license_url=payload.business_license_url,
        legal_person_auth_url=payload.legal_person_auth_url,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return _admin_request_out(req, db)


@router.get("/admin-request", response_model=Optional[AdminRequestOut])
def get_my_admin_request(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前用户的最新管理员申请状态。"""
    req = (
        db.query(AdminRequest)
        .filter(AdminRequest.user_id == user.id)
        .order_by(AdminRequest.id.desc())
        .first()
    )
    return _admin_request_out(req, db) if req else None


# ---------------- 邀请码 / 员工加入 ----------------
# 员工加入申请的内存存储（后续可迁移到数据库表）
_join_requests: list[dict] = []
_join_req_counter = {"n": 0}


def _require_company_admin(user: User, db: Session) -> Company:
    """校验当前用户是某公司的管理员，返回该公司。"""
    if not user.is_admin or not user.company_id:
        raise HTTPException(status_code=403, detail="仅公司管理员可执行此操作")
    company = db.get(Company, user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="公司不存在")
    if company.admin_id != user.id:
        raise HTTPException(status_code=403, detail="仅公司管理员可执行此操作")
    return company


@router.get("/company/invite-code", response_model=InviteCodeOut)
def get_company_invite_code(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员获取本公司的当前邀请码（若不存在则自动生成）。"""
    company = _require_company_admin(user, db)
    if not company.invite_code:
        company.invite_code = _gen_invite_code()
        db.commit()
    return InviteCodeOut(
        company_id=company.id,
        company_name=company.name,
        invite_code=company.invite_code,
    )


@router.post("/company/invite-code/regenerate", response_model=InviteCodeOut)
def regenerate_company_invite_code(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员重新生成邀请码（旧码立即失效）。"""
    company = _require_company_admin(user, db)
    company.invite_code = _gen_invite_code()
    db.commit()
    return InviteCodeOut(
        company_id=company.id,
        company_name=company.name,
        invite_code=company.invite_code,
    )


@router.post("/company/join", response_model=JoinRequestOut)
def apply_join_company(
    payload: JoinRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """员工凭邀请码申请加入公司，等待管理员审批。

    条件：
    - 邀请码能匹配到某公司
    - 用户非管理员
    - 无重复 pending 申请
    """
    if user.is_admin:
        raise HTTPException(status_code=400, detail="管理员无需申请加入公司")

    company = (
        db.query(Company).filter(Company.invite_code == payload.invite_code).first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="邀请码无效或已失效")

    # 已在同公司则无需重复申请
    if user.company_id == company.id:
        raise HTTPException(status_code=400, detail="您已加入该公司")

    # 查重：同一用户对同一公司已有 pending 申请
    for r in _join_requests:
        if (
            r["user_id"] == user.id
            and r["company_id"] == company.id
            and r["status"] == "pending"
        ):
            raise HTTPException(status_code=400, detail="已有待审批的加入申请")

    _join_req_counter["n"] += 1
    req = {
        "id": _join_req_counter["n"],
        "user_id": user.id,
        "user_name": user.name,
        "user_email": user.email,
        "company_id": company.id,
        "company_name": company.name,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "reviewed_at": None,
    }
    _join_requests.append(req)
    return JoinRequestOut(**req)


@router.get("/company/join-requests", response_model=list[JoinRequestOut])
def list_company_join_requests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员查询本公司的待审批加入申请列表。"""
    company = _require_company_admin(user, db)
    return [
        JoinRequestOut(**r)
        for r in _join_requests
        if r["company_id"] == company.id
    ]


@router.post("/company/join-requests/{req_id}/approve", response_model=JoinRequestOut)
def approve_join_request(
    req_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员批准员工加入申请，将员工加入公司。"""
    company = _require_company_admin(user, db)
    req = next((r for r in _join_requests if r["id"] == req_id), None)
    if not req:
        raise HTTPException(status_code=404, detail="加入申请不存在")
    if req["company_id"] != company.id:
        raise HTTPException(status_code=403, detail="无权审批该公司申请")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")

    applicant = db.get(User, req["user_id"])
    if not applicant:
        raise HTTPException(status_code=404, detail="申请用户不存在")
    # 若员工已在其他公司，批准后将转移至本公司
    applicant.company_id = company.id
    applicant.is_admin = False
    req["status"] = "approved"
    req["reviewed_at"] = datetime.utcnow()
    db.commit()
    return JoinRequestOut(**req)


@router.post("/company/join-requests/{req_id}/reject", response_model=JoinRequestOut)
def reject_join_request(
    req_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员拒绝员工加入申请。"""
    company = _require_company_admin(user, db)
    req = next((r for r in _join_requests if r["id"] == req_id), None)
    if not req:
        raise HTTPException(status_code=404, detail="加入申请不存在")
    if req["company_id"] != company.id:
        raise HTTPException(status_code=403, detail="无权审批该公司申请")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")

    req["status"] = "rejected"
    req["reviewed_at"] = datetime.utcnow()
    return JoinRequestOut(**req)
