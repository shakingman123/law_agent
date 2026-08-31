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


def _noop():
    """空上下文：未传计时报告时的占位。"""
    from contextlib import nullcontext

    return nullcontext()

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
    _report=None,
) -> list[dict]:
    """检索单个集合，返回 [{source, title, content, score}]。

    _report: 可选 StageReport，用于分段计时诊断（embed/远端检索/回退）。
    """
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
        with (_report.child(label, "chroma回退") if _report else _noop()):
            return _fallback_chroma()

    try:
        with (_report.child(label, "embed") if _report else _noop()):
            vector = _embed(query)
        with (_report.child(label, "qdrant搜索") if _report else _noop()):
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
    _report=None,
) -> list[dict]:
    """多路并行检索：法条 / 判例 / 公众号，合并返回。

    每路取 top_k 条，合并后按 score 降序排列。
    使用线程池实现并行检索。
    _report: 可选 StageReport，计时细分到每一路（embed/qdrant搜索/回退）。
    """
    from concurrent.futures import ThreadPoolExecutor

    k = top_k or settings.RAG_TOP_K

    def _do_search(collection: str, label: str) -> list[dict]:
        return search(query, collection=collection, top_k=k, source_label=label, _report=_report)

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


def ingest_document(
    text: str,
    title: str = "",
    collection: str = settings.QDRANT_COLLECTION_LAW,
    metadata: Optional[dict] = None,
) -> int:
    """将整篇文档切块后入库（复用 Chroma 的切块器保证切分一致），返回入库块数。

    Qdrant 侧单 point 不适合长文档，入库前先按 500 字符切块；
    每块携带 chunk_index / total_chunks 便于管理界面按文档聚合展示。
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
        if ingest(chunk, title=title, collection=collection, metadata=meta):
            ok += 1
    logger.info("[qdrant] 文档入库完成: collection=%s, title=%s, chunks=%d/%d", collection, title, ok, len(chunks))
    return ok


def scroll_points(
    collection: str,
    limit: int = 20,
    offset: Optional[str] = None,
) -> dict:
    """分页列出集合条目（管理界面用），返回 {points, next_offset}。

    next_offset 为不透明分页令牌（Qdrant 为 point id，Chroma 回退为数字偏移），
    为 None 表示已到末尾。
    """
    client = _get_client()
    if client is None:
        # Chroma 回退：col.get 数字偏移分页
        try:
            from app.rag.store import _get_collection

            col = _get_collection(collection)
            data = col.get(limit=limit, offset=int(offset) if offset else 0, include=["documents", "metadatas"])
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
        records, next_offset = client.scroll(
            collection_name=collection,
            limit=limit,
            offset=offset,
            with_payload=True,
        )
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


def delete_point(collection: str, point_id: str) -> bool:
    """删除单条向量（管理界面用）。"""
    client = _get_client()
    if client is None:
        try:
            from app.rag.store import _get_collection

            _get_collection(collection).delete(ids=[point_id])
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[qdrant] Chroma 删除回退失败: %s", e)
            return False
    try:
        from qdrant_client import models

        client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points_ids=[point_id]),
        )
        logger.info("[qdrant] 已删除: collection=%s, id=%s", collection, point_id)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[qdrant] 删除失败: %s", e)
        return False
