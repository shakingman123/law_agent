import { useState } from 'react';
import { Avatar, Typography, Modal, Tabs, Form, Input, Button, App } from 'antd';
import { SettingOutlined, UserOutlined, LogoutOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { colors } from '../../theme/tokens';

/**
 * 左下用户卡片
 * 依据 figma-design-spec.md §3：38px 头像 + 姓名 + 公司 + 齿轮按钮
 * - 未登录时显示「未登录」+ 登录按钮（弹出登录/注册）
 * - 点击齿轮跳转设置页
 */
export default function UserCard() {
  const { user, login, register, logout } = useAuthStore();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [authOpen, setAuthOpen] = useState(false);
  const [loginForm] = Form.useForm();
  const [regForm] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const handleLogin = async () => {
    try {
      const v = await loginForm.validateFields();
      setSubmitting(true);
      await login(v.email, v.password);
      message.success('登录成功');
      setAuthOpen(false);
      loginForm.resetFields();
    } catch {
      /* 校验或请求失败 */
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegister = async () => {
    try {
      const v = await regForm.validateFields();
      setSubmitting(true);
      await register({
        name: v.name,
        email: v.email,
        password: v.password,
      });
      message.success('注册成功');
      setAuthOpen(false);
      regForm.resetFields();
    } catch {
      /* 校验或请求失败 */
    } finally {
      setSubmitting(false);
    }
  };

  if (!user) {
    return (
      <>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 16px',
            borderTop: `1px solid ${colors.border}`,
          }}
        >
          <Avatar size={38} icon={<UserOutlined />} style={{ backgroundColor: colors.muted }} />
          <Button type="primary" size="small" onClick={() => setAuthOpen(true)}>
            登录 / 注册
          </Button>
        </div>
        <Modal
          title="登录法律文书 Agent"
          open={authOpen}
          onCancel={() => setAuthOpen(false)}
          footer={null}
          width={420}
        >
          <Tabs
            items={[
              {
                key: 'login',
                label: '登录',
                children: (
                  <Form form={loginForm} layout="vertical" style={{ marginTop: 8 }}>
                    <Form.Item name="email" label="邮箱" rules={[{ required: true }]}>
                      <Input placeholder="you@example.com" />
                    </Form.Item>
                    <Form.Item name="password" label="密码" rules={[{ required: true }]}>
                      <Input.Password />
                    </Form.Item>
                    <Button type="primary" block loading={submitting} onClick={handleLogin}>
                      登录
                    </Button>
                  </Form>
                ),
              },
              {
                key: 'register',
                label: '注册',
                children: (
                  <Form form={regForm} layout="vertical" style={{ marginTop: 8 }}>
                    <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item name="email" label="邮箱" rules={[{ required: true }]}>
                      <Input placeholder="you@example.com" />
                    </Form.Item>
                    <Form.Item name="password" label="密码" rules={[{ required: true }]}>
                      <Input.Password />
                    </Form.Item>
                    <Button type="primary" block loading={submitting} onClick={handleRegister}>
                      注册
                    </Button>
                  </Form>
                ),
              },
            ]}
          />
        </Modal>
      </>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '12px 16px',
        borderTop: `1px solid ${colors.border}`,
      }}
    >
      <Avatar size={38} style={{ backgroundColor: colors.primary, flexShrink: 0 }}>
        {user.name[0]}
      </Avatar>
      <div style={{ flex: 1, marginLeft: 12, overflow: 'hidden' }}>
        <Typography.Text strong ellipsis style={{ display: 'block', fontSize: 14 }}>
          {user.name}
          {user.isAdmin && (
            <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>
              管理员
            </Typography.Text>
          )}
        </Typography.Text>
        <Typography.Text type="secondary" ellipsis style={{ fontSize: 12 }}>
          {user.company}
        </Typography.Text>
      </div>
      <SettingOutlined
        style={{ color: colors.muted, fontSize: 16, cursor: 'pointer', marginRight: 12 }}
        onClick={() => navigate('/settings')}
      />
      <LogoutOutlined
        style={{ color: colors.muted, fontSize: 15, cursor: 'pointer' }}
        onClick={() => {
          Modal.confirm({
            title: '确认退出登录？',
            content: '退出后需要重新登录才能继续使用',
            okText: '退出登录',
            okType: 'danger',
            cancelText: '取消',
            onOk: () => {
              logout();
              message.success('已退出登录');
              navigate('/');
            },
          });
        }}
      />
    </div>
  );
}
