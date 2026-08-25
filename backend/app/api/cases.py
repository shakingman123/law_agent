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
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.case import Case, CaseDocument
from app.models.user import User
from app.schemas.case import CaseCreate, CaseOut, CaseDocumentOut

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _save_upload(file: UploadFile, subdir: str = "") -> tuple[str, str, int]:
    """保存上传文件到 UPLOAD_DIR，返回 (file_url, file_name, file_size)。"""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    target_dir = os.path.join(settings.UPLOAD_DIR, subdir) if subdir else settings.UPLOAD_DIR
    os.makedirs(target_dir, exist_ok=True)

    # 加时间戳避免重名
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = f"{ts}_{file.filename}"
    dest = os.path.join(target_dir, safe_name)
    with open(dest, "wb") as f:
        data = file.file.read()
        f.write(data)
    url = f"/api/files/{subdir}/{safe_name}" if subdir else f"/api/files/{safe_name}"
    return url, file.filename, len(data)


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
    case = db.get(Case, case_id)
    if not case or case.owner_id != user.id:
        raise HTTPException(status_code=404, detail="案件不存在")
    return case


@router.post("/{case_id}/touch", response_model=CaseOut)
def touch_case(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新最近打开时间（点开案件时调用）。"""
    case = db.get(Case, case_id)
    if not case or case.owner_id != user.id:
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
    """上传案件资料文件。"""
    case = db.get(Case, case_id)
    if not case or case.owner_id != user.id:
        raise HTTPException(status_code=404, detail="案件不存在")

    url, name, size = _save_upload(file, subdir=f"case_{case_id}")
    doc = CaseDocument(
        case_id=case_id,
        file_name=name,
        file_url=url,
        file_type=_file_type(name),
        file_size=size,
        uploaded_by=user.id,
    )
    db.add(doc)
    # 更新案件更新时间
    case.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(doc)
    return doc
