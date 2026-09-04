import axios, { AxiosError } from 'axios';
import { message as staticMessage } from 'antd';
import { storage } from '../utils/storage';

/**
 * 扩展 axios config，支持自定义 silent 字段：
 * 调用方设 silent: true 时，响应拦截器跳过全局错误弹窗（由调用方自行处理）。
 */
declare module 'axios' {
  interface AxiosRequestConfig {
    silent?: boolean;
  }
}

// ---------------------------------------------------------------------------
// 401 全局去重：确保并发/串行 401 只弹一次"登录过期"提示
// 页面刷新后 flag 自动重置（模块级变量随页面加载重新初始化）
// ---------------------------------------------------------------------------
let hasShown401Warning = false;

/** 重置 401 提示状态（登录成功后调用） */
export function reset401Warning() {
  hasShown401Warning = false;
}

/**
 * axios 实例
 * - 统一 baseURL（VITE_API_BASE）
 * - 请求拦截：注入 Authorization: Bearer <token>
 * - 响应拦截：统一错误处理（401 跳登录）
 */
const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 15000,
});

// 请求拦截：注入 token
request.interceptors.request.use((config) => {
  const token = storage.get('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：统一错误处理
request.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<{ detail?: string }>) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail || '请求失败';

    // 调用方可通过 config.silent 跳过全局错误弹窗（如对话自行处理错误展示）
    const silent: boolean | undefined = error.config?.silent;

    if (status === 401) {
      // 登录/注册接口的 401 表示"凭据错误"（邮箱或密码错误），不是 token 过期：
      // 不清登录态、不弹"登录已过期"、不触发 logout，直接展示后端返回的原因
      const url = error.config?.url || '';
      const isAuthRequest = url.includes('/auth/login') || url.includes('/auth/register');
      if (isAuthRequest) {
        if (!silent) staticMessage.error(detail);
        return Promise.reject(error);
      }
      // token 失效，清除并提示
      storage.remove('token');
      if (!hasShown401Warning) {
        hasShown401Warning = true;
        staticMessage.error('登录已过期，请重新登录');
      }
      // 同步清除前端状态（动态导入避免循环依赖）
      import('../stores/authStore').then(({ useAuthStore }) => {
        useAuthStore.getState().logout();
      });
    } else if (status === 403) {
      staticMessage.error('无权限执行此操作');
    } else if (status && status >= 500) {
      if (!silent) staticMessage.error('服务器异常，请稍后重试');
    } else {
      if (!silent) staticMessage.error(detail);
    }
    return Promise.reject(error);
  },
);

export default request;
