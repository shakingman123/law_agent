import request from './request';

/**
 * 知识库（RAG 管理）接口
 * 对应后端 /api/rag/admin/*，仅管理员可用
 * law → 法条库 / case → 判例库 / wechat → 观点库
 */
export type KnowledgeKey = 'law' | 'case' | 'wechat';

export interface KnowledgeDoc {
  id: string;
  title: string;
  content: string;
  chunk_index?: number;
  total_chunks?: number;
  file_name?: string;
  /** 搜索结果中的相关度（0~1，列表接口无此字段） */
  score?: number;
  source?: string;
}

export interface KnowledgeListResult {
  points: KnowledgeDoc[];
  /** 不透明分页令牌，null 表示到底 */
  next_offset: string | null;
  collection: string;
  label: string;
}

export interface KnowledgeSearchHit {
  source: string;
  title: string;
  content: string;
  score: number;
}

export interface IngestResult {
  ingested_chunks: number;
  file_name: string;
  title: string;
  collection: string;
}

export interface IngestUrlResult {
  ingested_chunks: number;
  title: string;
  url: string;
  collection: string;
}

export const knowledgeApi = {
  /** 上传文件入库（切块 + 向量化） */
  upload: (file: File, collectionKey: KnowledgeKey, title = '') => {
    const form = new FormData();
    form.append('file', file);
    form.append('collection_key', collectionKey);
    if (title) form.append('title', title);
    return request
      .post<IngestResult>('/rag/admin/ingest-file', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      })
      .then((r) => r.data);
  },

  /** 粘贴 URL 抓取网页正文入库 */
  ingestUrl: (url: string, collectionKey: KnowledgeKey) =>
    request
      .post<IngestUrlResult>(
        '/rag/admin/ingest-url',
        { url, collection_key: collectionKey },
        { timeout: 30000 },
      )
      .then((r) => r.data),

  /** 分页列出已入库条目 */
  list: (collectionKey: KnowledgeKey, pageSize = 20, offset = '') =>
    request
      .get<KnowledgeListResult>('/rag/admin/documents', {
        params: { collection_key: collectionKey, page_size: pageSize, offset },
      })
      .then((r) => r.data),

  /** 语义搜索（collectionKey 为空则三库合并检索） */
  search: (q: string, collectionKey: KnowledgeKey | '', topK = 10) =>
    request
      .get<{ query: string; hits: KnowledgeSearchHit[] }>('/rag/admin/search', {
        params: { q, collection_key: collectionKey || undefined, top_k: topK },
      })
      .then((r) => r.data),

  /** 删除单条向量 */
  remove: (collectionKey: KnowledgeKey, id: string) =>
    request.delete(`/rag/admin/documents/${collectionKey}/${id}`).then((r) => r.data),
};
