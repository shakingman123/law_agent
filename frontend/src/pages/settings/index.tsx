import { useEffect, useState } from 'react';
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
  List,
  Tooltip,
  message as staticMessage,
} from 'antd';
import { UserOutlined, BgColorsOutlined, HomeOutlined, ApiOutlined, UploadOutlined, CrownOutlined, LogoutOutlined, CopyOutlined, ReloadOutlined, TeamOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { useAuthStore } from '../../stores/authStore';
import { colors } from '../../theme/tokens';
import LlmApiPanel from '../../components/settings/LlmApiPanel';
import { authApi, type InviteCode, type JoinRequest } from '../../api/auth';
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

  // 邀请码管理（管理员）
  const [inviteCodeInfo, setInviteCodeInfo] = useState<InviteCode | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  // 待审批加入申请（管理员）
  const [joinRequests, setJoinRequests] = useState<JoinRequest[]>([]);
  const [joinReqLoading, setJoinReqLoading] = useState(false);
  const [reviewingId, setReviewingId] = useState<number | null>(null);

  // 员工申请加入
  const [submittingJoin, setSubmittingJoin] = useState(false);

  // 管理员进入公司 tab 时加载邀请码与加入申请
  const loadCompanyAdminData = async () => {
    if (!user?.isAdmin || !user?.companyId) return;
    setInviteLoading(true);
    setJoinReqLoading(true);
    try {
      const [code, reqs] = await Promise.all([
        authApi.getInviteCode().catch(() => null),
        authApi.listJoinRequests().catch(() => [] as JoinRequest[]),
      ]);
      if (code) setInviteCodeInfo(code);
      setJoinRequests(reqs);
    } finally {
      setInviteLoading(false);
      setJoinReqLoading(false);
    }
  };

  useEffect(() => {
    if (section === 'company') {
      loadCompanyAdminData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, user?.isAdmin, user?.companyId]);

  const handleCopyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      message.success('邀请码已复制到剪贴板');
    } catch {
      staticMessage.warning('复制失败，请手动选择复制');
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const res = await authApi.regenerateInviteCode();
      setInviteCodeInfo(res);
      message.success('已重新生成邀请码，旧码已失效');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败');
    } finally {
      setRegenerating(false);
    }
  };

  const handleApprove = async (reqId: number) => {
    setReviewingId(reqId);
    try {
      await authApi.approveJoinRequest(reqId);
      message.success('已批准加入申请');
      setJoinRequests((prev) => prev.filter((r) => r.id !== reqId));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败');
    } finally {
      setReviewingId(null);
    }
  };

  const handleReject = async (reqId: number) => {
    setReviewingId(reqId);
    try {
      await authApi.rejectJoinRequest(reqId);
      message.success('已拒绝加入申请');
      setJoinRequests((prev) => prev.filter((r) => r.id !== reqId));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败');
    } finally {
      setReviewingId(null);
    }
  };

  const handleApplyJoin = async () => {
    if (!inviteCode.trim()) {
      message.error('请输入邀请码');
      return;
    }
    setSubmittingJoin(true);
    try {
      await authApi.applyJoinCompany(inviteCode.trim());
      message.success('申请已提交，等待该公司管理员审批');
      setInviteCode('');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '申请失败');
    } finally {
      setSubmittingJoin(false);
    }
  };

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

                {/* 块二（管理员）：邀请码管理 */}
                {user.isAdmin && !!user.companyId && (
                  <>
                    <Typography.Title level={5}>
                      <CrownOutlined style={{ marginRight: 6, color: colors.primary }} />
                      邀请码管理
                    </Typography.Title>
                    <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                      生成随机邀请码后分享给员工，员工填入邀请码申请加入，经您审批后即可加入公司。
                    </Typography.Text>
                    <Card size="small" loading={inviteLoading} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                          <Typography.Text type="secondary" style={{ flexShrink: 0 }}>当前邀请码</Typography.Text>
                          {inviteCodeInfo?.invite_code ? (
                            <Typography.Text
                              copyable={false}
                              style={{
                                fontFamily: 'monospace',
                                fontSize: 18,
                                fontWeight: 600,
                                letterSpacing: 2,
                                color: colors.primary,
                              }}
                            >
                              {inviteCodeInfo.invite_code}
                            </Typography.Text>
                          ) : (
                            <Typography.Text type="secondary">—</Typography.Text>
                          )}
                        </div>
                        <Space>
                          <Tooltip title="复制邀请码">
                            <Button
                              icon={<CopyOutlined />}
                              disabled={!inviteCodeInfo?.invite_code}
                              onClick={() => inviteCodeInfo?.invite_code && handleCopyCode(inviteCodeInfo.invite_code)}
                            >
                              复制
                            </Button>
                          </Tooltip>
                          <Tooltip title="重新生成，旧码立即失效">
                            <Button
                              icon={<ReloadOutlined />}
                              loading={regenerating}
                              onClick={handleRegenerate}
                            >
                              重新生成
                            </Button>
                          </Tooltip>
                        </Space>
                      </div>
                    </Card>
                    <Alert
                      type="warning"
                      showIcon
                      message="重新生成邀请码后，旧邀请码将立即失效"
                      description="请将最新邀请码发送给需加入公司的员工，员工在「加入新公司」处填写即可申请。"
                      style={{ marginBottom: 16 }}
                    />

                    <Divider />

                    {/* 块三（管理员）：待审批加入申请 */}
                    <Typography.Title level={5}>
                      <TeamOutlined style={{ marginRight: 6, color: colors.primary }} />
                      待审批加入申请
                    </Typography.Title>
                    <List
                      loading={joinReqLoading}
                      dataSource={joinRequests.filter((r) => r.status === 'pending')}
                      locale={{ emptyText: '暂无待审批的加入申请' }}
                      renderItem={(req) => (
                        <List.Item
                          actions={[
                            <Button
                              key="approve"
                              type="primary"
                              size="small"
                              icon={<CheckOutlined />}
                              loading={reviewingId === req.id}
                              onClick={() => handleApprove(req.id)}
                            >
                              批准
                            </Button>,
                            <Button
                              key="reject"
                              danger
                              size="small"
                              icon={<CloseOutlined />}
                              loading={reviewingId === req.id}
                              onClick={() => handleReject(req.id)}
                            >
                              拒绝
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={
                              <Space>
                                <Typography.Text strong>{req.user_name}</Typography.Text>
                                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                  {req.user_email}
                                </Typography.Text>
                              </Space>
                            }
                            description={`申请加入 · ${new Date(req.created_at).toLocaleString()}`}
                          />
                        </List.Item>
                      )}
                      style={{ marginBottom: 16 }}
                    />

                    <Divider />
                  </>
                )}

                {/* 块四：加入新公司（非管理员） */}
                {!user.isAdmin && (
                  <>
                    <Typography.Title level={5}>加入新公司</Typography.Title>
                    <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                      填入公司管理者发送的邀请码，申请加入
                    </Typography.Text>
                    <Space.Compact style={{ width: '100%', marginBottom: 8 }}>
                      <Input
                        placeholder="请输入邀请码"
                        value={inviteCode}
                        onChange={(e) => setInviteCode(e.target.value)}
                        onPressEnter={handleApplyJoin}
                      />
                      <Button
                        type="primary"
                        loading={submittingJoin}
                        onClick={handleApplyJoin}
                      >
                        申请加入
                      </Button>
                    </Space.Compact>

                    <Divider />
                  </>
                )}

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
