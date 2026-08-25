import request from './request';

export interface FileUploadResult {
  url: string;
  file_name: string;
  file_size: number;
  file_type: string;
}

export const filesApi = {
  upload: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request
      .post<FileUploadResult>('/files/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },
};
