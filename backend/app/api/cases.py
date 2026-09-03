"""案件接口：增删改查 + 资料上传。

依据 docs/implementation-guide.md §2：
- POST /api/cases            新建案件（名称/原告/被告/管辖法院 必填）
- GET  /api/cases/recent     最近 1 周打开的案件
- GET  /api/cases            全部案件（文档库用，含文档类型聚合）
- GET  /api/cases/{id}       案件详情
- POST /api/cases/{id}/documents  上传案件资料
- POST /api/cases/{id}/touch      更新最近打开时间
"""
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user, get_db
from app.core.storage import storage, make_safe_name
from app.models.case import Case, CaseDocument
from app.models.user import User
from app.schemas.case import CaseCreate, CaseOut, CaseDocumentOut

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext in ("docx", "doc"):
        return "docx"
    if ext == "pdf":
        return "pdf"
    if ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp"):
        return "image"
    if ext in ("mp4", "mov", "avi", "mkv"):
        return "video"
    return ext or "file"


@router.post("", response_model=CaseOut)
def create_case(
    payload: CaseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建案件。同一用户下案件名称不可重复。"""
    # 名称唯一性检查（按 owner_id + name）
    existing = (
        db.query(Case)
        .filter(Case.owner_id == user.id, Case.name == payload.name.strip())
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"案件名称「{payload.name}」已存在，请使用其他名称")

    case = Case(
        name=payload.name.strip(),
        plaintiff=payload.plaintiff,
        defendant=payload.defendant,
        court=payload.court,
        summary=payload.summary or "",
        scope=payload.scope,
        owner_id=user.id,
        company_id=user.company_id,
        last_opened_at=datetime.utcnow(),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("/recent", response_model=list[CaseOut])
def recent_cases(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """最近 1 周打开的案件（按最近打开倒序）。"""
    week_ago = datetime.utcnow() - timedelta(days=7)
    cases = (
        db.query(Case)
        .options(joinedload(Case.documents))
        .filter(Case.owner_id == user.id, Case.last_opened_at >= week_ago)
        .order_by(Case.last_opened_at.desc())
        .all()
    )
    return cases


@router.get("", response_model=list[CaseOut])
def list_cases(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """全部案件（文档库用，含文档类型聚合）。"""
    cases = (
        db.query(Case)
        .options(joinedload(Case.documents))
        .filter(Case.owner_id == user.id)
        .order_by(Case.updated_at.desc())
        .all()
    )
    return cases


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = (
        db.query(Case)
        .options(joinedload(Case.documents))
        .filter(Case.id == case_id, Case.owner_id == user.id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    return case


@router.post("/{case_id}/touch", response_model=CaseOut)
def touch_case(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新最近打开时间（点开案件时调用）。"""
    case = (
        db.query(Case)
        .options(joinedload(Case.documents))
        .filter(Case.id == case_id, Case.owner_id == user.id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    case.last_opened_at = datetime.utcnow()
    db.commit()
    db.refresh(case)
    return case


@router.post("/{case_id}/documents", response_model=CaseDocumentOut)
def upload_case_document(
    case_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传案件资料文件（通过 StorageService，MinIO 优先 / 本地回退）。"""
    case = db.get(Case, case_id)
    if not case or case.owner_id != user.id:
        raise HTTPException(status_code=404, detail="案件不存在")

    raw = file.file.read()
    object_name, _safe = make_safe_name(file.filename, subdir=f"case_{case_id}")
    url, size = storage.upload_plain(raw, object_name)
    doc = CaseDocument(
        case_id=case_id,
        file_name=file.filename,
        file_url=url,
        file_type=_file_type(file.filename),
        file_size=size,
        uploaded_by=user.id,
    )
    db.add(doc)
    # 更新案件更新时间
    case.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(doc)
    return doc
