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


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    """生成中文 n-gram 字符集（2字滑动窗口），用于关键词重叠度计算。"""
    text = (text or "").strip()
    if not text:
        return set()
    if len(text) <= n:
        return {text}
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _keyword_overlap(query: str, content: str) -> float:
    """计算 query 和 content 的 2-gram 重叠率（以 query 的 n-gram 为分母）。

    中文语义单元通常是 2 字以上，2-gram 比单字更有判别力。
    返回 0~1 的比例，>=0.5 表示 query 的一半以上 2-gram 出现在 content 里。
    """
    q_ngrams = _char_ngrams(query, 2)
    if not q_ngrams:
        return 0.0
    c_ngrams = _char_ngrams(content, 2)
    overlap = q_ngrams & c_ngrams
    return len(overlap) / len(q_ngrams)


def _single_category_query(
    col, query: str, category: str, k: int, report_stage: str = ""
) -> list[dict]:
    """单分类检索：向量粗召回 + 关键词精过滤。

    流程：
      1. 向量检索（用放宽的 RAG_MAX_DISTANCE 做粗召回）
      2. 对距离 > 严格阈值 RAG_STRICT_DISTANCE 的结果，再用关键词重叠率过滤
      3. 关键词重叠率 < RAG_MIN_KEYWORD_OVERLAP 的视为不相关，丢弃

    这样兼顾短 query（向量距离高但关键词完全匹配）和长 query（向量距离低）。
    """
    where_filter = {"category": category} if category else None
    result = col.query(
        query_texts=[query],
        n_results=k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        # 1. 距离 > 放宽阈值 → 直接丢弃（完全不相关）
        if dist > settings.RAG_MAX_DISTANCE:
            continue
        # 2. 距离 <= 严格阈值 → 信任向量结果，直接通过
        if dist <= settings.RAG_STRICT_DISTANCE:
            out.append({"content": doc, "distance": dist, "category": category, **(meta or {})})
            continue
        # 3. 距离在 (严格阈值, 放宽阈值] 之间 → 关键词重叠率二次过滤
        overlap = _keyword_overlap(query, doc)
        if overlap >= settings.RAG_MIN_KEYWORD_OVERLAP:
            out.append({"content": doc, "distance": dist, "category": category, **(meta or {})})
        else:
            logger.debug(
                "[rag] 关键词过滤丢弃: dist=%.4f overlap=%.2f query=%r content=%s",
                dist, overlap, query[:30], (doc or "")[:50],
            )
    return out


def _merge_weighted(
    results_by_category: dict[str, list[dict]],
    weights: dict,
    final_k: int,
) -> list[dict]:
    """三路并行检索结果 → 乘权重 → 合并排序 → 取 top_k。

    Chroma 返回余弦距离（0=完全相同，2=完全相反），转 score = 1 - distance。
    """
    merged = []
    for cat, hits in results_by_category.items():
        w = weights.get(cat, 0.5)
        for h in hits:
            raw_score = 1 - h.get("distance", 1)  # 距离越小越相关
            h["score"] = raw_score * w
            h["category"] = cat
            merged.append(h)
    merged.sort(key=lambda r: r["score"], reverse=True)
    return merged[:final_k]


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    collection: str = DEFAULT_COLLECTION,
    category: str = "",
    weighted: bool = True,
    _report=None,
) -> list[dict]:
    """检索与 query 最相关的文档片段，返回 [{content, source, ...}]。

    Args:
        query: 检索文本。
        top_k: 最终返回条数（默认 settings.RAG_TOP_K）。
        collection: Chroma 集合名（默认 knowledge_base）。
        category: 只检索某分类（"law"/"case"/"wechat"）。空字符串=不过滤。
        weighted: 是否启用加权并行三路检索（True=三分类并行+权重合并；False=单集合不过滤）。
            - chat.py 对话框用 weighted=True（全局加权检索）。
            - 知识库管理页面指定分类时用 weighted=False + category="law"（单路无加权）。
        _report: 可选 StageReport，细分计时。
    """
    if not query or not query.strip():
        return []
    col = _get_collection(collection)
    k = top_k or settings.RAG_TOP_K

    # 情况 1：指定了 category → 单分类检索
    if category:
        stage_name = f"chroma查询({category})"
        if _report:
            with _report.stage(stage_name):
                hits = _single_category_query(col, query, category, k)
        else:
            hits = _single_category_query(col, query, category, k)
        logger.info(
            "[rag] 单分类检索: category=%s, query=%r, hits=%d, 阈值=%.2f",
            category, query[:40], len(hits), settings.RAG_MAX_DISTANCE,
        )
        return hits

    # 情况 2：weighted=True → 三分类并行 + 加权合并
    if weighted:
        from concurrent.futures import ThreadPoolExecutor

        cats = list(settings.RAG_CATEGORY_WEIGHTS.keys())
        per_k = settings.RAG_PER_CATEGORY_K
        results_by_cat: dict[str, list[dict]] = {}

        def _search_one(cat: str) -> tuple[str, list[dict]]:
            if _report:
                with _report.stage(f"chroma查询({cat})"):
                    return cat, _single_category_query(col, query, cat, per_k)
            return cat, _single_category_query(col, query, cat, per_k)

        with ThreadPoolExecutor(max_workers=3) as executor:
            for cat, hits in executor.map(lambda c: _search_one(c), cats):
                results_by_cat[cat] = hits

        merged = _merge_weighted(results_by_cat, settings.RAG_CATEGORY_WEIGHTS, k)
        total_hits = sum(len(v) for v in results_by_cat.values())
        logger.info(
            "[rag] 加权合并检索: query=%r, 三路总命中=%d, 合并后=%d, 权重=%s",
            query[:40], total_hits, len(merged), settings.RAG_CATEGORY_WEIGHTS,
        )
        return merged

    # 情况 3：weighted=False 且未指定 category → 全局不过滤
    if _report:
        with _report.stage("chroma查询(全局)"):
            result = col.query(
                query_texts=[query], n_results=k,
                include=["documents", "metadatas", "distances"],
            )
    else:
        result = col.query(
            query_texts=[query], n_results=k,
            include=["documents", "metadatas", "distances"],
        )
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        if dist > settings.RAG_MAX_DISTANCE:
            continue
        out.append({"content": doc, "distance": dist, **(meta or {})})
    logger.info("[rag] 全局检索: query=%r, hits=%d", query[:40], len(out))
    return out


def list_collections() -> list[str]:
    """列出所有集合名。"""
    client = _get_client()
    return [c.name for c in client.list_collections()]
