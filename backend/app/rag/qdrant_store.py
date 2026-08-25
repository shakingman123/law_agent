"""Qdrant 向量库封装 — 法律检索多源 RAG。

依据 docs/project-framework.md §5.2：
    法条库(民法典/刑法/司法解释)  — Qdrant 向量检索
    判例库(公司脱敏案例)          — Qdrant 向量检索
    公众号观点                    — 向量检索

复用 ChromaDB 的默认 embedding 函数（all-MiniLM-L6-v2，384 维），
确保 Chroma 与 Qdrant 入库/检索的向量空间一致。
Qdrant 服务不可用时回退到 ChromaDB（dev 环境容错）。
"""
from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("app.rag")

# Qdrant 集合 → 来源标签映射
COLLECTION_LABELS = {
    settings.QDRANT_COLLECTION_LAW: "法条",
    settings.QDRANT_COLLECTION_CASE: "判例",
    settings.QDRANT_COLLECTION_WECHAT: "公众号",
}

# 所有多源检索集合
ALL_COLLECTIONS = list(COLLECTION_LABELS.keys())


@lru_cache(maxsize=1)
def _get_embedding_fn():
    """复用 ChromaDB 默认 embedding 函数（all-MiniLM-L6-v2，384 维）。"""
    from chromadb.utils import embedding_functions

    fn = embedding_functions.DefaultEmbeddingFunction()
    logger.info("[qdrant] embedding 函数已加载: all-MiniLM-L6-v2 (384d)")
    return fn


def _embed(text: str) -> list[float]:
    """将文本转为向量。"""
    fn = _get_embedding_fn()
    return fn([text])[0]


# Qdrant 客户端单例（进程级缓存：None 表示不可用）
_qdrant_client = None
_qdrant_checked = False


def _get_client():
    """获取 Qdrant 客户端。服务不可用时返回 None（仅探测一次，缓存结果）。"""
    global _qdrant_client, _qdrant_checked
    if _qdrant_checked:
        return _qdrant_client
    _qdrant_checked = True
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        client.get_collections()  # 连接探测
        _qdrant_client = client
        logger.info("[qdrant] 客户端已连接: %s", settings.QDRANT_URL)
        return client
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 连接失败，将回退 ChromaDB: %s", e)
        return None


def _ensure_collection(client, name: str) -> None:
    """确保集合存在，不存在则创建（384 维向量）。"""
    from qdrant_client.http.exceptions import UnexpectedResponse

    try:
        client.get_collection(name)
    except (UnexpectedResponse, Exception):  # noqa: BLE001
        client.create_collection(
            collection_name=name,
            vectors_config={"size": 384, "distance": "Cosine"},
        )
        logger.info("[qdrant] 集合已创建: %s", name)


def ingest(
    text: str,
    title: str = "",
    collection: str = settings.QDRANT_COLLECTION_LAW,
    metadata: Optional[dict] = None,
) -> bool:
    """将一段文本入库到指定 Qdrant 集合。返回是否成功。"""
    if not text or not text.strip():
        return False

    def _fallback_chroma_ingest() -> bool:
        """回退到 ChromaDB 入库。"""
        try:
            from app.rag.store import ingest_text

            ingest_text(text, metadata=metadata, collection=collection, source=title)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[qdrant] ChromaDB 回退入库也失败: %s", e)
            return False

    client = _get_client()
    if client is None:
        return _fallback_chroma_ingest()

    try:
        _ensure_collection(client, collection)
        vector = _embed(text)
        point_id = str(uuid.uuid4())
        payload = {"title": title, "content": text, **(metadata or {})}
        client.upsert(
            collection_name=collection,
            points=[{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info("[qdrant] 入库完成: collection=%s, title=%s", collection, title)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 入库失败，回退 ChromaDB: %s", e)
        return _fallback_chroma_ingest()


def search(
    query: str,
    collection: str = settings.QDRANT_COLLECTION_LAW,
    top_k: Optional[int] = None,
    source_label: str = "",
) -> list[dict]:
    """检索单个集合，返回 [{source, title, content, score}]。"""
    if not query or not query.strip():
        return []

    k = top_k or settings.RAG_TOP_K
    label = source_label or COLLECTION_LABELS.get(collection, "知识库")

    def _fallback_chroma() -> list[dict]:
        """回退到 ChromaDB 检索。"""
        try:
            from app.rag.store import retrieve

            results = retrieve(query, top_k=k, collection=collection)
            return [{"source": label, "title": r.get("source", ""), "content": r.get("content", "")} for r in results]
        except Exception as e:  # noqa: BLE001
            logger.warning("[qdrant] ChromaDB 回退检索也失败: %s", e)
            return []

    client = _get_client()
    if client is None:
        return _fallback_chroma()

    try:
        vector = _embed(query)
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            limit=k,
            with_payload=True,
        )
        out = []
        for hit in hits:
            payload = hit.payload or {}
            out.append({
                "source": label,
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                "score": hit.score,
            })
        logger.info("[qdrant] 检索完成: collection=%s, query=%r, hits=%d", collection, query[:40], len(out))
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 检索失败，回退 ChromaDB: %s", e)
        return _fallback_chroma()


def search_multi(
    query: str,
    top_k: Optional[int] = None,
) -> list[dict]:
    """多路并行检索：法条 / 判例 / 公众号，合并返回。

    每路取 top_k 条，合并后按 score 降序排列。
    使用线程池实现并行检索。
    """
    from concurrent.futures import ThreadPoolExecutor

    k = top_k or settings.RAG_TOP_K

    def _do_search(collection: str, label: str) -> list[dict]:
        return search(query, collection=collection, top_k=k, source_label=label)

    all_hits = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(_do_search, col, label)
            for col, label in COLLECTION_LABELS.items()
        ]
        for future in futures:
            try:
                all_hits.extend(future.result())
            except Exception as e:  # noqa: BLE001
                logger.warning("[qdrant] 检索异常: %s", e)

    # 按 score 降序（无 score 的排末尾）
    all_hits.sort(key=lambda r: r.get("score", 0), reverse=True)
    logger.info("[qdrant] 多路检索合并: query=%r, total=%d", query[:40], len(all_hits))
    return all_hits
