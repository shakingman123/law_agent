"""案件归档 Agent — LangGraph 状态图。

依据 docs/project-framework.md §5.4：
    上传 Word/PDF/照片/视频 → 病毒扫描 → AES 加密 → MinIO
    → 按案件归档 → (公司库) 脱敏处理 → 写入 legal_references

脱敏采用纯本地方案（正则 + spaCy NER），详见 desensitize.py。
病毒扫描通过 ClamAV 守护进程（clamd）；守护进程不可用时 fail-open（仅记录日志）。
加密与存储统一走 StorageService（MinIO 优先 / 本地回退，Fernet AES 内置）。
"""
from __future__ import annotations

import logging
import os
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents.archive.desensitize import desensitize_file
from app.core.config import settings
from app.core.storage import storage
from app.models.legal_reference import LegalReference
from app.models.user import User

logger = logging.getLogger("app.agents.archive")


class ArchiveState(TypedDict, total=False):
    file_name: str
    file_type: str               # docx/pdf/image/video
    case_id: int
    scanned: bool                # 病毒扫描通过
    encrypted_url: str           # 加密存储后的 URL
    desensitized: bool           # 是否完成脱敏
    desensitized_text: str       # 脱敏后的文本（待写入 legal_references）
    legal_ref_id: int            # 写入 legal_references 的 ID


def _scan_with_clamav(file_path: str) -> bool:
    """通过 ClamAV 守护进程扫描文件。

    返回 True 表示安全（或守护进程不可用时 fail-open）。
    返回 False 表示检测到病毒。
    """
    try:
        import clamd
    except ImportError:
        logger.warning("[scan] clamd 未安装，跳过病毒扫描（fail-open）")
        return True

    try:
        if settings.CLAMAV_SOCKET:
            cd = clamd.ClamdUnixSocket(settings.CLAMAV_SOCKET)
        else:
            cd = clamd.ClamdNetworkSocket(
                settings.CLAMAV_HOST, settings.CLAMAV_PORT
            )
        result = cd.scan(file_path)
        # result 格式: {'file_path': ('OK', None)} 或 {'file_path': ('FOUND', 'VirusName')}
        for _path, (status, virus) in result.items():
            if status == "FOUND":
                logger.warning("[scan] 检测到病毒: %s → %s", file_path, virus)
                return False
        logger.info("[scan] 病毒扫描通过: %s", file_path)
        return True
    except Exception as e:  # noqa: BLE001
        # 守护进程不可用、连接超时等 → fail-open（开发环境）
        logger.warning("[scan] ClamAV 守护进程不可用，跳过扫描（fail-open）: %s", e)
        return True


def _encrypt_and_store(file_path: str, file_name: str) -> str:
    """读取文件 → Fernet AES 加密 → 上传存储（MinIO 优先 / 本地回退）。

    存储与加密能力全部委托 StorageService，返回对外可访问的 URL。
    """
    with open(file_path, "rb") as f:
        raw = f.read()
    return storage.upload_encrypted(raw, file_name)


def build_archive_graph(user: User, db: Session):
    def scan_node(state: ArchiveState) -> dict:
        """病毒扫描：通过 ClamAV 守护进程扫描上传文件。"""
        file_name = state.get("file_name", "")
        file_path = os.path.join(settings.UPLOAD_DIR, file_name)
        if not os.path.isfile(file_path):
            logger.warning("[scan] 文件不存在，跳过扫描: %s", file_name)
            return {"scanned": False}
        safe = _scan_with_clamav(file_path)
        return {"scanned": safe}

    async def desensitize_node(state: ArchiveState) -> dict:
        """脱敏处理：纯本地方案（正则 + spaCy NER）。

        仅公司库入 legal_references 时需要；私库文件原文加密存储。
        流程：
        1. 定位文件路径（uploads/{file_name}）
        2. 提取文本（docx 用 python-docx，pdf 用 PyMuPDF）
        3. 正则匹配结构化信息（身份证/手机/银行卡/案号/地址）
        4. spaCy NER 识别人名/机构名/地名
        5. 角色替换（上诉人张三 → 上诉人甲）
        6. 写入 legal_references 表（type=公司案例, is_desensitized=True）
        文件不存在/格式不支持/内容为空，由 desensitize_file 统一返回 None。
        """
        file_name = state.get("file_name", "")
        file_path = os.path.join(settings.UPLOAD_DIR, file_name)
        logger.info("[desensitize_node] 开始脱敏: file=%s", file_name)
        result = desensitize_file(file_path)
        if result is None:
            logger.warning("[desensitize_node] 脱敏失败或无内容: %s", file_name)
            return {"desensitized": False}

        # 写入 legal_references 表（公司案例库，已脱敏）
        case_id = state.get("case_id")
        ref = LegalReference(
            type="公司案例",
            title=file_name,
            content=result,
            is_desensitized=True,
            source_url=file_name,
            case_id=case_id,
        )
        db.add(ref)
        db.commit()
        db.refresh(ref)
        logger.info(
            "[desensitize_node] 脱敏完成并入库 legal_references: file=%s, ref_id=%d, 脱敏后长度=%d",
            file_name, ref.id, len(result),
        )
        return {"desensitized": True, "desensitized_text": result, "legal_ref_id": ref.id}

    def store_node(state: ArchiveState) -> dict:
        """AES(Fernet) 加密文件 → 上传 MinIO（不可用时回退本地存储）。"""
        file_name = state.get("file_name", "")
        file_path = os.path.join(settings.UPLOAD_DIR, file_name)
        if not os.path.isfile(file_path):
            logger.warning("[store] 文件不存在，跳过加密存储: %s", file_name)
            return {"encrypted_url": ""}
        url = _encrypt_and_store(file_path, file_name)
        return {"encrypted_url": url}

    builder = StateGraph(ArchiveState)
    builder.add_node("scan", scan_node)
    builder.add_node("desensitize", desensitize_node)
    builder.add_node("store", store_node)
    builder.set_entry_point("scan")
    builder.add_edge("scan", "desensitize")
    builder.add_edge("desensitize", "store")
    builder.add_edge("store", END)

    return builder.compile()
