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
import { useUiStore, type FontSize, type BgTheme } from '../../stores/uiStore';
import { colors } from '../../theme/tokens';
import LlmApiPanel from '../../components/settings/LlmApiPanel';
import { authApi, type AdminRequest, type InviteCode, type JoinRequest } from '../../api/auth';
import { filesApi } from '../../api/files';
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
  const { settings, update: updateUi } = useUiStore();
  const [fontSize, setFontSize] = useState<FontSize>(settings.fontSize);
  const [bgTheme, setBgTheme] = useState<BgTheme>(settings.bgTheme);
  // 切换到该 tab 时从 store 同步一次，避免其他页面改了之后显示过期
  useEffect(() => {
    if (section === 'interface') {
      setFontSize(useUiStore.getState().settings.fontSize);
      setBgTheme(useUiStore.getState().settings.bgTheme);
    }
  }, [section]);
  const [inviteCode, setInviteCode] = useState('');
  const { message } = App.useApp();

  // 成为公司管理员：申请记录 + 弹窗上传执照/授权书
  const [myRequest, setMyRequest] = useState<AdminRequest | null>(null);
  const [applyOpen, setApplyOpen] = useState(false);
  const [applyReason, setApplyReason] = useState('');
  const [licenseFile, setLicenseFile] = useState<UploadFile[]>([]);
  const [authFile, setAuthFile] = useState<UploadFile[]>([]);
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
      // 非管理员：加载自己的管理员申请状态（待审核/已通过/已驳回）
      if (!user?.isAdmin) {
        authApi
          .getMyAdminRequest()
          .then(setMyRequest)
          .catch(() => setMyRequest(null));
      }
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

  const openApplyModal = () => {
    setApplyReason('');
    setLicenseFile([]);
    setAuthFile([]);
    setApplyOpen(true);
  };

  const handleApplyAdmin = async () => {
    if (licenseFile.length === 0) {
      message.error('请上传营业执照');
      return;
    }
    if (authFile.length === 0) {
      message.error('请上传法人授权书');
      return;
    }
    setSubmittingAdmin(true);
    try {
      // 先上传两个附件拿到 URL，再提交申请
      const [licenseRes, authRes] = await Promise.all([
        filesApi.upload(licenseFile[0].originFileObj as File),
        filesApi.upload(authFile[0].originFileObj as File),
      ]);
      await authApi.createAdminRequest({
        company_name: applyCompanyName.trim(),
        reason: applyReason.trim() || undefined,
        business_license_url: licenseRes.url,
        legal_person_auth_url: authRes.url,
      });
      setApplyOpen(false);
      message.success('管理员申请已提交，等待平台开发者审核');
      const req = await authApi.getMyAdminRequest();
      setMyRequest(req);
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
                  <Avatar size={64} src={user.avatar || undefined} style={{ backgroundColor: colors.primary }}>
                    {user.name?.[0] || 'U'}
                  </Avatar>
                  <Upload
                    showUploadList={false}
                    accept="image/*"
                    maxCount={1}
                    beforeUpload={async (file) => {
                      if (!file.type.startsWith('image/')) {
                        message.error('只能上传图片作为头像');
                        return Upload.LIST_IGNORE;
                      }
                      if (file.size > 5 * 1024 * 1024) {
                        message.error('头像图片不能超过 5MB');
                        return Upload.LIST_IGNORE;
                      }
                      try {
                        const r = await filesApi.upload(file);
                        await authApi.updateProfile({ avatar: r.url });
                        // 刷新本地用户
                        const me = await authApi.getMe();
                        setUser({ avatar: me.avatar || undefined });
                        message.success('头像更换成功');
                      } catch (e: any) {
                        message.error(e?.response?.data?.detail || '头像上传失败');
                      }
                      return Upload.LIST_IGNORE;
                    }}
                  >
                    <Button icon={<UploadOutlined />} style={{ marginLeft: 16 }}>
                      更换头像
                    </Button>
                  </Upload>
                  {user.avatar && (
                    <Button
                      type="text"
                      danger
                      style={{ marginLeft: 8 }}
                      onClick={async () => {
                        try {
                          await authApi.updateProfile({ avatar: '' });
                          const me = await authApi.getMe();
                          setUser({ avatar: me.avatar || undefined });
                          message.success('已恢复默认头像');
                        } catch (e: any) {
                          message.error(e?.response?.data?.detail || '恢复失败');
                        }
                      }}
                    >
                      恢复默认
                    </Button>
                  )}
                </div>
                <Form
                  form={basicForm}
                  layout="vertical"
                  initialValues={{
                    name: user.name,
                    email: user.email ?? '',
                    phone: user.phone ?? '',
                    role: user.role ?? '',
                  }}
                  onFinish={async (v) => {
                    try {
                      await authApi.updateProfile({
                        name: v.name,
                        phone: v.phone ?? '',
                      });
                      // 重新拉取当前用户，刷新本地状态
                      const me = await authApi.getMe();
                      setUser({ name: me.name, phone: me.phone ?? null });
                      message.success('基本信息已保存');
                    } catch (e: any) {
                      message.error(e?.response?.data?.detail || '保存失败');
                    }
                  }}
                >
                  <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
                    <Input />
                  </Form.Item>
                  {/* 邮箱与注册邮箱一致，不可修改 */}
                  <Form.Item label="邮箱" tooltip="邮箱为注册账号，不可修改">
                    <Input value={user.email ?? ''} disabled style={{ color: colors.muted }} />
                  </Form.Item>
                  {/* 手机号：用户可自行填写 */}
                  <Form.Item name="phone" label="手机号">
                    <Input placeholder="请输入手机号" />
                  </Form.Item>
                  {/* 职级：只读，由管理员在后台维护 */}
                  <Form.Item label="职级" tooltip="职级由管理员在后台维护，不可自行修改">
                    <Input
                      value={user.role || '员工'}
                      disabled
                      style={{ color: colors.muted }}
                    />
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
                      onChange={(v) => setFontSize(v as FontSize)}
                      options={(['小', '中', '大'] as const).map((opt) => ({
                        label: `${opt}${settings.fontSize === opt ? ' (当前)' : ''}`,
                        value: opt,
                      }))}
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
                          <Typography.Text>
                            {t}
                            {settings.bgTheme === t ? '  (当前)' : ''}
                          </Typography.Text>
                        </label>
                      ))}
                    </Space>
                  </Form.Item>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="修改后立即生效，配置保存到本地浏览器（下次打开自动恢复）"
                  />
                  <Form.Item>
                    <Space>
                      <Button
                        type="primary"
                        onClick={() => {
                          updateUi({ fontSize, bgTheme });
                          message.success('界面设置已保存，已立即生效');
                        }}
                      >
                        应用并保存
                      </Button>
                      <Button
                        onClick={() => {
                          setFontSize('中');
                          setBgTheme('浅灰');
                          updateUi({ fontSize: '中', bgTheme: '浅灰' });
                          message.success('已恢复默认');
                        }}
                      >
                        恢复默认
                      </Button>
                    </Space>
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
                ) : myRequest?.status === 'pending' ? (
                  <Alert
                    type="info"
                    showIcon
                    message="您的管理员申请正在等待平台开发者审核"
                    description={`申请管理公司「${myRequest.company_name}」 · 提交于 ${new Date(
                      myRequest.created_at,
                    ).toLocaleString()}`}
                  />
                ) : myRequest?.status === 'approved' ? (
                  <Alert
                    type="success"
                    showIcon
                    message="您的管理员申请已通过"
                    description="请刷新页面获取管理员权限"
                  />
                ) : (
                  <>
                    {myRequest?.status === 'rejected' && (
                      <Alert
                        type="warning"
                        showIcon
                        message="您此前的管理员申请未通过审核"
                        description="可补充完整资料后重新申请"
                        style={{ marginBottom: 12 }}
                      />
                    )}
                    <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                      输入公司名称查询：若该公司尚无管理员或平台上尚不存在，可上传营业执照和法人授权书申请成为管理员
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

                    {/* 查询结果：公司不存在 → 弹出上传资料界面 */}
                    {companyCheck.notFound && (
                      <Alert
                        type="warning"
                        showIcon
                        message={`公司「${applyCompanyName}」在平台上尚不存在`}
                        description="可上传公司营业执照和法人授权书，经平台开发者确认后创建该公司并将您设为管理员"
                        action={
                          <Button type="primary" size="small" onClick={openApplyModal}>
                            上传资料申请
                          </Button>
                        }
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

                    {/* 公司存在但无管理员 → 同样弹出上传资料界面 */}
                    {companyCheck.hasAdmin === false && (
                      <Alert
                        type="success"
                        showIcon
                        message={`「${applyCompanyName}」尚无管理员，可申请`}
                        description="上传营业执照和法人授权书，经平台开发者审核通过后您将成为该公司管理员"
                        action={
                          <Button type="primary" size="small" onClick={openApplyModal}>
                            上传资料申请
                          </Button>
                        }
                      />
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

      {/* 成为公司管理员申请弹窗：上传营业执照 + 法人授权书 */}
      <Modal
        title={`申请成为「${applyCompanyName}」的管理员`}
        open={applyOpen}
        onCancel={() => setApplyOpen(false)}
        onOk={handleApplyAdmin}
        okText="提交申请"
        cancelText="取消"
        confirmLoading={submittingAdmin}
        okButtonProps={{
          disabled: licenseFile.length === 0 || authFile.length === 0,
        }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="平台开发者将根据资料的完整性审核您的申请"
          description="审核通过后您将成为该公司管理员；若公司尚不存在，将一并创建。"
        />
        <Form layout="vertical">
          <Form.Item label="公司营业执照" required>
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              fileList={licenseFile}
              onChange={({ fileList }) => setLicenseFile(fileList.slice(-1))}
              accept=".pdf,.jpg,.jpeg,.png"
            >
              <Button icon={<UploadOutlined />}>上传营业执照</Button>
            </Upload>
          </Form.Item>
          <Form.Item label="法人授权书" required>
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              fileList={authFile}
              onChange={({ fileList }) => setAuthFile(fileList.slice(-1))}
              accept=".pdf,.jpg,.jpeg,.png"
            >
              <Button icon={<UploadOutlined />}>上传法人授权书</Button>
            </Upload>
          </Form.Item>
          <Form.Item label="申请说明（可选）">
            <Input.TextArea
              placeholder="补充说明您的身份与申请理由"
              rows={2}
              value={applyReason}
              onChange={(e) => setApplyReason(e.target.value)}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
