import { useEffect, type PropsWithChildren } from 'react';
import { useAuthStore } from './stores/authStore';

/**
 * 应用根组件
 * 全局 ConfigProvider / QueryClientProvider / 路由已在 main.tsx 注入。
 * 此处负责：启动时加载当前登录用户（若有 token）。
 */
export default function App({ children }: PropsWithChildren) {
  const initAuth = useAuthStore((s) => s.initAuth);

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  return <>{children}</>;
}
