import { create } from 'zustand';
import { casesApi, type Case, type CaseCreatePayload } from '../api/cases';

/**
 * 案件 Store
 * - recentCases: 工作台案件栏展示的最近 1 周案件
 * - allCases: 文档库展示的全部案件
 * - currentCaseId: 当前选中案件（对话上下文用）
 */
interface CaseState {
  recentCases: Case[];
  allCases: Case[];
  currentCaseId: number | null;
  loading: boolean;

  loadRecent: () => Promise<void>;
  loadAll: () => Promise<void>;
  createCase: (payload: CaseCreatePayload, files?: File[]) => Promise<Case>;
  selectCase: (id: number | null) => void;
  getCurrentCase: () => Case | null;
}

export const useCaseStore = create<CaseState>((set, get) => ({
  recentCases: [],
  allCases: [],
  currentCaseId: null,
  loading: false,

  loadRecent: async () => {
    set({ loading: true });
    try {
      const cases = await casesApi.recent();
      // 按 id 去重，相同案件只出现一次
      const seen = new Set<number>();
      const deduped = cases.filter((c) => {
        if (seen.has(c.id)) return false;
        seen.add(c.id);
        return true;
      });
      set({ recentCases: deduped, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  loadAll: async () => {
    set({ loading: true });
    try {
      const cases = await casesApi.list();
      set({ allCases: cases, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  createCase: async (payload, files) => {
    const created = await casesApi.create(payload);
    if (files && files.length > 0) {
      await Promise.all(files.map((f) => casesApi.uploadDocument(created.id, f)));
    }
    set((s) => {
      // 去重：如果新案件已在列表中（不太可能但防御性处理），先移除旧的
      const filtered = s.recentCases.filter((c) => c.id !== created.id);
      return {
        recentCases: [created, ...filtered],
        allCases: [created, ...s.allCases.filter((c) => c.id !== created.id)],
        currentCaseId: created.id,
      };
    });
    return created;
  },

  selectCase: (id) => {
    set({ currentCaseId: id });
    if (id !== null) {
      casesApi.touch(id).catch(() => undefined);
    }
  },

  getCurrentCase: () => {
    const id = get().currentCaseId;
    const pool = get().recentCases.length ? get().recentCases : get().allCases;
    return pool.find((c) => c.id === id) || null;
  },
}));
