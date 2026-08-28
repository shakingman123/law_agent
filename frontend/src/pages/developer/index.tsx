import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  List,
  Button,
  Tag,
  Typography,
  Form,
  Input,
  App,
  Space,
  Empty,
} from 'antd';
import {
  SafetyCertificateOutlined,
  ReloadOutlined,
  CheckOutlined,
  CloseOutlined,
  FileTextOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { authApi, type DevOverview } from '../../api/auth';
import { colors } from '../../theme/tokens';

/**
 * 开发者控制台
 * 仅平台开发者可进入：查看已存在公司（管理员/邮箱/电话）+ 「成为公司管理员」申请，
 * 依据资料完整性批准或驳回申请。
 * 未登录时内联提供登录表单（开发者账号与普通账号共用 /api/auth/login）。
 */
export default function Developer() {
  const { user, login, logout } = useAuthStore();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [loginForm] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [overview, setOverview] = useState<DevOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [reviewingId, setReviewingId] = useState<number | null>(null);

  const loadOverview = async () => {
    setLoading(true);
    try {
      const data = await authApi.devOverview();
      setOverview(data);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.isDeveloper) {
      loadOverview();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.isDeveloper]);

  const handleLogin = async () => {
    try {
      const v = await loginForm.validateFields();
      setSubmitting(true);
      await login(v.email, v.password);
      const u = useAuthStore.getState().user;
      if (!u?.isDeveloper) {
        message.error('该账号不是平台开发者');
        logout();
        return;
      }
      message.success('登录成功');
    } catch {
      /* 校验或请求失败 */
    } finally {
      setSubmitting(false);
    }
  };

  const handleReview = async (id: number, action: 'approve' | 'reject') => {
    setReviewingId(id);
    try {
      if (action === 'approve') {
        await authApi.devApproveAdminRequest(id);
        message.success('已批准，该公司已创建并将申请人设为管理员');
      } else {
        await authApi.devRejectAdminRequest(id);
        message.success('已驳回申请');
      }
      loadOverview();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败');
    } finally {
      setReviewingId(null);
    }
  };

  // 未登录：内联登录表单
  if (!user) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: colors.primaryBg,
        }}
      >
        <Card style={{ width: 380 }}>
          <Space direction="vertical" size={4} style={{ marginBottom: 12 }}>
            <Typography.Title level={4} style={{ margin: 0 }}>
              <SafetyCertificateOutlined style={{ color: colors.primary, marginRight: 8 }} />
              开发者控制台
            </Typography.Title>
            <Typography.Text type="secondary">请使用平台开发者账号登录</Typography.Text>
          </Space>
          <Form form={loginForm} layout="vertical">
            <Form.Item name="email" label="邮箱" rules={[{ required: true }]}>
              <Input placeholder="developer@lawagent.com" onPressEnter={handleLogin} />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true }]}>
              <Input.Password onPressEnter={handleLogin} />
            </Form.Item>
            <Button type="primary" block loading={submitting} onClick={handleLogin}>
              登录
            </Button>
          </Form>
        </Card>
      </div>
    );
  }

  // 已登录但非开发者
  if (!user.isDeveloper) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Card style={{ width: 380, textAlign: 'center' }}>
          <Typography.Text>当前账号无开发者权限</Typography.Text>
          <div style={{ marginTop: 16 }}>
            <Button type="primary" onClick={() => navigate('/')}>
              返回工作台
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const pendingReqs = overview?.admin_requests.filter((r) => r.status === 'pending') ?? [];
  const reviewedReqs = overview?.admin_requests.filter((r) => r.status !== 'pending') ?? [];

  return (
    <div style={{ minHeight: '100vh', background: colors.primaryBg, padding: 24 }}>
      <div style={{ maxWidth: 1000, margin: '0 auto' }}>
        {/* 顶栏 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            <SafetyCertificateOutlined style={{ color: colors.primary, marginRight: 8 }} />
            开发者控制台
          </Typography.Title>
          <Space>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={loadOverview}>
              刷新
            </Button>
            <Button
              icon={<LogoutOutlined />}
              onClick={() => {
                logout();
                navigate('/');
              }}
            >
              退出登录
            </Button>
          </Space>
        </div>

        {/* 已存在公司 */}
        <Card title="已存在公司" size="small" style={{ marginBottom: 16 }}>
          <Table
            size="small"
            rowKey="id"
            loading={loading}
            dataSource={overview?.companies ?? []}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无公司" /> }}
            columns={[
              { title: '公司名称', dataIndex: 'name' },
              { title: '管理员', dataIndex: 'admin_name', render: (v) => v || '—' },
              { title: '管理员邮箱', dataIndex: 'admin_email', render: (v) => v || '—' },
              { title: '电话', dataIndex: 'admin_phone', render: (v) => v || '—' },
              { title: '成员数', dataIndex: 'member_count', width: 80 },
            ]}
          />
        </Card>

        {/* 待审批的管理员申请 */}
        <Card
          title={`成为公司管理员的申请${pendingReqs.length ? `（${pendingReqs.length} 条待审批）` : ''}`}
          size="small"
          style={{ marginBottom: 16 }}
        >
          <List
            loading={loading}
            dataSource={pendingReqs}
            locale={{ emptyText: '暂无待审批的申请' }}
            renderItem={(req) => (
              <List.Item
                actions={[
                  <Button
                    key="approve"
                    type="primary"
                    size="small"
                    icon={<CheckOutlined />}
                    loading={reviewingId === req.id}
                    onClick={() => handleReview(req.id, 'approve')}
                  >
                    批准
                  </Button>,
                  <Button
                    key="reject"
                    danger
                    size="small"
                    icon={<CloseOutlined />}
                    loading={reviewingId === req.id}
                    onClick={() => handleReview(req.id, 'reject')}
                  >
                    驳回
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space wrap>
                      <Typography.Text strong>{req.user_name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {req.user_email}
                      </Typography.Text>
                      <Tag color="blue">申请管理「{req.company_name}」</Tag>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={2}>
                      <Space wrap>
                        {req.business_license_url && (
                          <Button
                            size="small"
                            type="link"
                            icon={<FileTextOutlined />}
                            onClick={() => window.open(req.business_license_url!, '_blank')}
                          >
                            营业执照
                          </Button>
                        )}
                        {req.legal_person_auth_url && (
                          <Button
                            size="small"
                            type="link"
                            icon={<FileTextOutlined />}
                            onClick={() => window.open(req.legal_person_auth_url!, '_blank')}
                          >
                            法人授权书
                          </Button>
                        )}
                      </Space>
                      {req.reason && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          说明：{req.reason}
                        </Typography.Text>
                      )}
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        提交时间：{new Date(req.created_at).toLocaleString()}
                      </Typography.Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        </Card>

        {/* 已处理的申请 */}
        {reviewedReqs.length > 0 && (
          <Card title="已处理的申请" size="small">
            <List
              size="small"
              dataSource={reviewedReqs}
              renderItem={(req) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <Typography.Text>{req.user_name}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {req.user_email}
                        </Typography.Text>
                        <Tag color="blue">「{req.company_name}」</Tag>
                        <Tag color={req.status === 'approved' ? 'green' : 'red'}>
                          {req.status === 'approved' ? '已批准' : '已驳回'}
                        </Tag>
                      </Space>
                    }
                    description={
                      req.reviewed_at ? `处理时间：${new Date(req.reviewed_at).toLocaleString()}` : undefined
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        )}
      </div>
    </div>
  );
}
