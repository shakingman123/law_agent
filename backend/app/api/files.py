"""文件上传与访问接口。

- POST /api/files/upload   通用文件上传（对话框附件用）
- GET  /api/files/{path}    访问已上传文件

底层通过 StorageService 统一管理（MinIO 优先 + 本地回退）。
"""
import os

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse

from app.core.deps import get_current_user
from app.core.storage import storage, make_safe_name

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """通用文件上传，返回访问 URL 与文件信息。"""
    raw = file.file.read()
    object_name, _safe = make_safe_name(file.filename)
    url, size = storage.upload_plain(raw, object_name)
    return {
        "url": url,
        "file_name": file.filename,
        "file_size": size,
        "file_type": os.path.splitext(file.filename)[1].lower().lstrip("."),
    }


@router.get("/{rest:path}")
def serve_file(rest: str) -> StreamingResponse | FileResponse:
    """访问已上传文件（支持子路径，如 case_1/xxx.pdf）。

    防目录穿越：禁止 .. 和绝对路径。
    """
    if ".." in rest or rest.startswith("/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="非法路径")
    url = f"/api/files/{rest}"
    return storage.serve_file_response(url)
