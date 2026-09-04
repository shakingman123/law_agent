"""文件上传与访问接口。

- POST /api/files/upload         通用文件上传（对话框附件用）
- GET  /api/files/preview-text  提取 docx/pdf/doc 文本（前端预览用）
- GET  /api/files/{path}         访问已上传文件（inline 预览 / 下载）

底层通过 StorageService 统一管理（MinIO 优先 + 本地回退）。
.doc 旧版 Office 格式通过 LibreOffice 转 .docx 后再用 python-docx 提取。
"""
import io
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.storage import storage, make_safe_name

logger = logging.getLogger("app.api.files")

router = APIRouter(prefix="/api/files", tags=["files"])


def _safe_path(rest: str) -> str:
    """统一的路径安全校验：防目录穿越。"""
    if ".." in rest or rest.startswith("/"):
        raise HTTPException(status_code=400, detail="非法路径")
    return rest


def _detect_real_format(raw: bytes, filename: str) -> str:
    """用 magic byte 判断文件真实格式，扩展名仅作兜底。

    为什么不直接信扩展名？Word 有保存 bug：用户选另存为 .docx，
    实际输出仍可能是 OLE 二进制。扩展名是 .docx，magic byte 却是 d0cf11e0。

    识别规则：
    - PK.......... → ZIP（真正的 .docx / .pptx / .xlsx）
    - d0cf11e0a1b11ae1 → OLE（旧版 .doc / .ppt / .xls）
    - 扩展名 .pdf → PDF（PyMuPDF 可自识别，容错）
    """
    magic = raw[:8]
    if magic[:2] == b"PK":
        return "zip"  # ZIP 容器，docx/xlsx/pptx 都是它
    if magic[:4] == b"\xd0\xcf\x11\xe0":
        return "ole"  # 旧版 Office 二进制
    if magic[:4] == b"%PDF":
        return "pdf"

    # 兜底：信扩展名
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext


_libreoffice_cache: str | None = None  # 缓存查找结果，避免每次都 shutil.which


def _find_libreoffice() -> str | None:
    """查找 LibreOffice 可执行文件，优先用配置，再查 PATH。

    返回绝对路径字符串，找不到返回 None。
    """
    global _libreoffice_cache
    if _libreoffice_cache is not None:
        return _libreoffice_cache

    # 1. 显式配置
    if settings.LIBREOFFICE_BIN:
        if os.path.isfile(settings.LIBREOFFICE_BIN):
            _libreoffice_cache = settings.LIBREOFFICE_BIN
            logger.info("[preview-text] LibreOffice 已配置: %s", _libreoffice_cache)
            return _libreoffice_cache
        logger.warning(
            "[preview-text] LIBREOFFICE_BIN 指向的文件不存在: %s，改为自动查找",
            settings.LIBREOFFICE_BIN,
        )

    # 2. PATH 查找
    for candidate in ("soffice", "libreoffice"):
        found = shutil.which(candidate)
        if found:
            _libreoffice_cache = found
            logger.info("[preview-text] LibreOffice 自动发现: %s", _libreoffice_cache)
            return _libreoffice_cache

    # 3. 常见硬编码路径兜底（Windows / macOS）
    for hardcoded in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if os.path.isfile(hardcoded):
            _libreoffice_cache = hardcoded
            logger.info("[preview-text] LibreOffice 硬编码发现: %s", _libreoffice_cache)
            return _libreoffice_cache

    _libreoffice_cache = ""  # 空串表示"查找过但没找到"
    logger.warning("[preview-text] 未找到 LibreOffice — .doc/.xls/.ppt 无法预览")
    return None


def _lo_diag(rc: int, stdout: str, stderr: str) -> str:
    """把 LibreOffice 的 rc/stdout/stderr 拼成简短诊断后缀，便于前端/日志定位。"""
    lines = [ln.strip() for ln in (stderr or stdout).splitlines() if ln.strip()]
    tail = "；".join(lines[-2:])[:200] if lines else "无错误输出"
    return f"（诊断：rc={rc}，{tail}）"


def _ole_to_docx(raw: bytes, filename: str) -> bytes:
    """用 LibreOffice 把 OLE 二进制（.doc/.xls/.ppt）转成 docx/xlsx/pptx。

    内部逻辑：把 raw 写到临时目录 → soffice --headless --convert-to xxx
    → 读出转换后的文件 → 返回字节 → 清理临时目录。

    失败抛 HTTPException（带用户友好消息）。
    """
    soffice = _find_libreoffice()
    if not soffice:
        raise HTTPException(
            status_code=400,
            detail="服务器未安装 LibreOffice，无法预览 .doc/.xls/.ppt 文件。"
            "请联系管理员安装 LibreOffice，或下载后用 Word/WPS 打开。",
        )

    # 根据扩展名决定要转换成什么
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    # OLE 格式的扩展名 → LibreOffice 转换目标格式
    OLE_EXT_TO_TARGET = {
        "doc": "docx",
        "xls": "xlsx",
        "ppt": "pptx",
    }
    # 如果 magic byte 是 OLE 但扩展名不匹配（用户说 docx 实际是 doc），默认当 doc 处理
    target_ext = OLE_EXT_TO_TARGET.get(ext, "docx")

    # 临时目录做转换（Windows 需要 CWD 也可写）
    with tempfile.TemporaryDirectory(prefix="lawagent_ole_") as tmp:
        # 输入文件
        safe_in_name = f"source.{ext or 'doc'}"
        in_path = os.path.join(tmp, safe_in_name)
        with open(in_path, "wb") as fh:
            fh.write(raw)

        # LibreOffice 输出目录 = tmp（--convert-to 默认输出到当前目录）
        # 注意：Windows 下 soffice 对路径里的斜杠敏感，全部用 os.path.join

        # 关键：为本次转换指定独立的用户 profile 目录（放在可写的 tmp 内）。
        # 否则在 systemd 等服务器环境下会出现经典的"rc=0 但没有输出文件"：
        #   1. HOME 不可写 / 被 ProtectHome 隔离 → 默认 profile (~/.config/libreoffice)
        #      初始化失败，soffice 静默退出不转换；
        #   2. 残留 soffice 进程或并发转换共用默认 profile → 新调用经 UNO 管道
        #      把任务转发给旧实例后立即退出，旧实例卡住则无输出。
        profile_dir = os.path.join(tmp, "lo_profile")
        os.makedirs(profile_dir, exist_ok=True)
        profile_uri = Path(profile_dir).as_uri()  # file:///... 跨平台格式

        # systemd 下 HOME 可能缺失，fontconfig/javaldx 等组件仍会用到，补一个兜底
        env = os.environ.copy()
        env.setdefault("HOME", tmp)

        try:
            result = subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={profile_uri}",
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--norestore",
                    "--nofirststartwizard",
                    "--convert-to",
                    target_ext,
                    "--outdir",
                    tmp,
                    in_path,
                ],
                capture_output=True,
                timeout=settings.LIBREOFFICE_TIMEOUT,
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=502,
                detail=f"LibreOffice 转换超时（>{settings.LIBREOFFICE_TIMEOUT}s），"
                "请稍后重试或下载后用 Word/WPS 打开。",
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"LibreOffice 调用失败: {e}",
            )

        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        if result.returncode != 0:
            logger.error(
                "[preview-text] LibreOffice 转换失败 rc=%s\nstdout: %s\nstderr: %s",
                result.returncode,
                stdout[:500],
                stderr[:500],
            )
            diag = _lo_diag(result.returncode, stdout, stderr)
            raise HTTPException(
                status_code=400,
                detail="LibreOffice 无法解析该文件（可能已损坏）。"
                "请下载后用 Word/WPS 打开，或另存为 .docx 后重新上传。"
                + diag,
            )

        # 找到输出文件（LibreOffice 输出名 = 输入名去掉原扩展名 + 新扩展名）
        out_name = f"source.{target_ext}"
        out_path = os.path.join(tmp, out_name)
        if not os.path.isfile(out_path):
            # LibreOffice 有时用原文件名（带扩展名）+ 新扩展名
            alt_out_name = f"source.{ext or 'doc'}.{target_ext}"
            alt_out_path = os.path.join(tmp, alt_out_name)
            if os.path.isfile(alt_out_path):
                out_path = alt_out_path
            else:
                logger.error(
                    "[preview-text] LibreOffice rc=%s 未生成输出文件\n"
                    "stdout: %s\nstderr: %s\n临时目录内容: %s",
                    result.returncode,
                    stdout[:500],
                    stderr[:500],
                    os.listdir(tmp),
                )
                diag = _lo_diag(result.returncode, stdout, stderr)
                raise HTTPException(
                    status_code=400,
                    detail="LibreOffice 转换完成但未生成输出文件。"
                    "请联系管理员检查服务器 LibreOffice 运行环境"
                    "（可用 `sudo -u <服务用户> soffice --headless --convert-to docx 某.doc` 手动复现），"
                    "或下载后用 Word/WPS 打开。"
                    + diag,
                )

        with open(out_path, "rb") as fh:
            return fh.read()


def _extract_text_from_bytes(raw: bytes, filename: str) -> tuple[str, str]:
    """从文件字节提取纯文本。

    返回 (text, detected_format)。
    """
    real = _detect_real_format(raw, filename)

    # 真实是 ZIP 容器：可能是 docx / xlsx / pptx，目前只支持 docx
    if real == "zip":
        try:
            from docx import Document
            doc = Document(io.BytesIO(raw))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return text, "docx"
        except Exception:
            # 不是 docx（可能是 xlsx / pptx），再试一下扩展名
            ext = os.path.splitext(filename)[1].lower().lstrip(".")
            if ext in ("xlsx", "pptx"):
                raise HTTPException(status_code=400, detail=f"{ext} 暂不支持文本预览")
            raise HTTPException(status_code=400, detail="docx 解析失败：文件可能已损坏")

    if real == "pdf":
        try:
            import fitz  # PyMuPDF
            text_parts: list[str] = []
            with fitz.open(stream=raw, filetype="pdf") as doc:
                for page in doc:
                    text_parts.append(page.get_text())
            return "\n".join(text_parts), "pdf"
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"PDF 解析失败: {e}")

    if real == "ole":
        # 旧版 Office 二进制（.doc / .xls / .ppt）——先让 LibreOffice 转成现代格式
        converted = _ole_to_docx(raw, filename)
        # 转换后的字节重新走 zip 分支（docx/xlsx/pptx 都是 ZIP 容器）
        return _extract_text_from_bytes(converted, f"converted.{os.path.splitext(filename)[1].lower() or 'doc'}x")

    if real == "txt":
        try:
            return raw.decode("utf-8"), "txt"
        except UnicodeDecodeError:
            return raw.decode("gbk", errors="replace"), "txt"

    # 其他未知格式
    raise HTTPException(
        status_code=400,
        detail=f"暂不支持文本预览的文件格式（magic={real}）",
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
    text, detected = _extract_text_from_bytes(raw, path)
    return {
        "text": text,
        "file_type": detected,
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
