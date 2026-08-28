import { createHashRouter, Navigate } from 'react-router-dom';
import AppLayout from '../layouts/AppLayout';
import Workbench from '../pages/workbench';
import Calendar from '../pages/calendar';
import DocLib from '../pages/doclib';
import CaseDetail from '../pages/case-detail';
import Settings from '../pages/settings';
import Developer from '../pages/developer';

/**
 * 路由配置
 * 依据 readme.md 四大功能：工作台 / 日程列表 / 文档库 / 设置
 * 工作台为默认入口（主界面，撰写文书与其他功能跳转中心）
 * 案件详情页从工作台案件栏或文档库进入
 * /developer 为平台开发者控制台（独立布局，仅开发者可进）
 *
 * 后续若需按页拆 bundle，将页面改为 lazy() + Suspense 即可
 */
export const router = createHashRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/workbench" replace /> },
      { path: 'workbench', element: <Workbench /> },
      { path: 'calendar', element: <Calendar /> },
      { path: 'doclib', element: <DocLib /> },
      { path: 'cases/:id', element: <CaseDetail /> },
      { path: 'settings', element: <Settings /> },
    ],
  },
  { path: '/developer', element: <Developer /> },
]);
