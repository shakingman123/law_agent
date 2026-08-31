import { lazy, Suspense } from 'react';
import { createHashRouter, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import AppLayout from '../layouts/AppLayout';

/**
 * 路由配置
 * 依据 readme.md 四大功能：工作台 / 日程列表 / 文档库 / 设置
 * 工作台为默认入口（主界面，撰写文书与其他功能跳转中心）
 * 案件详情页从工作台案件栏或文档库进入
 * /developer 为平台开发者控制台（独立布局，仅开发者可进）
 *
 * 页面组件全部 React.lazy 懒加载：按路由自动代码分割，首屏只加载工作台所需代码
 */
function PageLoading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <Spin size="large" tip="加载中..." />
    </div>
  );
}

const lazyPage = (loader: () => Promise<{ default: React.ComponentType }>) => {
  const Page = lazy(loader);
  return (
    <Suspense fallback={<PageLoading />}>
      <Page />
    </Suspense>
  );
};

export const router = createHashRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/workbench" replace /> },
      { path: 'workbench', element: lazyPage(() => import('../pages/workbench')) },
      { path: 'calendar', element: lazyPage(() => import('../pages/calendar')) },
      { path: 'doclib', element: lazyPage(() => import('../pages/doclib')) },
      { path: 'knowledge', element: lazyPage(() => import('../pages/knowledge')) },
      { path: 'cases/:id', element: lazyPage(() => import('../pages/case-detail')) },
      { path: 'settings', element: lazyPage(() => import('../pages/settings')) },
    ],
  },
  { path: '/developer', element: lazyPage(() => import('../pages/developer')) },
]);
