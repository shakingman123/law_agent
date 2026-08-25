import { create } from 'zustand';
import {
  llmApi,
  type Provider,
  type LlmSource,
  type AccessStatus,
  type CompanyLlmConfig as ApiCompanyConfig,
  type PersonalLlmConfig as ApiPersonalConfig,
  type AccessRequest as ApiAccessRequest,
  type UsageRecord as ApiUsageRecord,
  type MyUsageResponse,
} from '../api/llm';

/**
 * LLM 配置与用量 Store
 * 依据 implementation-guide.md §4：
 *   - 公司 API 由管理员配置，员工申请、管理员审核后可使用
 *   - 个人 API 员工自行填设
 *   - 管理员可查看每个员工的用量
 *   - Key 接口只回掩码（sk-••••f2a）
 *
 * 所有数据通过后端接口获取/提交，store 仅做缓存与字段映射
 * (后端 snake_case <-> 前端 camelCase)
 */

export type { Provider, LlmSource, AccessStatus };

export interface CompanyLlmConfig {
  isActive: boolean;
  provider: Provider;
  baseUrl: string;
  apiKeyMasked: string;
  models: string[];
  monthlyBudget: number;
}

export interface PersonalLlmConfig {
  isActive: boolean;
  provider: Provider;
  baseUrl: string;
  apiKeyMasked: string;
  models: string[];
}

export interface AccessRequest {
  id: number;
  userId: number;
  userName: string;
  status: AccessStatus;
  reason?: string;
  createdAt: string;
  reviewedAt?: string;
}

export interface UsageRecord {
  userId: number;
  userName: string;
  source: LlmSource;
  provider: Provider;
  model: string;
  calls: number;
  promptTokens: number;
  completionTokens: number;
  cost: number;
  quotaLimit: number;
}

export interface MyUsage extends UsageRecord {
  quotaUsedRatio: number;
}

interface SaveCompanyPayload {
  provider: Provider;
  baseUrl: string;
  apiKey?: string;
  models: string[];
  monthlyBudget: number;
}

interface SavePersonalPayload {
  provider: Provider;
  baseUrl: string;
  apiKey: string;
  models: string[];
}

interface LlmState {
  companyConfig: CompanyLlmConfig | null;
  personalConfig: PersonalLlmConfig | null;
  accessRequest: AccessRequest | null;
  usageRecords: UsageRecord[];
  myUsage: MyUsage | null;
  loading: boolean;

  /** 加载全部（按是否管理员拉取不同范围） */
  loadAll: (isAdmin: boolean) => Promise<void>;
  setCompanyConfig: (payload: SaveCompanyPayload) => Promise<void>;
  setPersonalConfig: (payload: SavePersonalPayload) => Promise<void>;
  switchSource: (source: LlmSource) => Promise<void>;
  requestCompanyAccess: (reason?: string) => Promise<void>;
  approveRequest: (id: number, approved: boolean) => Promise<void>;
  setQuotaLimit: (userId: number, limit: number) => Promise<void>;
}

// ===== 后端 snake_case -> 前端 camelCase 映射 =====
const mapCompany = (c: ApiCompanyConfig): CompanyLlmConfig => ({
  isActive: c.is_active,
  provider: c.provider,
  baseUrl: c.base_url,
  apiKeyMasked: c.api_key_masked,
  models: c.models,
  monthlyBudget: c.monthly_budget,
});

const mapPersonal = (c: ApiPersonalConfig): PersonalLlmConfig => ({
  isActive: c.is_active,
  provider: c.provider,
  baseUrl: c.base_url,
  apiKeyMasked: c.api_key_masked,
  models: c.models,
});

const mapAccess = (a: ApiAccessRequest): AccessRequest => ({
  id: a.id,
  userId: a.user_id,
  userName: a.user_name,
  status: a.status,
  reason: a.reason,
  createdAt: a.created_at,
  reviewedAt: a.reviewed_at,
});

const mapUsage = (u: ApiUsageRecord): UsageRecord => ({
  userId: u.user_id,
  userName: u.user_name,
  source: u.source,
  provider: u.provider,
  model: u.model,
  calls: u.calls,
  promptTokens: u.prompt_tokens,
  completionTokens: u.completion_tokens,
  cost: u.cost,
  quotaLimit: u.quota_limit,
});

/** 后端 /usage/me 返回 {records, totals, quota}，需拍平为 MyUsage */
const mapMyUsage = (u: MyUsageResponse): MyUsage => {
  const t = u.totals ?? { calls: 0, prompt_tokens: 0, completion_tokens: 0, cost: 0 };
  const q = u.quota;
  const first = u.records?.[0];
  return {
    userId: first?.user_id ?? '',
    userName: first?.user_name ?? '',
    source: first?.source ?? 'company',
    provider: first?.provider ?? 'openai',
    model: first?.model ?? '',
    calls: t.calls ?? 0,
    promptTokens: t.prompt_tokens ?? 0,
    completionTokens: t.completion_tokens ?? 0,
    cost: t.cost ?? 0,
    quotaLimit: q?.quota_limit ?? 0,
    quotaUsedRatio: q && q.quota_limit > 0 ? Math.round((q.used / q.quota_limit) * 100) : 0,
  };
};

export const useLlmStore = create<LlmState>((set, get) => ({
  companyConfig: null,
  personalConfig: null,
  accessRequest: null,
  usageRecords: [],
  myUsage: null,
  loading: false,

  loadAll: async (isAdmin) => {
    set({ loading: true });
    try {
      const [company, personal, , myUsage] = await Promise.all([
        llmApi.getCompanyConfig().catch(() => null),
        llmApi.getPersonalConfig().catch(() => null),
        llmApi.getSource().catch(() => null),
        llmApi.getMyUsage().catch(() => null),
      ]);
      const next: Partial<LlmState> = { loading: false };
      if (company) next.companyConfig = mapCompany(company);
      if (personal) next.personalConfig = mapPersonal(personal);
      if (myUsage) next.myUsage = mapMyUsage(myUsage);

      // 管理员额外加载全员用量与待审批
      if (isAdmin) {
        const [usage, requests] = await Promise.all([
          llmApi.getCompanyUsage().catch(() => []),
          llmApi.listAccessRequests().catch(() => []),
        ]);
        next.usageRecords = usage.map(mapUsage);
        // 管理员看板直接存所有待审批申请，LlmApiPanel 渲染列表
        const pending = requests.filter((r) => r.status === 'pending');
        if (pending.length > 0) {
          // 取第一条作为 accessRequest 兼容旧 UI（后续应改为列表渲染）
          next.accessRequest = mapAccess(pending[0]);
        }
      }
      set(next);
    } catch {
      set({ loading: false });
    }
  },

  setCompanyConfig: async (payload) => {
    const data = await llmApi.saveCompanyConfig({
      provider: payload.provider,
      base_url: payload.baseUrl,
      api_key: payload.apiKey,
      models: payload.models,
      monthly_budget: payload.monthlyBudget,
      is_active: true, // 保存即启用
    });
    set({ companyConfig: mapCompany(data) });
  },

  setPersonalConfig: async (payload) => {
    const data = await llmApi.savePersonalConfig({
      provider: payload.provider,
      base_url: payload.baseUrl,
      api_key: payload.apiKey,
      models: payload.models,
      is_active: true, // 保存即启用
    });
    set({ personalConfig: mapPersonal(data) });
  },

  switchSource: async (source) => {
    await llmApi.switchSource(source);
    // 同步 myUsage 的 source 字段
    const my = get().myUsage;
    if (my) set({ myUsage: { ...my, source } });
  },

  requestCompanyAccess: async (reason) => {
    const data = await llmApi.createAccessRequest(reason);
    set({ accessRequest: mapAccess(data) });
  },

  approveRequest: async (id, approved) => {
    const data = await llmApi.reviewAccessRequest(id, approved);
    // 若审批的是当前用户的申请，同步更新
    if (get().accessRequest?.id === id) {
      set({ accessRequest: mapAccess(data) });
    }
  },

  setQuotaLimit: async (userId, limit) => {
    await llmApi.setQuotaLimit(userId, limit);
    set((s) => ({
      usageRecords: s.usageRecords.map((r) =>
        r.userId === userId ? { ...r, quotaLimit: limit } : r,
      ),
    }));
  },
}));
