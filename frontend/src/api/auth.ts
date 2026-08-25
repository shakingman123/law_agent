import request from './request';

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  company_name?: string;
}

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  company_id: string | null;
  company_name: string;
  role: string;
  is_admin: boolean;
  avatar?: string;
  llm_source: 'company' | 'personal';
}

export interface AuthResult {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface AdminRequestPayload {
  company_name: string;
  reason?: string;
  business_license_url: string;
  legal_person_auth_url: string;
}

export interface AdminRequest {
  id: number;
  user_id: number;
  user_name: string;
  company_id: number;
  company_name: string;
  status: 'pending' | 'approved' | 'rejected';
  reason?: string;
  business_license_url?: string;
  legal_person_auth_url?: string;
  created_at: string;
  reviewed_at?: string;
  reviewed_by?: number;
}

export interface CompanyAdminStatus {
  company_id: number;
  company_name: string;
  has_admin: boolean;
  admin_name?: string;
}

export interface InviteCode {
  company_id: number;
  company_name: string;
  invite_code: string | null;
}

export interface JoinRequest {
  id: number;
  user_id: number;
  user_name: string;
  user_email: string;
  company_id: number;
  company_name: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  reviewed_at?: string | null;
}

export const authApi = {
  login: (payload: LoginPayload) =>
    request.post<AuthResult>('/auth/login', payload).then((r) => r.data),

  register: (payload: RegisterPayload) =>
    request.post<AuthResult>('/auth/register', payload).then((r) => r.data),

  getMe: () => request.get<AuthUser>('/auth/me').then((r) => r.data),

  getCompanyAdminStatus: (companyName: string) =>
    request
      .get<CompanyAdminStatus>('/auth/company-admin-status', {
        params: { company_name: companyName },
      })
      .then((r) => r.data),

  createAdminRequest: (payload: AdminRequestPayload) =>
    request.post<AdminRequest>('/auth/admin-request', payload).then((r) => r.data),

  getMyAdminRequest: () =>
    request.get<AdminRequest | null>('/auth/admin-request').then((r) => r.data),

  // ---- 邀请码 / 员工加入 ----
  getInviteCode: () =>
    request.get<InviteCode>('/auth/company/invite-code').then((r) => r.data),

  regenerateInviteCode: () =>
    request
      .post<InviteCode>('/auth/company/invite-code/regenerate')
      .then((r) => r.data),

  applyJoinCompany: (inviteCode: string) =>
    request
      .post<JoinRequest>('/auth/company/join', { invite_code: inviteCode })
      .then((r) => r.data),

  listJoinRequests: () =>
    request.get<JoinRequest[]>('/auth/company/join-requests').then((r) => r.data),

  approveJoinRequest: (reqId: number) =>
    request
      .post<JoinRequest>(`/auth/company/join-requests/${reqId}/approve`)
      .then((r) => r.data),

  rejectJoinRequest: (reqId: number) =>
    request
      .post<JoinRequest>(`/auth/company/join-requests/${reqId}/reject`)
      .then((r) => r.data),
};
