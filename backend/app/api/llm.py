"""LLM 路由：公司/个人 API 配置、访问申请审批、用量统计、额度控制。

对应前端 stores/llmStore.ts 的全部操作。所有写接口中 API Key 明文入参、
落库前 AES(Fernet) 加密；所有读接口仅返回掩码（sk-••••f2a）。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_admin_user, get_current_user, get_db
from app.core.security import decrypt_api_key, encrypt_api_key, mask_api_key
from app.models.llm import (
    CompanyLlmConfig,
    LlmAccessRequest,
    LlmQuota,
    LlmUsageRecord,
    UserLlmConfig,
)
from app.models.user import User
from app.schemas.llm import (
    AccessRequestCreate,
    AccessRequestOut,
    AccessRequestReview,
    CompanyLlmConfigIn,
    CompanyLlmConfigOut,
    CompanyLlmConfigPublic,
    LlmSourceIn,
    LlmSourceOut,
    MyUsageOut,
    PersonalLlmConfigIn,
    PersonalLlmConfigOut,
    QuotaOut,
    QuotaUpdate,
    UsageRecordOut,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])


# ---------------- 辅助函数 ----------------
def _current_period() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _company_config_out(cfg: CompanyLlmConfig) -> CompanyLlmConfigOut:
    return CompanyLlmConfigOut(
        is_active=cfg.is_active,
        provider=cfg.provider,
        base_url=cfg.base_url or "",
        api_key_masked=mask_api_key(decrypt_api_key(cfg.api_key_enc or "")),
        models=cfg.models or [],
        monthly_budget=cfg.monthly_budget or 0.0,
    )


def _personal_config_out(cfg: Optional[UserLlmConfig]) -> PersonalLlmConfigOut:
    if not cfg:
        return PersonalLlmConfigOut(
            is_active=False,
            provider="deepseek",
            base_url="",
            api_key_masked="",
            models=[],
        )
    return PersonalLlmConfigOut(
        is_active=cfg.is_active,
        provider=cfg.provider,
        base_url=cfg.base_url or "",
        api_key_masked=mask_api_key(decrypt_api_key(cfg.api_key_enc or "")),
        models=cfg.models or [],
    )


def _access_request_out(req: LlmAccessRequest, db: Session) -> AccessRequestOut:
    user = db.get(User, req.user_id)
    return AccessRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=user.name if user else f"user#{req.user_id}",
        company_id=req.company_id,
        status=req.status,
        reason=req.reason,
        created_at=req.created_at,
        reviewed_by=req.reviewed_by,
        reviewed_at=req.reviewed_at,
    )


# ---------------- 公司配置 ----------------
@router.get("/config/company")
def get_company_config(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取公司 LLM 配置。管理员看完整字段，员工只看启用状态与掩码。"""
    if not user.company_id:
        raise HTTPException(status_code=404, detail="当前用户未加入公司")
    cfg = (
        db.query(CompanyLlmConfig)
        .filter(CompanyLlmConfig.company_id == user.company_id)
        .first()
    )
    if not cfg:
        raise HTTPException(status_code=404, detail="公司尚未配置 LLM")
    masked = mask_api_key(decrypt_api_key(cfg.api_key_enc or ""))
    if user.is_admin:
        return _company_config_out(cfg)
    return CompanyLlmConfigPublic(
        is_active=cfg.is_active,
        api_key_masked=masked,
        provider=cfg.provider,
        models=cfg.models or [],
    )


@router.put("/config/company", response_model=CompanyLlmConfigOut)
def put_company_config(
    payload: CompanyLlmConfigIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """管理员保存公司 LLM 配置（API Key AES 加密落库，返回掩码）。"""
    if not admin.company_id:
        raise HTTPException(status_code=400, detail="管理员未关联公司")
    cfg = (
        db.query(CompanyLlmConfig)
        .filter(CompanyLlmConfig.company_id == admin.company_id)
        .first()
    )
    if not cfg:
        cfg = CompanyLlmConfig(company_id=admin.company_id)
        db.add(cfg)
    cfg.provider = payload.provider
    cfg.base_url = payload.base_url
    cfg.models = payload.models
    cfg.monthly_budget = payload.monthly_budget
    cfg.is_active = payload.is_active
    if payload.api_key:
        cfg.api_key_enc = encrypt_api_key(payload.api_key)
    db.commit()
    db.refresh(cfg)
    return _company_config_out(cfg)


# ---------------- 个人配置 ----------------
@router.get("/config/me", response_model=PersonalLlmConfigOut)
def get_personal_config(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取本人个人 LLM 配置（仅本人，Key 掩码）。"""
    cfg = (
        db.query(UserLlmConfig)
        .filter(UserLlmConfig.user_id == user.id)
        .first()
    )
    return _personal_config_out(cfg)


@router.put("/config/me", response_model=PersonalLlmConfigOut)
def put_personal_config(
    payload: PersonalLlmConfigIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存个人 LLM 配置（API Key AES 加密落库，返回掩码）。"""
    cfg = (
        db.query(UserLlmConfig)
        .filter(UserLlmConfig.user_id == user.id)
        .first()
    )
    if not cfg:
        cfg = UserLlmConfig(user_id=user.id)
        db.add(cfg)
    cfg.provider = payload.provider
    cfg.base_url = payload.base_url
    cfg.models = payload.models
    cfg.is_active = payload.is_active
    if payload.api_key:
        cfg.api_key_enc = encrypt_api_key(payload.api_key)
    db.commit()
    db.refresh(cfg)
    return _personal_config_out(cfg)


# ---------------- 使用方式切换 ----------------
@router.get("/source", response_model=LlmSourceOut)
def get_source(user: User = Depends(get_current_user)):
    return LlmSourceOut(source=user.llm_source or "company")


@router.put("/source", response_model=LlmSourceOut)
def set_source(
    payload: LlmSourceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """切换使用方式。切换到 company 需管理员身份或已审批通过的访问申请。"""
    if payload.source == "company" and not user.is_admin:
        approved = (
            db.query(LlmAccessRequest)
            .filter(
                LlmAccessRequest.user_id == user.id,
                LlmAccessRequest.company_id == user.company_id,
                LlmAccessRequest.status == "approved",
            )
            .first()
        )
        if not approved:
            raise HTTPException(
                status_code=403,
                detail="未获得公司 API 使用授权，请先提交申请",
            )
    user.llm_source = payload.source
    db.commit()
    db.refresh(user)
    return LlmSourceOut(source=user.llm_source)


# ---------------- 公司 API 访问申请 ----------------
@router.post("/access-request", response_model=AccessRequestOut)
def create_access_request(
    payload: AccessRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """员工申请使用公司 API。"""
    if not user.company_id:
        raise HTTPException(status_code=400, detail="未加入公司，无法申请")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="管理员无需申请")
    existing = (
        db.query(LlmAccessRequest)
        .filter(
            LlmAccessRequest.user_id == user.id,
            LlmAccessRequest.status == "pending",
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="已有待审批的申请")
    req = LlmAccessRequest(
        user_id=user.id,
        company_id=user.company_id,
        status="pending",
        reason=payload.reason,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return _access_request_out(req, db)


@router.get("/access-request/me", response_model=Optional[AccessRequestOut])
def get_my_access_request(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前员工在本公司最近一次公司 API 使用申请（无申请返回 null）。"""
    if not user.company_id:
        return None
    req = (
        db.query(LlmAccessRequest)
        .filter_by(user_id=user.id, company_id=user.company_id)
        .order_by(LlmAccessRequest.id.desc())
        .first()
    )
    return _access_request_out(req, db) if req else None


@router.get("/access-requests", response_model=list[AccessRequestOut])
def list_access_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """管理员查看访问申请列表（默认全部，可按 status 过滤）。"""
    if not admin.company_id:
        raise HTTPException(status_code=400, detail="管理员未关联公司")
    query = db.query(LlmAccessRequest).filter(
        LlmAccessRequest.company_id == admin.company_id
    )
    if status_filter:
        query = query.filter(LlmAccessRequest.status == status_filter)
    reqs = query.order_by(LlmAccessRequest.created_at.desc()).all()
    return [_access_request_out(r, db) for r in reqs]


@router.put("/access-requests/{req_id}", response_model=AccessRequestOut)
def review_access_request(
    req_id: int,
    payload: AccessRequestReview,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """管理员审批访问申请（approve/reject）。"""
    req = db.get(LlmAccessRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.company_id != admin.company_id:
        raise HTTPException(status_code=403, detail="无权审批此申请")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")
    req.status = "approved" if payload.action == "approve" else "rejected"
    req.reviewed_by = admin.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(req)
    return _access_request_out(req, db)


# ---------------- 用量统计 ----------------
@router.get("/usage/me", response_model=MyUsageOut)
def my_usage(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的用量统计（按 source/provider/model 聚合）。"""
    records = (
        db.query(LlmUsageRecord)
        .filter(LlmUsageRecord.user_id == user.id)
        .all()
    )
    grouped: dict[tuple, dict] = {}
    for r in records:
        key = (r.source, r.provider, r.model)
        bucket = grouped.setdefault(
            key,
            {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0},
        )
        bucket["calls"] += 1
        bucket["prompt_tokens"] += r.prompt_tokens or 0
        bucket["completion_tokens"] += r.completion_tokens or 0
        bucket["cost"] += r.cost or 0.0

    out_records = [
        UsageRecordOut(
            user_id=user.id,
            user_name=user.name,
            source=source,
            provider=provider,
            model=model,
            calls=v["calls"],
            prompt_tokens=v["prompt_tokens"],
            completion_tokens=v["completion_tokens"],
            cost=v["cost"],
            quota_limit=0.0,
        )
        for (source, provider, model), v in grouped.items()
    ]
    totals = {
        "calls": sum(r.calls for r in out_records),
        "prompt_tokens": sum(r.prompt_tokens for r in out_records),
        "completion_tokens": sum(r.completion_tokens for r in out_records),
        "cost": sum(r.cost for r in out_records),
    }

    quota: Optional[dict] = None
    if user.company_id:
        q = (
            db.query(LlmQuota)
            .filter(
                LlmQuota.user_id == user.id,
                LlmQuota.company_id == user.company_id,
                LlmQuota.period == _current_period(),
            )
            .first()
        )
        if q:
            quota = {
                "period": q.period,
                "quota_limit": q.quota_limit,
                "used": q.used,
                "status": q.status,
            }
    return MyUsageOut(records=out_records, totals=totals, quota=quota)


@router.get("/usage/company", response_model=list[UsageRecordOut])
def company_usage(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """管理员查看全员用量明细（按 用户/source/provider/model 聚合）。"""
    if not admin.company_id:
        raise HTTPException(status_code=400, detail="管理员未关联公司")

    # 公司全部成员
    member_rows = (
        db.query(User.id, User.name)
        .filter(User.company_id == admin.company_id)
        .all()
    )
    user_map = {row[0]: row[1] for row in member_rows}
    member_ids = list(user_map.keys())
    if not member_ids:
        return []

    records = (
        db.query(LlmUsageRecord)
        .filter(LlmUsageRecord.user_id.in_(member_ids))
        .all()
    )

    grouped: dict[tuple, dict] = {}
    for r in records:
        key = (r.user_id, r.source, r.provider, r.model)
        bucket = grouped.setdefault(
            key,
            {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0},
        )
        bucket["calls"] += 1
        bucket["prompt_tokens"] += r.prompt_tokens or 0
        bucket["completion_tokens"] += r.completion_tokens or 0
        bucket["cost"] += r.cost or 0.0

    quota_rows = (
        db.query(LlmQuota)
        .filter(
            LlmQuota.company_id == admin.company_id,
            LlmQuota.period == _current_period(),
        )
        .all()
    )
    quota_map = {q.user_id: q.quota_limit for q in quota_rows}

    return [
        UsageRecordOut(
            user_id=uid,
            user_name=user_map.get(uid, str(uid)),
            source=source,
            provider=provider,
            model=model,
            calls=v["calls"],
            prompt_tokens=v["prompt_tokens"],
            completion_tokens=v["completion_tokens"],
            cost=v["cost"],
            quota_limit=quota_map.get(uid, 0.0),
        )
        for (uid, source, provider, model), v in grouped.items()
    ]


# ---------------- 额度 ----------------
@router.put("/quotas/{user_id}", response_model=QuotaOut)
def set_quota(
    user_id: int,
    payload: QuotaUpdate,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """管理员设置员工月度额度（当前年月，不存在则新建）。"""
    if not admin.company_id:
        raise HTTPException(status_code=400, detail="管理员未关联公司")
    target = db.get(User, user_id)
    if not target or target.company_id != admin.company_id:
        raise HTTPException(status_code=404, detail="员工不存在或不属于本公司")

    period = _current_period()
    q = (
        db.query(LlmQuota)
        .filter(
            LlmQuota.user_id == user_id,
            LlmQuota.company_id == admin.company_id,
            LlmQuota.period == period,
        )
        .first()
    )
    if not q:
        q = LlmQuota(
            user_id=user_id,
            company_id=admin.company_id,
            period=period,
            quota_limit=payload.quota_limit,
            used=0.0,
            status="active",
        )
        db.add(q)
    else:
        q.quota_limit = payload.quota_limit
    db.commit()
    db.refresh(q)
    return QuotaOut(
        user_id=q.user_id,
        company_id=q.company_id,
        period=q.period,
        quota_limit=q.quota_limit,
        used=q.used,
        status=q.status,
    )
