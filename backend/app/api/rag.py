"""RAG 知识库接口：文档入库 + 检索。

- POST /api/rag/ingest-file   上传文件入库（切块 + embedding + 写 Chroma）
- POST /api/rag/ingest-text   纯文本入库
- GET  /api/rag/search        检索知识库
- GET  /api/rag/collections   列出集合
"""
import os
import tempfile

from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.rag import ingest_file, ingest_text, retrieve, list_collections

router = APIRouter(prefix="/api/rag", tags=["rag"])


class IngestTextRequest(BaseModel):
    text: str
    collection: str = "knowledge_base"
    source: str = ""
    metadata: dict = {}


class SearchResult(BaseModel):
    content: str
    source: str = ""
    chunk_index: int = 0


@router.post("/ingest-file")
def ingest_uploaded_file(
    file: UploadFile = File(...),
    collection: str = Form("knowledge_base"),
    user=Depends(get_current_user),
):
    """上传文件到知识库：先落临时文件 → 提取文本 → 入向量库。"""
    # 写到临时文件，便于按扩展名提取
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    try:
        chunks = ingest_file(
            tmp_path,
            metadata={"file_name": file.filename, "uploaded_by": str(user.id)},
            collection=collection,
        )
    finally:
        os.unlink(tmp_path)
    return {"ingested_chunks": chunks, "file_name": file.filename, "collection": collection}


@router.post("/ingest-text")
def ingest_text_api(
    payload: IngestTextRequest,
    user=Depends(get_current_user),
):
    """纯文本入库。"""
    meta = {"source": payload.source, "uploaded_by": str(user.id), **payload.metadata}
    chunks = ingest_text(payload.text, metadata=meta, collection=payload.collection, source=payload.source)
    return {"ingested_chunks": chunks}


@router.get("/search", response_model=list[SearchResult])
def search_api(
    q: str,
    top_k: int = 0,
    collection: str = "knowledge_base",
    user=Depends(get_current_user),
):
    """检索知识库，返回相关片段。"""
    results = retrieve(q, top_k=top_k or None, collection=collection)
    return [
        SearchResult(
            content=r.get("content", ""),
            source=r.get("source", ""),
            chunk_index=r.get("chunk_index", 0),
        )
        for r in results
    ]


@router.get("/collections")
def collections_api(user=Depends(get_current_user)):
    return {"collections": list_collections()}
