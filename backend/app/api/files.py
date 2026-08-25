"""文件上传与访问接口。

- POST /api/files/upload   通用文件上传（对话框附件用）
- GET  /api/files/{path}    访问已上传文件
"""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.deps import get_current_user

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """通用文件上传，返回访问 URL 与文件信息。"""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = f"{ts}_{file.filename}"
    dest = os.path.join(settings.UPLOAD_DIR, safe_name)
    with open(dest, "wb") as f:
        data = file.file.read()
        f.write(data)
    return {
        "url": f"/api/files/{safe_name}",
        "file_name": file.filename,
        "file_size": len(data),
        "file_type": os.path.splitext(file.filename)[1].lower().lstrip("."),
    }


@router.get("/{rest:path}")
def serve_file(rest: str):
    """访问已上传文件（支持子路径，如 case_1/xxx.pdf）。"""
    # 防目录穿越
    if ".." in rest or rest.startswith("/"):
        raise HTTPException(status_code=400, detail="非法路径")
    full = os.path.join(settings.UPLOAD_DIR, rest)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(full)
