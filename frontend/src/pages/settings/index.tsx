import { useState } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Avatar,
  Menu,
  Typography,
  Segmented,
  Space,
  Divider,
  App,
  Switch,
  Upload,
  Tag,
  Alert,
  Modal,
} from 'antd';
import { UserOutlined, BgColorsOutlined, HomeOutlined, ApiOutlined, UploadOutlined, CrownOutlined, LogoutOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { useAuthStore } from '../../stores/authStore';
import { colors } from '../../theme/tokens';
import LlmApiPanel from '../../components/settings/LlmApiPanel';
import { authApi } from '../../api/auth';
import { useNavigate } from 'react-router-dom';

type Section = 'basic' | 'interface' | 'company' | 'llm';

const menuItems = [
  { key: 'basic', icon: <UserOutlined />, label: '基本信息' },
  { key: 'interface', icon: <BgColorsOutlined />, label: '界面设置' },
  { key: 'company', icon: <HomeOutlined />, label: '公司' },
  { key: 'llm', icon: <ApiOutlined />, label: '模型与 API' },
];

/**
 * 设置页
 * 依据 figma-design-spec.md §6：左 200 子导航 + 右侧表单
 * 基本信息 / 界面设置 / 公司（邀请码加入/退出）
 */
export default function Settings() {
  const [section, setSection] = useState<Section>('basic');
  const { user, setUser, logout } = useAuthStore();
  const navigate = useNavigate();
  const [basicForm] = Form.useForm();
  const [fontSize, setFontSize] = useState<'小' | '中' | '大'>('中');
  const [bgTheme, setBgTheme] = useState<'浅灰' | '米白' | '深色' | '护眼绿'>('浅灰');
  const [inviteCode, setInviteCode] = useState('');
  const { message } = App.useApp();

  // 管理员申请相关状态
  const [licenseFiles, setLicenseFiles] = useState<UploadFile[]>([]);
  const [authFiles, setAuthFiles] = useState<UploadFile[]>([]);
  const [adminReqStatus, setAdminReqStatus] = useState<'none' | 'pending' | 'approved' | 'rejected'>('none');
  const [submittingAdmin, setSubmittingAdmin] = useState(false);

  // 成为公司管理员：输入公司名 → 查是否已有管理员 → 决定是否可申请
  const [applyCompanyName, setApplyCompanyName] = useState('');
  const [companyCheck, setCompanyCheck] = useState<{
    loading: boolean;
    hasAdmin?: boolean;
    adminName?: string;
    notFound?: boolean;
  }>({ loading: false });

  const handleCheckCompany = async () => {
    if (!applyCompanyName.trim()) {
      message.error('请输入公司名称');
      return;
    }
    setCompanyCheck({ loading: true });
    try {
      const res = await authApi.getCompanyAdminStatus(applyCompanyName.trim());
      setCompanyCheck({
        loading: false,
        hasAdmin: res.has_admin,
        adminName: res.admin_name,
        notFound: false,
      });
    } catch (e: any) {
      const detail = e?.response?.data?.detail || '';
      if (detail.includes('不存在')) {
        setCompanyCheck({ loading: false, notFound: true });
      } else {
        message.error(detail || '查询失败');
        setCompanyCheck({ loading: false });
      }
    }
  };

  const handleApplyAdmin = async () => {
    if (licenseFiles.length === 0) {
      message.error('请上传营业执照');
      return;
    }
    if (authFiles.length === 0) {
      message.error('请上传法人授权签字文件');
      return;
    }
    setSubmittingAdmin(true);
    try {
      const licenseUrl = licenseFiles[0]?.name || '';
      const authUrl = authFiles[0]?.name || '';
      await authApi.createAdminRequest({
        company_name: applyCompanyName.trim(),
        business_license_url: licenseUrl,
        legal_person_auth_url: authUrl,
      });
      setAdminReqStatus('pending');
      message.success('管理员申请已提交，等待平台审核');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交失败');
    } finally {
      setSubmittingAdmin(false);
    }
  };

  if (!user) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Typography.Text type="secondary">请先登录后查看设置</Typography.Text>
      </div>
    );
  }

  const handleLogout = () => {
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
  };

  return (
    <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
      <Card styles={{ body: { padding: 0 } }}>
        <div style={{ display: 'flex', minHeight: 520 }}>
          {/* 左侧子导航 */}
          <div style={{ width: 200, borderRight: `1px solid ${colors.border}` }}>
            <div style={{ padding: '20px 16px 12px', fontWeight: 600 }}>设置</div>
            <Menu
              mode="inline"
              selectedKeys={[section]}
              items={menuItems}
              onClick={({ key }) => setSection(key as Section)}
              style={{ borderInlineEnd: 'none' }}
            />
          </div>

          {/* 右侧表单区 */}
          <div style={{ flex: 1, padding: 24 }}>
            {section === 'basic' && (
              <div style={{ maxWidth: 480 }}>
                <Typography.Title level={5}>基本信息</Typography.Title>
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
                  <Avatar size={64} style={{ backgroundColor: colors.primary }}>
                    {user.name[0]}
                  </Avatar>
                  <Button style={{ marginLeft: 16 }}>更换头像</Button>
                </div>
                <Form
                  form={basicForm}
                  layout="vertical"
                  initialValues={{
                    name: user.name,
                    email: 'zhang@lawfirm.com',
                    phone: '13800138000',
                    role: user.role,
                  }}
                  onFinish={(v) => {
                    setUser({ name: v.name, role: v.role });
                    message.success('基本信息已保存');
                  }}
                >
                  <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="email" label="邮箱">
                    <Input />
                  </Form.Item>
                  <Form.Item name="phone" label="手机号">
                    <Input />
                  </Form.Item>
                  <Form.Item name="role" label="职级">
                    <Input />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit">
                      保存
                    </Button>
                  </Form.Item>
                </Form>
                <Divider />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography.Text type="secondary">账号安全</Typography.Text>
                  <Button
                    danger
                    icon={<LogoutOutlined />}
                    onClick={handleLogout}
                  >
                    退出登录
                  </Button>
                </div>
              </div>
            )}

            {section === 'interface' && (
              <div style={{ maxWidth: 480 }}>
                <Typography.Title level={5}>界面设置</Typography.Title>
                <Form layout="vertical">
                  <Form.Item label="字体大小">
                    <Segmented
                      value={fontSize}
                      onChange={(v) => setFontSize(v as typeof fontSize)}
                      options={['小', '中', '大']}
                    />
                  </Form.Item>
                  <Form.Item label="背景颜色">
                    <Space direction="vertical">
                      {(['浅灰', '米白', '深色', '护眼绿'] as const).map((t) => (
                        <label
                          key={t}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            cursor: 'pointer',
                          }}
                        >
                          <input
                            type="radio"
                            checked={bgTheme === t}
                            onChange={() => setBgTheme(t)}
                          />
                          <span
                            style={{
                              display: 'inline-block',
                              width: 24,
                              height: 16,
                              borderRadius: 4,
                              background:
                                t === '浅灰'
                                  ? '#EEF2F7'
                                  : t === '米白'
                                    ? '#FAF7F0'
                                    : t === '深色'
                                      ? '#1F2937'
                                      : '#C7E6C7',
                              border: `1px solid ${colors.border}`,
                            }}
                          />
                          <Typography.Text>{t}</Typography.Text>
                        </label>
                      ))}
                    </Space>
                  </Form.Item>
                  <Form.Item>
                    <Button
                      type="primary"
                      onClick={() => message.success('界面设置已保存（仅本地演示）')}
                    >
                      保存
                    </Button>
                  </Form.Item>
                </Form>
              </div>
            )}

            {section === 'company' && (
              <div style={{ maxWidth: 560 }}>
                {/* 块一：当前公司 */}
                <Typography.Title level={5}>当前公司</Typography.Title>
                {user.companyId ? (
                  <Card size="small" style={{ marginBottom: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <Typography.Text strong>{user.company}</Typography.Text>
                        <div style={{ fontSize: 12, color: colors.muted }}>
                          已加入
                          {user.isAdmin && (
                            <Tag color="gold" style={{ marginLeft: 8 }}>
                              管理员
                            </Tag>
                          )}
                        </div>
                      </div>
                      <Button
                        danger
                        onClick={() => {
                          message.success('已退出公司');
                          setUser({ company: '未加入公司', companyId: undefined, isAdmin: false });
                        }}
                      >
                        退出公司
                      </Button>
                    </div>
                  </Card>
                ) : (
                  <Alert
                    type="info"
                    showIcon
                    message="您尚未加入公司"
                    description="可通过下方邀请码加入已有公司，或申请成为某公司的管理员"
                    style={{ marginBottom: 16 }}
                  />
                )}

                <Divider />

                {/* 块二：加入新公司 */}
                <Typography.Title level={5}>加入新公司</Typography.Title>
                <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                  填入公司管理者发送的邀请码，申请加入
                </Typography.Text>
                <Space.Compact style={{ width: '100%', marginBottom: 8 }}>
                  <Input
                    placeholder="请输入邀请码"
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value)}
                  />
                  <Button
                    type="primary"
                    onClick={() => {
                      if (!inviteCode) {
                        message.error('请输入邀请码');
                        return;
                      }
                      message.success('申请已提交，等待管理者审核');
                      setInviteCode('');
                    }}
                  >
                    申请加入
                  </Button>
                </Space.Compact>

                <Divider />

                {/* 块三：成为公司管理员 */}
                <Typography.Title level={5}>
                  <CrownOutlined style={{ marginRight: 6, color: colors.primary }} />
                  成为公司管理员
                </Typography.Title>
                {user.isAdmin ? (
                  <Alert
                    type="success"
                    showIcon
                    message={`您已是「${user.company}」的管理员`}
                  />
                ) : adminReqStatus === 'pending' ? (
                  <Alert
                    type="info"
                    showIcon
                    message="您的管理员申请已提交，正在等待平台审核"
                    description="审核通过后，您将获得管理员权限，可配置公司 API、管理成员用量。"
                  />
                ) : (
                  <>
                    <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                      输入公司名称查询，若该公司尚无管理员，可上传营业执照和法人授权书申请成为管理员
                    </Typography.Text>

                    {/* 第一步：输入公司名查询 */}
                    <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
                      <Input
                        placeholder="请输入公司名称"
                        value={applyCompanyName}
                        onChange={(e) => {
                          setApplyCompanyName(e.target.value);
                          setCompanyCheck({ loading: false });
                        }}
                        onPressEnter={handleCheckCompany}
                      />
                      <Button
                        type="primary"
                        onClick={handleCheckCompany}
                        loading={companyCheck.loading}
                      >
                        查询
                      </Button>
                    </Space.Compact>

                    {/* 查询结果 */}
                    {companyCheck.notFound && (
                      <Alert
                        type="warning"
                        showIcon
                        message={`公司「${applyCompanyName}」不存在`}
                        description="请确认公司名称是否正确，或联系平台创建该公司"
                        style={{ marginBottom: 12 }}
                      />
                    )}

                    {companyCheck.hasAdmin === true && (
                      <Alert
                        type="info"
                        showIcon
                        message={`「${applyCompanyName}」已有管理员`}
                        description={`当前管理员：${companyCheck.adminName || '未知'}，无需申请`}
                        style={{ marginBottom: 12 }}
                      />
                    )}

                    {/* 公司无管理员 → 显示上传文件表单 */}
                    {companyCheck.hasAdmin === false && (
                      <Form layout="vertical">
                        <Alert
                          type="success"
                          showIcon
                          message={`「${applyCompanyName}」尚无管理员，可申请`}
                          style={{ marginBottom: 12 }}
                        />
                        <Form.Item label="营业执照" required>
                          <Upload
                            beforeUpload={() => false}
                            maxCount={1}
                            fileList={licenseFiles}
                            onChange={({ fileList }) => setLicenseFiles(fileList.slice(-1))}
                            accept=".pdf,.jpg,.jpeg,.png"
                          >
                            <Button icon={<UploadOutlined />}>上传营业执照</Button>
                          </Upload>
                        </Form.Item>
                        <Form.Item label="法人授权签字文件" required>
                          <Upload
                            beforeUpload={() => false}
                            maxCount={1}
                            fileList={authFiles}
                            onChange={({ fileList }) => setAuthFiles(fileList.slice(-1))}
                            accept=".pdf,.jpg,.jpeg,.png"
                          >
                            <Button icon={<UploadOutlined />}>上传法人授权书</Button>
                          </Upload>
                        </Form.Item>
                        <Form.Item label="申请说明（可选）">
                          <Input.TextArea
                            placeholder="补充说明您的身份与申请理由"
                            rows={2}
                          />
                        </Form.Item>
                        <Button
                          type="primary"
                          loading={submittingAdmin}
                          onClick={handleApplyAdmin}
                        >
                          提交申请
                        </Button>
                      </Form>
                    )}
                  </>
                )}
              </div>
            )}

            {section === 'llm' && (
              <div>
                <div
                  style={{
                    marginBottom: 16,
                    padding: '8px 12px',
                    background: colors.primaryBg,
                    borderRadius: 8,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    fontSize: 12,
                    color: colors.muted,
                  }}
                >
                  <Switch
                    size="small"
                    checked={user.isAdmin}
                    onChange={(v) => {
                      setUser({ isAdmin: v });
                      message.success(`已切换为${v ? '管理员' : '员工'}视角（演示）`);
                    }}
                  />
                  <span>切换管理员视角（演示用）：{user.isAdmin ? '管理员' : '员工'}</span>
                </div>
                <LlmApiPanel />
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
