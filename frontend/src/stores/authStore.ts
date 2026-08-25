import { create } from 'zustand';
import { authApi, type AuthUser } from '../api/auth';
import { reset401Warning } from '../api/request';
import { useChatStore } from './chatStore';
import { storage } from '../utils/storage';

/**
 * 当前用户
 * user 为 null 表示未登录（未获取到 token 或请求失败）
 * llmSource：当前使用的 LLM 来源（company / personal），由后端 /api/llm/source 维护
 */
export interface User {
  id: string;
  name: string;
  email?: string;
  company: string;
  companyId?: string;
  role: string;
  isAdmin: boolean;
  llmSource: 'company' | 'personal';
}

interface AuthState {
  user: User | null;
  loading: boolean;
  /** 启动时调用：有 token 则加载当前用户，失败则清空 */
  initAuth: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: {
    name: string;
    email: string;
    password: string;
    company_name?: string;
  }) => Promise<void>;
  logout: () => void;
  /** 本地同步更新（如切换 llmSource 后） */
  setUser: (u: Partial<User>) => void;
}

const mapUser = (u: AuthUser): User => ({
  id: u.id,
  name: u.name,
  email: u.email,
  company: u.company_name || '未加入公司',
  companyId: u.company_id ?? undefined,
  role: u.role,
  isAdmin: u.is_admin,
  llmSource: u.llm_source,
});

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: false,

  initAuth: async () => {
    const token = storage.get('token');
    if (!token) return;
    set({ loading: true });
    try {
      const u = await authApi.getMe();
      set({ user: mapUser(u), loading: false });
    } catch {
      storage.remove('token');
      set({ user: null, loading: false });
    }
  },

  login: async (email, password) => {
    const r = await authApi.login({ email, password });
    storage.set('token', r.access_token);
    reset401Warning();
    set({ user: mapUser(r.user) });
  },

  register: async (payload) => {
    const r = await authApi.register(payload);
    storage.set('token', r.access_token);
    reset401Warning();
    set({ user: mapUser(r.user) });
  },

  logout: () => {
    storage.remove('token');
    reset401Warning();
    useChatStore.getState().reset();
    set({ user: null });
  },

  setUser: (u) => set((s) => (s.user ? { user: { ...s.user, ...u } } : s)),
}));
