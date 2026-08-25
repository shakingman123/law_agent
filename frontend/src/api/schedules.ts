import request from './request';

/** 日程紧急程度：urgent 紧急 / normal 一般 / meeting 会议 */
export type ScheduleLevel = 'urgent' | 'normal' | 'meeting';

/** 日程项（对应后端 ScheduleOut） */
export interface ScheduleItem {
  id: number;
  user_id: number;
  title: string;
  date: string; // YYYY-MM-DD
  level: ScheduleLevel;
  /** 提前提醒天数：0=当天，n=提前 n 天，null=不提醒 */
  remind_advance?: number | null;
  case_name?: string | null;
  case_id?: number | null;
  created_at: string;
}

export interface ScheduleCreatePayload {
  title: string;
  date: string; // YYYY-MM-DD
  level: ScheduleLevel;
  remind_advance?: number | null;
  case_name?: string;
  case_id?: number;
}

export const schedulesApi = {
  list: () => request.get<ScheduleItem[]>('/schedules').then((r) => r.data),

  create: (payload: ScheduleCreatePayload) =>
    request.post<ScheduleItem>('/schedules', payload).then((r) => r.data),

  remove: (id: number) =>
    request.delete<{ ok: true }>(`/schedules/${id}`).then((r) => r.data),
};
