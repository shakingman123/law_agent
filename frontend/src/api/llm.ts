import request from './request';

export type Provider = 'openai' | 'azure' | 'qwen' | 'deepseek' | 'zhipu';
export type LlmSource = 'company' | 'personal';
export type AccessStatus = 'pending' | 'approved' | 'rejected';

/** 公司 LLM 配置（员工视角：只含掩码与启用状态） */
export interface CompanyLlmConfig {
  is_active: boolean;
  provider: Provider;
  base_url: string;
  api_key_masked: string;
  models: string[];
  monthly_budget: number;
}

/** 个人 LLM 配置 */
export interface PersonalLlmConfig {
  is_active: boolean;
  provider: Provider;
  base_url: string;
  api_key_masked: string;
  models: string[];
}

/** 保存配置请求体（apiKey 为明文，落库时加密） */
export interface SaveCompanyConfigPayload {
  is_active?: boolean;
  provider: Provider;
  base_url: string;
  api_key?: string; // 留空表示不修改
  models: string[];
  monthly_budget: number;
}

export interface SavePersonalConfigPayload {
  is_active?: boolean;
  provider: Provider;
  base_url: string;
  api_key: string;
  models: string[];
}

export interface AccessRequest {
  id: number;
  user_id: number;
  user_name: string;
  company_id: number;
  status: AccessStatus;
  reason?: string;
  created_at: string;
  reviewed_at?: string;
  reviewed_by?: number;
}

export interface UsageRecord {
  user_id: number;
  user_name: string;
  source: LlmSource;
  provider: Provider;
  model: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost: number;
  quota_limit: number;
}

/** 后端 /usage/me 实际返回的嵌套结构 */
export interface MyUsageResponse {
  records: UsageRecord[];
  totals: {
    calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost: number;
  };
  quota: {
    period: string;
    quota_limit: number;
    used: number;
    status: string;
  } | null;
}

export const llmApi = {
  // 公司配置
  getCompanyConfig: () =>
    request.get<CompanyLlmConfig>('/llm/config/company').then((r) => r.data),
  saveCompanyConfig: (payload: SaveCompanyConfigPayload) =>
    request.put<CompanyLlmConfig>('/llm/config/company', payload).then((r) => r.data),

  // 个人配置
  getPersonalConfig: () =>
    request.get<PersonalLlmConfig>('/llm/config/me').then((r) => r.data),
  savePersonalConfig: (payload: SavePersonalConfigPayload) =>
    request.put<PersonalLlmConfig>('/llm/config/me', payload).then((r) => r.data),

  // 使用方式切换
  getSource: () =>
    request.get<{ source: LlmSource }>('/llm/source').then((r) => r.data),
  switchSource: (source: LlmSource) =>
    request.put<{ source: LlmSource }>('/llm/source', { source }).then((r) => r.data),

  // 申请使用公司 API
  createAccessRequest: (reason?: string) =>
    request.post<AccessRequest>('/llm/access-request', { reason }).then((r) => r.data),

  // 管理员：待审批列表
  listAccessRequests: () =>
    request.get<AccessRequest[]>('/llm/access-requests').then((r) => r.data),

  // 管理员：审批
  reviewAccessRequest: (id: number, approved: boolean) =>
    request
      .put<AccessRequest>(`/llm/access-requests/${id}`, { action: approved ? 'approve' : 'reject' })
      .then((r) => r.data),

  // 用量
  getMyUsage: () => request.get<MyUsageResponse>('/llm/usage/me').then((r) => r.data),
  getCompanyUsage: () =>
    request.get<UsageRecord[]>('/llm/usage/company').then((r) => r.data),

  // 管理员：设置额度
  setQuotaLimit: (userId: number, limit: number) =>
    request
      .put<{ ok: true }>(`/llm/quotas/${userId}`, { quota_limit: limit })
      .then((r) => r.data),
};
