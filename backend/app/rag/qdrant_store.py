"""Qdrant 向量库封装 — 单一集合 + 分类 metadata + 加权并行检索。

所有数据统一存入 knowledge_base 集合，用 metadata.category 区分来源（law/case/wechat）。
检索时按 category 并行三路查询，各自乘权重后合并排序返回。
Qdrant 服务不可用时自动回退到 ChromaDB（dev 环境容错）。
"""
from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("app.rag")


def _noop():
    """空上下文：未传计时报告时的占位。"""
    from contextlib import nullcontext

    return nullcontext()


# 分类 key → UI 标签（不再对应集合名）
CATEGORY_LABELS = {
    "law": "法条",
    "case": "判例",
    "wechat": "公众号",
}

# 知识库集合名（统一）
KNOWLEDGE_COLLECTION = "knowledge_base"


@lru_cache(maxsize=1)
def _get_embedding_fn():
    """获取 embedding 函数（与 store.py 保持同一套多层回退策略，保证向量空间一致）。"""
    from app.rag.store import _init_embedding_fn

    return _init_embedding_fn()


def _embed(text: str) -> list[float]:
    """将文本转为向量；ONNX 延迟失败时自动重新初始化 embedding 函数并重试。"""
    fn = _get_embedding_fn()
    try:
        return fn([text])[0]
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] embed 调用异常，重置 embedding 函数重试: %s", e)
        _get_embedding_fn.cache_clear()  # 清缓存后下次调用会自然重新初始化
        from app.rag.store import _init_embedding_fn

        fn = _init_embedding_fn()
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

        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=settings.QDRANT_TIMEOUT)
        client.get_collections()  # 连接探测
        _qdrant_client = client
        logger.info("[qdrant] 客户端已连接: %s, timeout=%s", settings.QDRANT_URL, settings.QDRANT_TIMEOUT)
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


def _qdrant_category_filter(category: str):
    """构造 Qdrant payload 过滤条件：must match category。"""
    from qdrant_client import models

    return models.Filter(
        must=[models.FieldCondition(key="category", match=models.MatchValue(value=category))]
    )


def ingest(
    text: str,
    title: str = "",
    category: str = "law",
    metadata: Optional[dict] = None,
) -> bool:
    """将一段文本入库到 knowledge_base 集合。返回是否成功。

    category: "law" / "case" / "wechat"，写入 metadata.category。
    """
    if not text or not text.strip():
        return False

    def _fallback_chroma_ingest() -> bool:
        """回退到 ChromaDB 入库。"""
        try:
            from app.rag.store import ingest_text

            meta = {**(metadata or {}), "category": category}
            ingest_text(text, metadata=meta, collection=KNOWLEDGE_COLLECTION, source=title)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[qdrant] ChromaDB 回退入库也失败: %s", e)
            return False

    client = _get_client()
    if client is None:
        return _fallback_chroma_ingest()

    try:
        _ensure_collection(client, KNOWLEDGE_COLLECTION)
        vector = _embed(text)
        point_id = str(uuid.uuid4())
        payload = {"title": title, "content": text, "category": category, **(metadata or {})}
        client.upsert(
            collection_name=KNOWLEDGE_COLLECTION,
            points=[{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info("[qdrant] 入库完成: category=%s, title=%s", category, title)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 入库失败，回退 ChromaDB: %s", e)
        return _fallback_chroma_ingest()


def search(
    query: str,
    category: str = "",
    top_k: Optional[int] = None,
    source_label: str = "",
    _report=None,
) -> list[dict]:
    """检索 knowledge_base 集合。

    Args:
        query: 检索文本。
        category: 过滤分类（"law"/"case"/"wechat"）。空=不过滤。
        top_k: 返回条数。
        source_label: 覆盖来源标签。
        _report: 计时报告。

    返回 [{source, title, content, score, category}]。
    """
    if not query or not query.strip():
        return []

    k = top_k or settings.RAG_TOP_K
    label = source_label or CATEGORY_LABELS.get(category, "知识库")

    def _fallback_chroma() -> list[dict]:
        """回退到 ChromaDB 检索。"""
        try:
            from app.rag.store import retrieve

            results = retrieve(query, top_k=k, collection=KNOWLEDGE_COLLECTION, category=category, weighted=False)
            return [{"source": label, "title": r.get("source", r.get("title", "")),
                     "content": r.get("content", ""), "score": 1 - r.get("distance", 1),
                     "category": r.get("category", category)} for r in results]
        except Exception as e:  # noqa: BLE001
            logger.warning("[qdrant] ChromaDB 回退检索也失败: %s", e)
            return []

    client = _get_client()
    if client is None:
        with (_report.child(label, "chroma回退") if _report else _noop()):
            return _fallback_chroma()

    try:
        with (_report.child(label, "embed") if _report else _noop()):
            vector = _embed(query)

        search_kwargs = {
            "collection_name": KNOWLEDGE_COLLECTION,
            "query_vector": vector,
            "limit": k,
            "with_payload": True,
        }
        if category:
            search_kwargs["query_filter"] = _qdrant_category_filter(category)

        with (_report.child(label, "qdrant搜索") if _report else _noop()):
            hits = client.search(**search_kwargs)

        out = []
        for hit in hits:
            payload = hit.payload or {}
            out.append({
                "source": CATEGORY_LABELS.get(payload.get("category", ""), label),
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                "score": hit.score,
                "category": payload.get("category", category),
            })
        logger.info("[qdrant] 检索完成: category=%s, query=%r, hits=%d", category or "全量", query[:40], len(out))
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 检索失败，回退 ChromaDB: %s", e)
        return _fallback_chroma()


def search_multi(
    query: str,
    top_k: Optional[int] = None,
    _report=None,
) -> list[dict]:
    """同一集合 knowledge_base 三路并行 + 加权合并检索。

    每路用 where={"category": ...} 过滤，各自取 RAG_PER_CATEGORY_K 条，
    乘权重后合并排序，最终取 top_k 返回。
    """
    from concurrent.futures import ThreadPoolExecutor

    k = top_k or settings.RAG_TOP_K
    per_k = settings.RAG_PER_CATEGORY_K
    weights = settings.RAG_CATEGORY_WEIGHTS
    cats = list(CATEGORY_LABELS.keys())

    def _do_search(cat: str) -> list[dict]:
        return search(query, category=cat, top_k=per_k, source_label=CATEGORY_LABELS[cat], _report=_report)

    all_hits = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_do_search, cat) for cat in cats]
        for future in futures:
            try:
                all_hits.extend(future.result())
            except Exception as e:  # noqa: BLE001
                logger.warning("[qdrant] 检索异常: %s", e)

    # 加权：score = 原分 × 权重
    for h in all_hits:
        w = weights.get(h.get("category", ""), 0.5)
        h["score"] = h.get("score", 0) * w

    all_hits.sort(key=lambda r: r.get("score", 0), reverse=True)
    result = all_hits[:k]
    logger.info("[qdrant] 多路加权合并: query=%r, total=%d, merged=%d", query[:40], len(all_hits), len(result))
    return result


def ingest_document(
    text: str,
    title: str = "",
    category: str = "law",
    metadata: Optional[dict] = None,
) -> int:
    """将整篇文档切块后入库，返回入库块数。

    category: "law" / "case" / "wechat"，写入 metadata.category。
    """
    if not text or not text.strip():
        return 0
    from app.rag.store import _splitter

    chunks = _splitter.split_text(text)
    if not chunks:
        return 0
    ok = 0
    for i, chunk in enumerate(chunks):
        meta = {**(metadata or {}), "chunk_index": i, "total_chunks": len(chunks)}
        if ingest(chunk, title=title, category=category, metadata=meta):
            ok += 1
    logger.info("[qdrant] 文档入库完成: category=%s, title=%s, chunks=%d/%d", category, title, ok, len(chunks))
    return ok


def scroll_points(
    category: str = "",
    limit: int = 20,
    offset: Optional[str] = None,
) -> dict:
    """分页列出 knowledge_base 集合条目（可按 category 过滤）。"""
    client = _get_client()
    if client is None:
        # Chroma 回退
        try:
            from app.rag.store import _get_collection

            col = _get_collection(KNOWLEDGE_COLLECTION)
            where_filter = {"category": category} if category else None
            data = col.get(limit=limit, offset=int(offset) if offset else 0,
                           where=where_filter, include=["documents", "metadatas"])
            ids = data.get("ids") or []
            docs = data.get("documents") or []
            metas = data.get("metadatas") or []
            points = []
            for i, pid in enumerate(ids):
                meta = metas[i] if i < len(metas) else {}
                points.append({
                    "id": pid,
                    "title": (meta or {}).get("title", (meta or {}).get("source", "")),
                    "content": docs[i] if i < len(docs) else "",
                    **(meta or {}),
                })
            has_more = len(ids) == limit
            next_offset = str((int(offset) if offset else 0) + len(ids)) if has_more else None
            return {"points": points, "next_offset": next_offset}
        except Exception as e:  # noqa: BLE001
            logger.warning("[qdrant] Chroma 列表回退失败: %s", e)
            return {"points": [], "next_offset": None}

    try:
        scroll_kwargs = {
            "collection_name": KNOWLEDGE_COLLECTION,
            "limit": limit,
            "offset": offset,
            "with_payload": True,
        }
        if category:
            scroll_kwargs["scroll_filter"] = _qdrant_category_filter(category)
        records, next_offset = client.scroll(**scroll_kwargs)
        points = []
        for rec in records:
            payload = rec.payload or {}
            points.append({
                "id": str(rec.id),
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                **{k: v for k, v in payload.items() if k not in ("title", "content")},
            })
        return {"points": points, "next_offset": str(next_offset) if next_offset else None}
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 列出条目失败: %s", e)
        return {"points": [], "next_offset": None}


def delete_point(point_id: str) -> bool:
    """删除 knowledge_base 集合中的单条向量。"""
    client = _get_client()
    if client is None:
        try:
            from app.rag.store import _get_collection

            _get_collection(KNOWLEDGE_COLLECTION).delete(ids=[point_id])
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[qdrant] Chroma 删除回退失败: %s", e)
            return False
    try:
        from qdrant_client import models

        client.delete(
            collection_name=KNOWLEDGE_COLLECTION,
            points_selector=models.PointIdsList(points_ids=[point_id]),
        )
        logger.info("[qdrant] 已删除: id=%s", point_id)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 删除失败: %s", e)
        return False
