import request from './request';
import type { Citation } from './conversations';

/** 通用对话 */
export interface ChatMessagePayload {
  message: string;
  conversation_id?: number;
  case_id?: number;
  case_name?: string;
  attachments?: string[];
  use_rag?: boolean;
}

export interface ChatMessageResult {
  reply: string;
  rag_sources: Citation[];
  conversation_id: number;
  message_id: number;
  error: string;
}

/** 启动文书撰写流程 */
export interface DraftPayload {
  user_input: string;
  case_id?: number;
  case_name?: string;
  template_id?: number;
}

export interface DraftResult {
  thread_id: string;
  doc_type: string;
  draft: string;
  missing_fields: string[];
  awaiting_review: boolean;
  done: boolean;
  file_url: string;     // docx 下载 URL
  pdf_url: string;      // pdf 下载 URL
  error: string;
}

/** 用户确认/微调后恢复 */
export interface ResumePayload {
  confirmed: boolean;
  feedback?: string;
}

// LLM 调用普遍较慢（DeepSeek 等可达数十秒），对话/文书请求单独放宽超时
const LLM_TIMEOUT = 120000;

export const chatApi = {
  /** 通用对话（接入 LLM + RAG）。错误由 ChatBox 自行展示，跳过全局弹窗 */
  sendMessage: (payload: ChatMessagePayload) =>
    request
      .post<ChatMessageResult>('/chat/message', payload, {
        timeout: LLM_TIMEOUT,
        silent: true,
      })
      .then((r) => r.data),

  /** 启动文书撰写流程 */
  startDraft: (payload: DraftPayload) =>
    request
      .post<DraftResult>('/chat/draft', payload, { timeout: LLM_TIMEOUT })
      .then((r) => r.data),

  /** 确认/微调后恢复文书流程 */
  resumeDraft: (threadId: string, payload: ResumePayload) =>
    request
      .post<DraftResult>(`/chat/draft/${threadId}/resume`, payload, {
        timeout: LLM_TIMEOUT,
      })
      .then((r) => r.data),
};
