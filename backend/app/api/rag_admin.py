"""RAG 知识库管理接口（仅管理员）。

面向前端「知识库」页面，管理统一知识库 knowledge_base 的三个分类：
    law    → 法条库
    case   → 判例库
    wechat → 观点库（公众号观点）

所有分类共用 knowledge_base 集合，用 metadata.category 区分。

- POST   /api/rag/admin/ingest-file                        上传文件（切块 + 向量化入库）
- POST   /api/rag/admin/ingest-url                         抓取网页正文入库
- GET    /api/rag/admin/documents?collection_key=law       分页列出已入库条目
- GET    /api/rag/admin/search?q=&collection_key=law       语义搜索（不传则三路加权合并）
- DELETE /api/rag/admin/documents/{collection_key}/{point_id}  删除单条向量
"""
import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.deps import get_admin_user
from app.rag import qdrant_store
from app.rag.store import _extract_text, html_to_text

router = APIRouter(prefix="/api/rag/admin", tags=["rag-admin"])

# 前端分类简称（同时也是 metadata.category 的值）
VALID_CATEGORIES = {"law", "case", "wechat"}
COLLECTION_LABELS = {"law": "法条库", "case": "判例库", "wechat": "观点库"}

ALLOWED_EXTS = (".txt", ".md", ".markdown", ".pdf", ".docx", ".html", ".htm")
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _resolve_category(collection_key: str) -> str:
    """校验分类 key 并返回 category 值（直接用 collection_key 做 category）。"""
    if collection_key not in VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"无效的知识库类型: {collection_key}，应为 law/case/wechat")
    return collection_key


@router.post("/ingest-file")
def ingest_file(
    file: UploadFile = File(...),
    collection_key: str = Form(...),
    title: str = Form(""),
    user=Depends(get_admin_user),
):
    """上传文件到指定分类：提取文本 → 切块 → 向量化入库。"""
    category = _resolve_category(collection_key)
    filename = file.filename or "untitled"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=422, detail="仅支持 .txt/.md/.pdf/.docx/.html 格式")

    # 落临时文件以便按扩展名提取
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = file.file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=422, detail="文件大小不能超过 20MB")
        tmp.write(content)
        tmp_path = tmp.name
    try:
        text = _extract_text(tmp_path)
    finally:
        os.unlink(tmp_path)

    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="文件无可提取文本")

    doc_title = title.strip() or os.path.splitext(filename)[0]
    chunks = qdrant_store.ingest_document(
        text,
        title=doc_title,
        category=category,
        metadata={"file_name": filename, "uploaded_by": str(user.id)},
    )
    if chunks == 0:
        raise HTTPException(status_code=500, detail="入库失败，请检查向量服务")
    return {
        "ingested_chunks": chunks,
        "file_name": filename,
        "title": doc_title,
        "category": category,
        "label": COLLECTION_LABELS[category],
    }


@router.get("/documents")
def list_documents(
    collection_key: str,
    page_size: int = 20,
    offset: str = "",
    user=Depends(get_admin_user),
):
    """分页列出某分类已入库条目（next_offset 为空表示到底）。"""
    category = _resolve_category(collection_key)
    page_size = max(1, min(page_size, 100))
    result = qdrant_store.scroll_points(category=category, limit=page_size, offset=offset or None)
    return {**result, "category": category, "label": COLLECTION_LABELS[category]}


@router.get("/search")
def search(
    q: str,
    collection_key: str = "",
    top_k: int = 10,
    user=Depends(get_admin_user),
):
    """语义搜索已入库内容；不传 collection_key 时三路加权并行检索。"""
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="搜索关键词不能为空")
    top_k = max(1, min(top_k, 30))
    if collection_key:
        category = _resolve_category(collection_key)
        hits = qdrant_store.search(
            q, category=category, top_k=top_k, source_label=COLLECTION_LABELS[collection_key],
        )
    else:
        hits = qdrant_store.search_multi(q, top_k=top_k)
    return {"query": q, "hits": hits}


@router.delete("/documents/{collection_key}/{point_id}")
def delete_document(collection_key: str, point_id: str, user=Depends(get_admin_user)):
    """删除单条向量。"""
    _resolve_category(collection_key)  # 校验但不用于删除（point_id 全局唯一）
    ok = qdrant_store.delete_point(point_id)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"deleted": True, "id": point_id}


class IngestUrlRequest(BaseModel):
    url: str
    collection_key: str
    title: str = ""


@router.post("/ingest-url")
def ingest_url(payload: IngestUrlRequest, user=Depends(get_admin_user)):
    """抓取网页正文入库：requests 抓取 → BeautifulSoup 提取正文 → 切块向量化。

    要求目标网页可公开访问（无需登录），静态 HTML 中的正文可完整提取；
    JS 动态渲染的内容无法抓取。
    """
    import requests

    category = _resolve_category(payload.collection_key)
    url = payload.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="URL 必须以 http:// 或 https:// 开头")

    # 1) 抓取
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LawAgentKB/1.0; +https://lawagent.local)"},
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"网页抓取失败: {e}") from e
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"网页返回状态码 {resp.status_code}，无法抓取")
    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
        raise HTTPException(status_code=422, detail=f"不支持的内容类型: {content_type}")

    # 2) 提取正文
    try:
        text, page_title = html_to_text(resp.content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"正文提取失败: {e}") from e
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="网页无可提取正文（可能为 JS 动态渲染页面）")

    # 3) 切块 + 向量化入库
    doc_title = payload.title.strip() or page_title or url
    try:
        chunks = qdrant_store.ingest_document(
            text,
            title=doc_title,
            category=category,
            metadata={"source_url": url, "file_name": page_title or url, "uploaded_by": str(user.id)},
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"向量化入库失败（向量服务不可用或 embedding 异常）: {e}",
        ) from e
    if chunks == 0:
        raise HTTPException(status_code=500, detail="向量化入库失败：所有切块均未成功写入。")
    return {
        "ingested_chunks": chunks,
        "title": doc_title,
        "url": url,
        "category": category,
        "label": COLLECTION_LABELS[category],
    }
