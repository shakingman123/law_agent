import { create } from 'zustand';
import { conversationsApi, type Conversation, type ChatMessage, type Citation } from '../api/conversations';

/**
 * 对话 Store
 * - currentConversationId: 当前会话 id（全局保持，切页面不丢）
 * - messages: 当前会话的历史消息（从后端加载，切换会话时刷新）
 * - loadedUserId: 已加载历史的用户 ID，防止用户切换时展示错误数据
 *
 * 登录/登出行为：
 * - 登录后：只加载会话列表，不自动选中/加载任何历史会话 → 用户从空白开始
 * - 登出后：reset() 清空所有状态 + sessionStorage 中的会话ID
 * - 同一会话内切页面：loadedUserId 未变，跳过重复请求
 * - 刷新页面：从 sessionStorage 恢复 currentConversationId 并加载对应消息
 *
 * 竞态防护：
 * - init() / selectConversation() 在 await 后检查 loadedUserId !== userId，
 *   若用户已登出或切换则丢弃结果。
 */
interface ChatState {
  conversations: Conversation[];
  currentConversationId: number | null;
  messages: ChatMessage[];
  loadedUserId: string | null;
  loading: boolean;

  init: (userId: string) => Promise<void>;
  selectConversation: (id: number) => Promise<void>;
  createConversation: () => Promise<void>;
  appendLocalMessage: (msg: ChatMessage) => void;
  updateLastAgentMessage: (content: string, ragSources?: Citation[], conversationId?: number) => void;
  reset: () => void;
}

const SESSION_CONV_ID = 'chat.currentConversationId';

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  loadedUserId: null,
  loading: false,

  init: async (userId: string) => {
    if (get().loadedUserId === userId) return;

    set({ loading: true, loadedUserId: userId });
    try {
      const list = await conversationsApi.list();
      if (get().loadedUserId !== userId) return;

      // 刷新场景：从 sessionStorage 恢复上次的会话 ID
      const savedIdStr = sessionStorage.getItem(SESSION_CONV_ID);
      const savedId = savedIdStr ? parseInt(savedIdStr, 10) : null;
      let currentId: number | null = null;
      let messages: ChatMessage[] = [];

      if (savedId && list.find((c) => c.id === savedId)) {
        // 恢复上次的会话，加载其消息
        currentId = savedId;
        try {
          const detail = await conversationsApi.get(savedId);
          if (get().loadedUserId !== userId) return;
          messages = detail.messages;
        } catch {
          // 恢复失败不阻塞
        }
      }

      set({
        conversations: list,
        currentConversationId: currentId,
        messages,
        loading: false,
      });
    } catch {
      if (get().loadedUserId === userId) {
        set({ loading: false });
      }
    }
  },

  reset: () => {
    sessionStorage.removeItem(SESSION_CONV_ID);
    set({
      conversations: [],
      currentConversationId: null,
      messages: [],
      loadedUserId: null,
      loading: false,
    });
  },

  selectConversation: async (id) => {
    const userId = get().loadedUserId;
    set({ currentConversationId: id, loading: true });
    try {
      const detail = await conversationsApi.get(id);
      if (get().loadedUserId !== userId) return;
      sessionStorage.setItem(SESSION_CONV_ID, String(id));
      set({ messages: detail.messages, loading: false });
    } catch {
      if (get().loadedUserId === userId) {
        set({ loading: false });
      }
    }
  },

  createConversation: async () => {
    const conv = await conversationsApi.create({ title: '新对话' });
    sessionStorage.setItem(SESSION_CONV_ID, String(conv.id));
    set((s) => ({
      conversations: [conv, ...s.conversations],
      currentConversationId: conv.id,
      messages: [],
    }));
  },

  appendLocalMessage: (msg) => {
    set((s) => ({ messages: [...s.messages, msg] }));
  },

  updateLastAgentMessage: (content, ragSources, conversationId) => {
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'agent') {
          msgs[i] = { ...msgs[i], content, rag_sources: ragSources ?? msgs[i].rag_sources };
          break;
        }
      }
      return {
        messages: msgs,
        currentConversationId: conversationId ?? s.currentConversationId,
      };
    });
  },
}));
