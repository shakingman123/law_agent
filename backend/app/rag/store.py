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

# 显式 embedding 函数：all-MiniLM-L6-v2（384 维），与 qdrant_store 共享向量空间。
# 服务器离线环境下 ONNX 模型随 chromadb 包预装，只需目录权限即可运行。
# 关键：import 阶段绝不能触发 HuggingFace 联网下载——否则 systemd 启动超时杀进程 → nginx 502。
def _init_embedding_fn():
    """多层回退，但只做构造不做 probe（probe 会触发模型写入/联网）。"""
    logger = logging.getLogger("app.rag")
    # 1) 优先 ONNX MiniLM：模型随 chromadb 预装在 site-packages/chromadb/utils/embedding_functions/models/
    #    不需要联网，只需要 ~/.cache/chroma/onnx_models 目录写权限
    try:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        fn = ONNXMiniLM_L6_V2()
        # 不跑 probe！probe 会触发首次 embed 写缓存 → 权限被拒 → 掉到 SentenceTransformer → 联网超时
        # 延迟到第一次真正的 col.add() / col.query() 时再决定是否需要 per-call 回退
        logger.info("[rag] embedding: ONNXMiniLM_L6_V2 (ONNX, 延迟验证)")
        return fn
    except Exception as e:  # noqa: BLE001
        logger.warning("[rag] ONNXMiniLM_L6_V2 构造失败: %s", e)

    # 2) SentenceTransformer：服务器无外网时会在 probe 阶段卡 HuggingFace 超时
    #    只构造不 probe，让延迟失败由 per-call 回退处理
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        logger.info("[rag] embedding: SentenceTransformer (PyTorch, 延迟验证)")
        return fn
    except Exception as e:  # noqa: BLE001
        logger.warning("[rag] SentenceTransformer 构造失败: %s", e)

    raise RuntimeError("所有 embedding 函数构造失败，请检查 chromadb/onnxruntime 依赖")


EMBEDDING_FN = _init_embedding_fn()

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
    try:
        col.add(documents=chunks, metadatas=metadatas, ids=ids)
    except Exception as e:  # noqa: BLE001
        # ONNX init probe 可能通过但实际 embed 时才炸（Rust 绑定延迟失败）
        logger.warning("[rag] Chroma 入库异常（可能是延迟失败的 Rust 绑定），尝试重新初始化 embedding: %s", e)
        # 重新加载 _init_embedding_fn 会跳过 ONNX 直接回退到 SentenceTransformer
        global EMBEDDING_FN
        try:
            EMBEDDING_FN = _init_embedding_fn()
        except Exception as e2:  # noqa: BLE001
            raise RuntimeError(f"embedding 重新初始化仍失败: {e2}") from e
        # 重建 collection（因为旧 collection 缓存了旧的 embedding_function 引用）
        col = _get_client().get_or_create_collection(
            name=collection,
            embedding_function=EMBEDDING_FN,
            configuration={"hnsw": {"space": "cosine"}},
        )
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


def html_to_text(content: bytes) -> tuple[str, str]:
    """HTML 字节流 → (正文文本, <title>标题)。

    去掉 script/style/noscript 标签，按行去空，供文件上传与 URL 抓取共用。
    传入 bytes 由 BeautifulSoup 自动检测编码（支持 UTF-8/GBK 等中文网页）。
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(content, "lxml")
    page_title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return text, page_title


def _extract_text(file_path: str) -> str:
    """按扩展名提取纯文本。"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in (".txt", ".md", ".markdown", ""):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if ext in (".html", ".htm"):
            with open(file_path, "rb") as f:
                text, _ = html_to_text(f.read())
            return text
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
