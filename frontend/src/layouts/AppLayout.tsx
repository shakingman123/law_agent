import { Layout } from 'antd';
import { Outlet } from 'react-router-dom';
import Sidebar from '../components/sidebar/Sidebar';

const { Content } = Layout;

/**
 * 应用外壳布局
 * 依据 figma-design-spec.md §3：左 224 Sidebar + 右侧 Content(自适应)
 * 工作台专属的右侧案件栏(288) 由 workbench 页面内部布局
 */
export default function AppLayout() {
  return (
    <Layout style={{ height: '100vh' }}>
      <Sidebar />
      <Content style={{ overflow: 'auto', height: '100vh' }}>
        <Outlet />
      </Content>
    </Layout>
  );
}
