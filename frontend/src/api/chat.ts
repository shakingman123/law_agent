import request from './request';
import type { Citation } from './conversations';
import { storage } from '../utils/storage';

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

/** 流式 meta 事件 */
export interface StreamMeta {
  conversation_id: number;
  rag_sources: Citation[];
}

/** 流式 done 事件 */
export interface StreamDone {
  message_id: number;
  conversation_id: number;
}

/** 流式回调 */
export interface StreamCallbacks {
  onMeta?: (meta: StreamMeta) => void;
  onToken?: (token: string) => void;
  onDone?: (data: StreamDone) => void;
  onError?: (error: string) => void;
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
  /** 流式对话（SSE）。返回取消函数 */
  streamMessage: (
    payload: ChatMessagePayload,
    callbacks: StreamCallbacks,
  ): (() => void) => {
    const controller = new AbortController();
    const baseURL = import.meta.env.VITE_API_BASE || '/api';
    const token = storage.get('token');

    (async () => {
      try {
        const resp = await fetch(`${baseURL}/chat/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          callbacks.onError?.(`请求失败（${resp.status}）`);
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const events = buffer.split('\n\n');
          buffer = events.pop() ?? '';

          for (const event of events) {
            for (const line of event.split('\n')) {
              if (!line.startsWith('data:')) continue;
              const raw = line.slice(5).trim();
              if (!raw) continue;
              try {
                const data = JSON.parse(raw) as {
                  type: string;
                  content?: string;
                  error?: string;
                  conversation_id?: number;
                  message_id?: number;
                  rag_sources?: Citation[];
                };
                switch (data.type) {
                  case 'meta':
                    callbacks.onMeta?.({
                      conversation_id: data.conversation_id ?? 0,
                      rag_sources: data.rag_sources ?? [],
                    });
                    break;
                  case 'token':
                    if (data.content) callbacks.onToken?.(data.content);
                    break;
                  case 'done':
                    callbacks.onDone?.({
                      message_id: data.message_id ?? 0,
                      conversation_id: data.conversation_id ?? 0,
                    });
                    break;
                  case 'error':
                    callbacks.onError?.(data.error ?? '流式对话失败');
                    break;
                }
              } catch {
                // 忽略无法解析的数据行
              }
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          callbacks.onError?.('网络请求失败');
        }
      }
    })();

    return () => controller.abort();
  },

};
