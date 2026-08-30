"""Chroma 向量库封装。

提供文本/文件入库与检索能力，供 rag.py 路由与 chat Agent 调用。
切块用 langchain 的 RecursiveCharacterTextSplitter（已安装 langchain-community）。
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

logger = logging.getLogger("app.rag")

# 持久化客户端（进程级单例）
_client: Optional[chromadb.PersistentClient] = None

# 默认知识库集合名
DEFAULT_COLLECTION = "knowledge_base"

# 显式 embedding 函数：chroma 自带 ONNX MiniLM（本地缓存，不依赖 HuggingFace 在线下载）。
# 必须显式指定——"default" EF 在不同进程可能解析到不同模型，导致查询向量与入库向量不一致。
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

EMBEDDING_FN = ONNXMiniLM_L6_V2()

# 文本切块器：500 字符，重叠 50
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "；", "！", "？", " ", ""],
)


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        os.makedirs(settings.CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        logger.info("[rag] Chroma 客户端已初始化: path=%s", settings.CHROMA_DIR)
    return _client


def _get_collection(name: str = DEFAULT_COLLECTION):
    client = _get_client()
    # 余弦空间 + 显式 embedding 函数 + 按相似度阈值过滤，避免不相关问题时仍返回参考资料
    return client.get_or_create_collection(
        name=name,
        embedding_function=EMBEDDING_FN,
        configuration={"hnsw": {"space": "cosine"}},
    )


def ingest_text(
    text: str,
    metadata: Optional[dict] = None,
    collection: str = DEFAULT_COLLECTION,
    source: str = "",
) -> int:
    """将一段文本切块后入库，返回入库块数。"""
    if not text or not text.strip():
        return 0
    chunks = _splitter.split_text(text)
    if not chunks:
        return 0

    col = _get_collection(collection)
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{**(metadata or {}), "source": source, "chunk_index": i} for i in range(len(chunks))]
    col.add(documents=chunks, metadatas=metadatas, ids=ids)
    logger.info("[rag] 入库完成: collection=%s, chunks=%d, source=%s", collection, len(chunks), source)
    return len(chunks)


def ingest_file(
    file_path: str,
    metadata: Optional[dict] = None,
    collection: str = DEFAULT_COLLECTION,
) -> int:
    """读取文件文本后入库，返回入库块数。

    支持 txt/md 直接读取；pdf/docx 需 pdfplumber/python-docx（已加入依赖）。
    """
    text = _extract_text(file_path)
    if not text:
        logger.warning("[rag] 文件无可提取文本: %s", file_path)
        return 0
    return ingest_text(text, metadata=metadata, collection=collection, source=os.path.basename(file_path))


def _extract_text(file_path: str) -> str:
    """按扩展名提取纯文本。"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in (".txt", ".md", ".markdown", ""):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if ext == ".pdf":
            import pdfplumber

            parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts)
        if ext == ".docx":
            from docx import Document

            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
        logger.warning("[rag] 不支持的文件类型，按文本尝试读取: %s", ext)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:  # noqa: BLE001
        logger.exception("[rag] 文件文本提取失败: %s, error=%s", file_path, e)
        return ""


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    collection: str = DEFAULT_COLLECTION,
    _report=None,
) -> list[dict]:
    """检索与 query 最相关的文档片段，返回 [{content, source, ...}]。

    _report: 可选 StageReport，细分计时（chroma查询含 embed + 检索）。
    """
    if not query or not query.strip():
        return []
    col = _get_collection(collection)
    k = top_k or settings.RAG_TOP_K
    if _report:
        with _report.stage("chroma查询(含embed)"):
            result = col.query(
                query_texts=[query],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
    else:
        result = col.query(
            query_texts=[query],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        # 余弦距离超过阈值视为不相关（如闲聊），直接丢弃，避免乱给参考资料
        if dist > settings.RAG_MAX_DISTANCE:
            continue
        out.append({"content": doc, **(meta or {})})
    dropped = len(docs) - len(out)
    logger.info(
        "[rag] 检索完成: query=%r, hits=%d, 过滤低相关=%d, 阈值=%.2f, 距离=%s, 集合数=%d",
        query[:40],
        len(out),
        dropped,
        settings.RAG_MAX_DISTANCE,
        [f"{d:.3f}" for d in dists],
        col.count(),
    )
    return out


def list_collections() -> list[str]:
    """列出所有集合名。"""
    client = _get_client()
    return [c.name for c in client.list_collections()]
