import request from './request';

/** 知识库引用（结构化） */
export interface Citation {
  index: number;
  title: string;
  source: string;
  content: string;
}

/** 消息（后端持久化） */
export interface ChatMessage {
  id: number;
  conversation_id: number;
  role: 'user' | 'agent';
  content: string;
  attachments: { url: string }[];
  rag_sources: Citation[];
  created_at: string;
}

/** 会话 */
export interface Conversation {
  id: number;
  title: string;
  user_id: number;
  case_id: number | null;
  last_message_at: string | null;
  created_at: string;
}

/** 会话 + 历史消息 */
export interface ConversationWithMessages extends Conversation {
  messages: ChatMessage[];
}

export const conversationsApi = {
  list: () =>
    request.get<Conversation[]>('/conversations').then((r) => r.data),

  create: (payload: { title?: string; case_id?: number }) =>
    request.post<Conversation>('/conversations', payload).then((r) => r.data),

  /** 获取会话详情 + 全部历史消息 */
  get: (id: number) =>
    request.get<ConversationWithMessages>(`/conversations/${id}`).then((r) => r.data),

  messages: (id: number) =>
    request.get<ChatMessage[]>(`/conversations/${id}/messages`).then((r) => r.data),

  remove: (id: number) =>
    request.delete(`/conversations/${id}`).then((r) => r.data),
};
