import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, App as AntdApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import 'antd/dist/reset.css';
import './styles/global.css';
import App from './App';
import { router } from './router';
import { useUiStore } from './stores/uiStore';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30 * 1000,
    },
  },
});

function Root() {
  const antdTheme = useUiStore((s) => s.antdTheme);
  return (
    <StrictMode>
      <ConfigProvider theme={antdTheme} locale={zhCN}>
        <AntdApp>
          <QueryClientProvider client={queryClient}>
            <App>
              <RouterProvider router={router} />
            </App>
          </QueryClientProvider>
        </AntdApp>
      </ConfigProvider>
    </StrictMode>
  );
}

createRoot(document.getElementById('root')!).render(<Root />);
