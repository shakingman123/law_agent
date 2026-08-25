import request from './request';

/** 案件文档 */
export interface CaseDocument {
  id: number;
  case_id: number;
  file_name: string;
  file_url: string;
  file_type: string | null;
  file_size: number;
  uploaded_by: number;
  created_at: string;
}

/** 案件 */
export interface Case {
  id: number;
  name: string;
  plaintiff: string;
  defendant: string;
  court: string;
  summary: string | null;
  scope: 'private' | 'public';
  owner_id: number;
  company_id: number | null;
  last_opened_at: string | null;
  created_at: string;
  updated_at: string;
  documents: CaseDocument[];
}

export interface CaseCreatePayload {
  name: string;
  plaintiff: string;
  defendant: string;
  court: string;
  summary?: string;
  scope?: 'private' | 'public';
}

export const casesApi = {
  create: (payload: CaseCreatePayload) =>
    request.post<Case>('/cases', payload).then((r) => r.data),

  recent: () => request.get<Case[]>('/cases/recent').then((r) => r.data),

  list: () => request.get<Case[]>('/cases').then((r) => r.data),

  get: (id: number) => request.get<Case>(`/cases/${id}`).then((r) => r.data),

  touch: (id: number) =>
    request.post<Case>(`/cases/${id}/touch`).then((r) => r.data),

  uploadDocument: (id: number, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request
      .post<CaseDocument>(`/cases/${id}/documents`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },
};
