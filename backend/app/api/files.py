"""文件上传与访问接口。

- POST /api/files/upload         通用文件上传（对话框附件用）
- GET  /api/files/preview-text  提取 docx/pdf 文本（前端预览用）
- GET  /api/files/{path}         访问已上传文件（inline 预览 / 下载）

底层通过 StorageService 统一管理（MinIO 优先 + 本地回退）。
"""
import io
import os
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.core.deps import get_current_user
from app.core.storage import storage, make_safe_name

router = APIRouter(prefix="/api/files", tags=["files"])


def _safe_path(rest: str) -> str:
    """统一的路径安全校验：防目录穿越。"""
    if ".." in rest or rest.startswith("/"):
        raise HTTPException(status_code=400, detail="非法路径")
    return rest


def _extract_text_from_bytes(raw: bytes, filename: str) -> str:
    """从文件字节提取文本，仅支持 docx（python-docx）和 pdf（PyMuPDF）。"""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")

    if ext == "docx":
        try:
            from docx import Document
            doc = Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"docx 解析失败: {e}")

    if ext == "pdf":
        try:
            import fitz  # PyMuPDF
            text_parts: list[str] = []
            with fitz.open(stream=raw, filetype="pdf") as doc:
                for page in doc:
                    text_parts.append(page.get_text())
            return "\n".join(text_parts)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"PDF 解析失败: {e}")

    # 其他格式（doc、图片、视频、txt 等）不支持文本提取
    raise HTTPException(
        status_code=400,
        detail=f"不支持文本预览的文件类型: .{ext}",
    )


# ---------------------------------------------------------------------------
# 以下路由需放在 /{rest:path} 之前，否则会被 path 参数吃掉
# ---------------------------------------------------------------------------


@router.get("/preview-text")
def preview_text(
    path: str = Query(..., description="文件相对路径，如 case_8/判决书.docx"),
    user=Depends(get_current_user),
) -> dict:
    """提取 docx / pdf 的纯文本，用于前端弹窗预览。

    返回结构::

        {
            "text": "...完整文本...",
            "file_type": "docx",
            "max_excerpt": false
        }

    不支持的格式（doc、图片、视频）返回 400。
    """
    _safe_path(path)
    url = f"/api/files/{path}"
    raw = storage.download(url)
    text = _extract_text_from_bytes(raw, path)
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {
        "text": text,
        "file_type": ext,
        "max_excerpt": len(text) > 10000,  # 超过 1 万字标记一下（前端可提示）
    }


# ---------------------------------------------------------------------------
# 通用路由
# ---------------------------------------------------------------------------


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


@router.get("/{rest:path}", response_model=None)
def serve_file(rest: str) -> StreamingResponse | FileResponse:
    """访问已上传文件（支持子路径，如 case_1/xxx.pdf）。

    返回 inline Content-Disposition + 正确的 Content-Type，
    浏览器可直接内联预览 PDF / 图片 / 视频。
    """
    _safe_path(rest)
    url = f"/api/files/{rest}"
    return storage.serve_file_response(url)
