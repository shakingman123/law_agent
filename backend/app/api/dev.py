"""平台开发者控制台接口：查看公司/管理员/管理员申请，并审批。

- GET  /api/dev/overview                      公司列表（含管理员联系方式）+ 管理员申请列表
- POST /api/dev/admin-requests/{id}/approve   批准申请（必要时创建公司）
- POST /api/dev/admin-requests/{id}/reject    驳回申请
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.api.auth import _gen_invite_code
from app.models.admin_request import AdminRequest
from app.models.user import Company, User

router = APIRouter(prefix="/api/dev", tags=["dev"])


# ---------------- Schema ----------------
class DevCompanyItem(BaseModel):
    id: int
    name: str
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_phone: Optional[str] = None
    member_count: int = 0


class DevAdminRequestItem(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_email: str
    company_name: str
    status: str  # pending / approved / rejected
    reason: Optional[str] = None
    business_license_url: Optional[str] = None
    legal_person_auth_url: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class DevOverview(BaseModel):
    companies: List[DevCompanyItem]
    admin_requests: List[DevAdminRequestItem]


# ---------------- 辅助 ----------------
def _require_developer(user: User) -> User:
    if not user.is_developer:
        raise HTTPException(status_code=403, detail="仅平台开发者可执行此操作")
    return user


# ---------------- 路由 ----------------
@router.get("/overview", response_model=DevOverview)
def dev_overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """公司列表（含管理员姓名/邮箱/电话）+ 全部管理员申请（pending 优先）。"""
    _require_developer(user)

    companies: list[DevCompanyItem] = []
    for c in db.query(Company).order_by(Company.id).all():
        admin = db.get(User, c.admin_id) if c.admin_id else None
        companies.append(
            DevCompanyItem(
                id=c.id,
                name=c.name,
                admin_name=admin.name if admin else None,
                admin_email=admin.email if admin else None,
                admin_phone=admin.phone if admin else None,
                member_count=len(c.members),
            )
        )

    reqs = db.query(AdminRequest).order_by(AdminRequest.status, AdminRequest.id.desc()).all()
    items = []
    for r in reqs:
        applicant = db.get(User, r.user_id)
        items.append(
            DevAdminRequestItem(
                id=r.id,
                user_id=r.user_id,
                user_name=applicant.name if applicant else "未知",
                user_email=applicant.email if applicant else "",
                company_name=r.company_name,
                status=r.status,
                reason=r.reason,
                business_license_url=r.business_license_url,
                legal_person_auth_url=r.legal_person_auth_url,
                created_at=r.created_at,
                reviewed_at=r.reviewed_at,
            )
        )
    return DevOverview(companies=companies, admin_requests=items)


@router.post("/admin-requests/{req_id}/approve", response_model=DevAdminRequestItem)
def approve_admin_request(
    req_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批准管理员申请：公司不存在则创建；将申请人设为该公司管理员。"""
    _require_developer(user)

    req = db.get(AdminRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")

    applicant = db.get(User, req.user_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="申请用户不存在")
    if applicant.is_admin:
        raise HTTPException(status_code=400, detail="该用户已是其他公司管理员")

    company = db.query(Company).filter(Company.name == req.company_name).first()
    if company is None:
        # 平台上不存在 → 开发者确认资料后创建公司
        company = Company(
            name=req.company_name,
            admin_id=applicant.id,
            invite_code=_gen_invite_code(),
        )
        db.add(company)
        db.flush()
    elif company.admin_id is not None:
        raise HTTPException(status_code=400, detail="该公司已有管理员，无法重复批准")

    company.admin_id = applicant.id
    applicant.is_admin = True
    applicant.company_id = company.id

    req.status = "approved"
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by = user.id
    if req.company_id is None:
        req.company_id = company.id
    db.commit()

    return DevAdminRequestItem(
        id=req.id,
        user_id=req.user_id,
        user_name=applicant.name,
        user_email=applicant.email,
        company_name=req.company_name,
        status=req.status,
        reason=req.reason,
        business_license_url=req.business_license_url,
        legal_person_auth_url=req.legal_person_auth_url,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
    )


@router.post("/admin-requests/{req_id}/reject", response_model=DevAdminRequestItem)
def reject_admin_request(
    req_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """驳回管理员申请（资料不完整或不符）。"""
    _require_developer(user)

    req = db.get(AdminRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")

    req.status = "rejected"
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by = user.id
    db.commit()

    applicant = db.get(User, req.user_id)
    return DevAdminRequestItem(
        id=req.id,
        user_id=req.user_id,
        user_name=applicant.name if applicant else "未知",
        user_email=applicant.email if applicant else "",
        company_name=req.company_name,
        status=req.status,
        reason=req.reason,
        business_license_url=req.business_license_url,
        legal_person_auth_url=req.legal_person_auth_url,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
    )
