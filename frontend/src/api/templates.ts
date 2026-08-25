import request from './request';

/** 文书模板 */
export interface DocTemplate {
  id: number;
  name: string;
  doc_type: string;
  content: string;
  placeholders: string[];
  scope: 'public' | 'private';
  user_id: number | null;
  created_at: string;
}

export interface ExtractResult {
  text: string;
  file_name: string;
  char_count: number;
}

export const templatesApi = {
  list: () => request.get<DocTemplate[]>('/templates').then((r) => r.data),

  create: (payload: {
    name: string;
    doc_type: string;
    content: string;
    placeholders?: string[];
  }) => request.post<DocTemplate>('/templates', payload).then((r) => r.data),

  remove: (id: number) => request.delete(`/templates/${id}`).then((r) => r.data),

  extractFile: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request
      .post<ExtractResult>('/templates/extract', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },
};
