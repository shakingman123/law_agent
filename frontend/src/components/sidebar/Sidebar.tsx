import { Layout, Menu } from 'antd';
import {
  CalendarOutlined,
  FileTextOutlined,
  EditOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import type { MenuProps } from 'antd';
import UserCard from './UserCard';
import { colors } from '../../theme/tokens';

const { Sider } = Layout;

type MenuItem = Required<MenuProps>['items'][number];

const menuItems: MenuItem[] = [
  { key: '/workbench', icon: <EditOutlined />, label: '工作台' },
  { key: '/calendar', icon: <CalendarOutlined />, label: '日程列表' },
  { key: '/doclib', icon: <FileTextOutlined />, label: '文档库' },
];

/**
 * 左侧列表栏
 * 依据 figma-design-spec.md §3：224px 宽，#F8FAFC 底色，导航项高 38，
 * 激活态 Primary-Bg 圆角 8；底部用户卡片
 */
export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const selectedKey = '/' + (location.pathname.split('/')[1] || 'workbench');

  return (
    <Sider
      width={224}
      theme="light"
      style={{
        background: colors.sidebarBg,
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        borderRight: `1px solid ${colors.border}`,
      }}
    >
      <div
        style={{
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 700,
          fontSize: 16,
          color: colors.primary,
        }}
      >
        法律文书 Agent
      </div>
      <Menu
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={({ key }) => navigate(key)}
        style={{
          borderInlineEnd: 'none',
          background: 'transparent',
          flex: 1,
        }}
      />
      <UserCard />
    </Sider>
  );
}
