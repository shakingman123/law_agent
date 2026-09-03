"""统一文件存储服务。

支持 MinIO 对象存储（优先）+ 本地文件系统（回退），
并提供 AES 加密存储能力（Fernet）。

对外暴露的 URL 统一为 ``/api/files/{path}`` 格式，
由 ``storage.serve_file_response(url)`` 自动识别后端（本地磁盘 / MinIO）
并返回正确的 FastAPI 响应。

URL 内部约定：
- ``object_name`` 形如 ``cases/{case_id}/判决书.doc`` 或 ``encrypted/xxx.enc``
- 本地明文：磁盘路径 ``UPLOAD_DIR/{object_name}``，URL ``/api/files/{object_name}``
- MinIO 明文：bucket + object_name，URL 同本地（通过 serve 路由统一代理）
- 加密文件：Fernet 加密后存储，URL 前缀标记为 ``encrypted/``

设计原则：
- 存储后端（本地 vs MinIO）对业务层透明
- MinIO 不可用时自动回退本地，不影响业务流程
- 加密是 upload_encrypted 的内置行为，调用方不需要自己 encrypt + 存
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.security import _fernet

logger = logging.getLogger("app.core.storage")

# ---------------------------------------------------------------------------
# MinIO 客户端（惰性初始化，首次真正需要时才连接）
# ---------------------------------------------------------------------------
_minio_client = None
_minio_available: Optional[bool] = None  # None=未检测, True=可用, False=不可用


def _get_minio_client():
    """返回 MinIO 客户端，不可用时返回 None（只尝试一次，后续直接用缓存结果）。"""
    global _minio_client, _minio_available
    if _minio_available is False:
        return None
    if _minio_client is not None:
        return _minio_client
    try:
        from minio import Minio
        from minio.error import S3Error

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        # 连通性探测：检查 bucket 存在性
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)
            logger.info("[storage] MinIO bucket '%s' created", settings.MINIO_BUCKET)
        _minio_client = client
        _minio_available = True
        logger.info("[storage] MinIO connected: %s/%s", settings.MINIO_ENDPOINT, settings.MINIO_BUCKET)
        return client
    except Exception as e:  # noqa: BLE001 — MinIO 所有异常都在这里兜底
        logger.warning("[storage] MinIO 不可用，回退本地存储: %s", e)
        _minio_available = False
        return None


def _is_minio_url(url: str) -> bool:
    """判断一个对外 URL 是否对应 MinIO 上的对象。

    约定：所有 URL 都以 /api/files/ 开头，本地和 MinIO 通过 StorageService 内部
    统一管理。这里不暴露额外前缀，URL 格式对调用方无差异。
    此函数始终返回 False —— URL 与后端解耦，下载时按需判断。
    """
    return False


# ---------------------------------------------------------------------------
# 核心服务
# ---------------------------------------------------------------------------
class StorageService:
    """统一文件存储：MinIO 优先 + 本地回退 + 可选 AES 加密。

    使用示例::

        storage = StorageService()
        url, size = storage.upload_plain(file_bytes, "cases/8/判决书.doc")
        # 返回 url = "/api/files/cases/8/判决书.doc"

        enc_url = storage.upload_encrypted(file_bytes, "encrypted/secret.doc")
        # 返回 enc_url = "/api/files/encrypted/secret.doc.enc"

        bytes_data = storage.download("/api/files/cases/8/判决书.doc")
        storage.delete("/api/files/cases/8/判决书.doc")
    """

    # URL 前缀（与 api/files.py 的路由保持一致）
    URL_PREFIX = "/api/files/"

    # 本地存储根目录
    @property
    def local_root(self) -> str:
        return settings.UPLOAD_DIR

    # ------------------------------------------------------------------
    # 上传：明文
    # ------------------------------------------------------------------
    def upload_plain(
        self,
        file_bytes: bytes,
        object_name: str,
    ) -> tuple[str, int]:
        """上传明文文件，返回 ``(url, file_size)``。

        :param file_bytes: 文件原始字节
        :param object_name: 对象名，如 ``cases/8/判决书.doc``
        """
        size = len(file_bytes)

        # 1. 尝试 MinIO
        minio = _get_minio_client()
        if minio is not None:
            try:
                minio.put_object(
                    settings.MINIO_BUCKET,
                    object_name,
                    io.BytesIO(file_bytes),
                    length=size,
                )
                url = f"{self.URL_PREFIX}{object_name}"
                logger.info("[storage][minio] upload_plain -> %s (%d bytes)", url, size)
                return url, size
            except Exception as e:  # noqa: BLE001
                logger.warning("[storage] MinIO put 失败，回退本地: %s", e)

        # 2. 本地回退
        local_path = os.path.join(self.local_root, object_name)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(file_bytes)
        url = f"{self.URL_PREFIX}{object_name}"
        logger.info("[storage][local] upload_plain -> %s (%d bytes)", url, size)
        return url, size

    # ------------------------------------------------------------------
    # 上传：AES 加密
    # ------------------------------------------------------------------
    def upload_encrypted(
        self,
        file_bytes: bytes,
        object_name: str,
    ) -> str:
        """Fernet AES 加密后存储，返回 ``url``。

        object_name 会自动加上 ``encrypted/`` 前缀与 ``.enc`` 后缀，
        调用方不需要自己加。最终 URL 形如 ``/api/files/encrypted/判决书.doc.enc``。
        """
        if not object_name.startswith("encrypted/"):
            object_name = f"encrypted/{object_name}"
        if not object_name.endswith(".enc"):
            object_name = f"{object_name}.enc"

        encrypted = _fernet.encrypt(file_bytes)

        # 1. 尝试 MinIO
        minio = _get_minio_client()
        if minio is not None:
            try:
                minio.put_object(
                    settings.MINIO_BUCKET,
                    object_name,
                    io.BytesIO(encrypted),
                    length=len(encrypted),
                )
                url = f"{self.URL_PREFIX}{object_name}"
                logger.info("[storage][minio] upload_encrypted -> %s", url)
                return url
            except Exception as e:  # noqa: BLE001
                logger.warning("[storage] MinIO put 加密文件失败，回退本地: %s", e)

        # 2. 本地回退
        local_path = os.path.join(self.local_root, object_name)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(encrypted)
        url = f"{self.URL_PREFIX}{object_name}"
        logger.info("[storage][local] upload_encrypted -> %s", url)
        return url

    # ------------------------------------------------------------------
    # 下载：返回 bytes（调用方自己决定要不要解密）
    # ------------------------------------------------------------------
    def download(self, url: str, decrypt: bool = False) -> bytes:
        """从存储读取文件字节。

        :param url: 存储服务返回的 URL，如 ``/api/files/cases/8/xxx.doc``
        :param decrypt: 若为 True 且检测到加密文件（路径含 ``.enc``），则自动 Fernet 解密
        """
        object_name = self._url_to_object_name(url)
        encrypted = object_name.startswith("encrypted/") or object_name.endswith(".enc")

        # 1. 先查 MinIO
        minio = _get_minio_client()
        if minio is not None:
            try:
                resp = minio.get_object(settings.MINIO_BUCKET, object_name)
                raw = resp.read()
                resp.close()
                logger.info("[storage][minio] download <- %s", url)
                return _decrypt_if_needed(raw, encrypted and decrypt)
            except Exception as e:  # noqa: BLE001
                logger.debug("[storage] MinIO get 失败，尝试本地: %s", e)

        # 2. 本地磁盘
        local_path = os.path.join(self.local_root, object_name)
        if not os.path.isfile(local_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {url}")
        with open(local_path, "rb") as f:
            raw = f.read()
        logger.info("[storage][local] download <- %s", url)
        return _decrypt_if_needed(raw, encrypted and decrypt)

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------
    def delete(self, url: str) -> None:
        """删除文件（MinIO + 本地都会尝试，幂等）。"""
        object_name = self._url_to_object_name(url)

        # MinIO
        minio = _get_minio_client()
        if minio is not None:
            try:
                minio.remove_object(settings.MINIO_BUCKET, object_name)
                logger.info("[storage][minio] deleted %s", url)
            except Exception as e:  # noqa: BLE001
                logger.debug("[storage] MinIO remove 失败（可能本就不存在）: %s", e)

        # 本地
        local_path = os.path.join(self.local_root, object_name)
        if os.path.isfile(local_path):
            os.remove(local_path)
            logger.info("[storage][local] deleted %s", url)

    # ------------------------------------------------------------------
    # FastAPI 响应：直接返回给浏览器下载/预览
    # ------------------------------------------------------------------
    def serve_file_response(self, url: str) -> StreamingResponse | FileResponse:
        """生成 FastAPI 响应，用于 GET /api/files/{path} 场景。

        本地文件用 FileResponse（零拷贝、支持 Range），
        MinIO 文件用 StreamingResponse（流式读取、避免大文件占内存）。
        加密文件（.enc）不解密返回 —— 这个接口只负责原始字节的 HTTP 输出。
        """
        object_name = self._url_to_object_name(url)
        filename = os.path.basename(object_name)

        # 1. MinIO 流式返回
        minio = _get_minio_client()
        if minio is not None:
            try:
                resp = minio.get_object(settings.MINIO_BUCKET, object_name)
                from fastapi import Header

                content_length = resp.headers.get("Content-Length")
                media_type = resp.headers.get("Content-Type", "application/octet-stream")

                return StreamingResponse(
                    resp.stream(32 * 1024),
                    media_type=media_type,
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}"',
                        **({"Content-Length": content_length} if content_length else {}),
                    },
                    background=lambda: resp.close(),
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("[storage] serve MinIO 失败，尝试本地: %s", e)

        # 2. 本地文件
        local_path = os.path.join(self.local_root, object_name)
        if not os.path.isfile(local_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(
            local_path,
            filename=filename,
            media_type=_guess_media_type(local_path),
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _url_to_object_name(self, url: str) -> str:
        """把对外 URL 转为内部 object_name。

        ``/api/files/cases/8/xxx.doc`` → ``cases/8/xxx.doc``
        """
        if url.startswith(self.URL_PREFIX):
            return url[len(self.URL_PREFIX):]
        # 兜底：去掉开头的 /
        return url.lstrip("/")


# ---------------------------------------------------------------------------
# 模块级单例（大多数场景直接 import storage 即可）
# ---------------------------------------------------------------------------
storage = StorageService()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _decrypt_if_needed(raw: bytes, do_decrypt: bool) -> bytes:
    """条件解密；do_decrypt=False 时原样返回。"""
    if not do_decrypt:
        return raw
    try:
        return _fernet.decrypt(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("[storage] 解密失败，返回原始字节: %s", e)
        return raw


def _guess_media_type(path: str) -> str:
    """简单的文件类型推断（够用即可，无需 mimetypes 模块的完整覆盖）。"""
    ext = os.path.splitext(path)[1].lower()
    mapping = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".txt": "text/plain; charset=utf-8",
    }
    return mapping.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# 兼容层：自动生成本地存储的时间戳文件名（保留原 _save_upload 的行为）
# ---------------------------------------------------------------------------
def make_safe_name(filename: str, subdir: str = "") -> tuple[str, str]:
    """生成带时间戳的安全 object_name，返回 ``(object_name, safe_filename)``。

    示例::

        make_safe_name("判决书.doc", subdir="case_8")
        # -> ("case_8/20260903120000_判决书.doc", "20260903120000_判决书.doc")
    """
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_filename = f"{ts}_{filename}"
    object_name = f"{subdir}/{safe_filename}" if subdir else safe_filename
    return object_name, safe_filename
