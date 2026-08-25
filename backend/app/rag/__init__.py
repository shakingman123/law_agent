"""RAG 知识库：基于 Chroma 的本地向量检索。

- 默认使用 Chroma 内置 embedding（sentence-transformers/all-MiniLM-L6-v2，首用时自动下载）
- 持久化到 CHROMA_DIR，重启不丢
- 提供 ingest_text / ingest_file / retrieve 三个核心能力
"""
from app.rag.store import ingest_file, ingest_text, retrieve, list_collections

__all__ = ["ingest_text", "ingest_file", "retrieve", "list_collections"]
