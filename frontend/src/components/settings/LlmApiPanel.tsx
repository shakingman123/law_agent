import { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Segmented,
  Typography,
  Space,
  Tag,
  Table,
  Progress,
  Modal,
  InputNumber,
  Descriptions,
  Spin,
  App,
} from 'antd';
import {
  ApiOutlined,
  CheckCircleTwoTone,
  ClockCircleTwoTone,
  CloseCircleTwoTone,
} from '@ant-design/icons';
import { useAuthStore } from '../../stores/authStore';
import {
  useLlmStore,
  type Provider,
  type UsageRecord,
  type CompanyLlmConfig,
  type PersonalLlmConfig,
} from '../../stores/llmStore';
import { colors } from '../../theme/tokens';

const providerOptions: { value: Provider; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'qwen', label: '通义千问' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'zhipu', label: '智谱 GLM' },
];

const defaultCompany: CompanyLlmConfig = {
  isActive: false,
  provider: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  apiKeyMasked: '',
  models: ['gpt-4o-mini', 'gpt-4o'],
  monthlyBudget: 500,
};

const defaultPersonal: PersonalLlmConfig = {
  isActive: false,
  provider: 'deepseek',
  baseUrl: 'https://api.deepseek.com/v1',
  apiKeyMasked: '',
  models: ['deepseek-chat'],
};

/**
 * 模型与 API 面板
 * 依据 implementation-guide.md §4：
 *   - 员工：切换「公司 API / 个人 API」、申请公司 API 使用权、配置个人 API、查看我的用量
 *   - 管理员：额外可见公司 API 配置、员工申请审批、员工用量看板与额度设置
 * 数据通过 stores/llmStore 调用后端接口获取/提交
 */
export default function LlmApiPanel() {
  const { user, setUser } = useAuthStore();
  const {
    companyConfig,
    personalConfig,
    accessRequest,
    usageRecords,
    myUsage,
    loading,
    loadAll,
    setCompanyConfig,
    setPersonalConfig,
    switchSource,
    requestCompanyAccess,
    approveRequest,
    setQuotaLimit,
  } = useLlmStore();
  const { message } = App.useApp();

  const [companyForm] = Form.useForm();
  const [personalForm] = Form.useForm();
  const [quotaModalOpen, setQuotaModalOpen] = useState(false);
  const [quotaTarget, setQuotaTarget] = useState<UsageRecord | null>(null);
  const [saving, setSaving] = useState<'company' | 'personal' | null>(null);

  // 初次加载
  useEffect(() => {
    if (user) loadAll(user.isAdmin);
  }, [user, loadAll]);

  const company = companyConfig ?? defaultCompany;
  const personal = personalConfig ?? defaultPersonal;
  const companyUsable = company.isActive && !!company.apiKeyMasked;
  const personalUsable = personal.isActive && !!personal.apiKeyMasked;

  if (!user) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Typography.Text type="secondary">请先登录后查看模型与 API 配置</Typography.Text>
      </div>
    );
  }

  // ===== 切换使用方式 =====
  const handleSwitchSource = async (v: 'company' | 'personal') => {
    if (v === 'company' && !companyUsable) {
      message.warning('公司 API 暂不可用，请先申请或等待管理员配置');
      return;
    }
    if (v === 'personal' && !personalUsable) {
      message.warning('个人 API 尚未配置，请先在下方填写');
      return;
    }
    try {
      await switchSource(v);
      setUser({ llmSource: v });
      message.success(`已切换为${v === 'company' ? '公司' : '个人'} API`);
    } catch {
      /* 错误已由 request 拦截器提示 */
    }
  };

  // ===== 员工申请公司 API 使用权 =====
  const handleRequest = async () => {
    try {
      await requestCompanyAccess();
      message.success('已提交申请，等待管理员审核');
    } catch {
      /* 拦截器已提示 */
    }
  };

  // ===== 管理员保存公司配置 =====
  const handleSaveCompany = async () => {
    try {
      const v = await companyForm.validateFields();
      setSaving('company');
      await setCompanyConfig({
        provider: v.provider,
        baseUrl: v.baseUrl,
        apiKey: v.apiKey || undefined,
        models: v.models?.split(/[,\s]+/).filter(Boolean) ?? company.models,
        monthlyBudget: v.monthlyBudget ?? company.monthlyBudget,
      });
      message.success('公司 API 配置已保存并启用');
    } catch {
      /* 校验失败或请求失败 */
    } finally {
      setSaving(null);
    }
  };

  // ===== 个人保存自己的 API =====
  const handleSavePersonal = async () => {
    try {
      const v = await personalForm.validateFields();
      setSaving('personal');
      await setPersonalConfig({
        provider: v.provider,
        baseUrl: v.baseUrl,
        apiKey: v.apiKey,
        models: v.models?.split(/[,\s]+/).filter(Boolean) ?? personal.models,
      });
      message.success('个人 API 已保存并启用');
    } catch {
      /* 校验失败或请求失败 */
    } finally {
      setSaving(null);
    }
  };

  // myUsage 可能为空对象（字段 undefined），用显式 fallback 保证渲染安全
  const uid = Number(user.id);
  const my: UsageRecord & { quotaUsedRatio: number } = myUsage
    ? {
        ...myUsage,
        userId: myUsage.userId || uid,
        userName: myUsage.userName || user.name,
        source: myUsage.source || user.llmSource,
        provider: myUsage.provider || (user.llmSource === 'company' ? company.provider : personal.provider),
        model: myUsage.model || (user.llmSource === 'company' ? company.models[0] : personal.models[0]) || '',
        calls: myUsage.calls ?? 0,
        promptTokens: myUsage.promptTokens ?? 0,
        completionTokens: myUsage.completionTokens ?? 0,
        cost: myUsage.cost ?? 0,
        quotaLimit: myUsage.quotaLimit ?? 0,
        quotaUsedRatio: myUsage.quotaUsedRatio ?? 0,
      }
    : {
        userId: uid,
        userName: user.name,
        source: user.llmSource,
        provider: user.llmSource === 'company' ? company.provider : personal.provider,
        model: user.llmSource === 'company' ? company.models[0] : personal.models[0],
        calls: 0,
        promptTokens: 0,
        completionTokens: 0,
        cost: 0,
        quotaLimit: 0,
        quotaUsedRatio: 0,
      };

  return (
    <Spin spinning={loading}>
      <Typography.Title level={5}>
        <ApiOutlined style={{ marginRight: 8 }} />
        模型与 API
      </Typography.Title>

      {/* ===== 使用方式（管理员可切换；员工按授权自动生效） ===== */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text strong>当前使用方式</Typography.Text>
          {user.isAdmin ? (
            <>
              <Segmented
                value={user.llmSource}
                onChange={(v) => handleSwitchSource(v as 'company' | 'personal')}
                options={[
                  {
                    label: `公司 API${companyUsable ? '' : '（未可用）'}`,
                    value: 'company',
                    disabled: !companyUsable,
                  },
                  {
                    label: `个人 API${personalUsable ? '' : '（未配置）'}`,
                    value: 'personal',
                    disabled: !personalUsable,
                  },
                ]}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                优先级：个人 API &gt; 公司 API。个人调用不计入公司额度。
              </Typography.Text>
            </>
          ) : (
            <Typography.Text type="secondary">
              由系统自动分配：已获授权且公司 API 可用时优先公司额度，否则使用您配置的个人 API
              （员工无需手动切换）。
            </Typography.Text>
          )}
        </Space>
      </Card>

      {/* ===== 公司 API ===== */}
      <Card
        size="small"
        title="公司 API"
        extra={
          company.isActive ? (
            <Tag color="green">已启用</Tag>
          ) : (
            <Tag>未启用</Tag>
          )
        }
        style={{ marginBottom: 16 }}
      >
        {user.isAdmin ? (
          // 管理员：配置表单
          <Form
            form={companyForm}
            layout="vertical"
            initialValues={{
              provider: company.provider,
              baseUrl: company.baseUrl,
              apiKey: '',
              models: company.models.join(', '),
              monthlyBudget: company.monthlyBudget,
            }}
          >
            <Form.Item name="provider" label="服务商" rules={[{ required: true }]}>
              <Segmented options={providerOptions} />
            </Form.Item>
            <Form.Item name="baseUrl" label="Base URL" rules={[{ required: true }]}>
              <Input placeholder="https://api.openai.com/v1" />
            </Form.Item>
            <Form.Item
              name="apiKey"
              label="API Key"
              extra={
                company.apiKeyMasked
                  ? `当前：${company.apiKeyMasked}（留空则不修改）`
                  : '将加密存储，接口仅返回掩码'
              }
            >
              <Input.Password placeholder="sk-..." />
            </Form.Item>
            <Form.Item name="models" label="可用模型（逗号分隔）" rules={[{ required: true }]}>
              <Input placeholder="gpt-4o-mini, gpt-4o" />
            </Form.Item>
            <Form.Item name="monthlyBudget" label="公司月度预算（美元）">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Button
              type="primary"
              loading={saving === 'company'}
              onClick={handleSaveCompany}
            >
              保存并启用
            </Button>
          </Form>
        ) : (
          // 员工：查看状态 / 申请
          <Space direction="vertical" style={{ width: '100%' }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="服务商">
                {providerOptions.find((p) => p.value === company.provider)?.label}
              </Descriptions.Item>
              <Descriptions.Item label="可用模型">
                {company.models.join('、') || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="API Key">
                {company.apiKeyMasked || '—（管理员未配置）'}
              </Descriptions.Item>
            </Descriptions>
            {companyUsable && (!accessRequest || accessRequest.status === 'rejected') && (
              <Button type="primary" onClick={handleRequest}>
                {accessRequest?.status === 'rejected' ? '重新申请使用公司 API' : '申请使用公司 API'}
              </Button>
            )}
            {accessRequest && (
              <div style={{ marginTop: 8 }}>
                <Space>
                  {accessRequest.status === 'pending' && (
                    <Tag icon={<ClockCircleTwoTone />}>审核中</Tag>
                  )}
                  {accessRequest.status === 'approved' && (
                    <Tag icon={<CheckCircleTwoTone twoToneColor={colors.green} />} color="green">
                      已通过
                    </Tag>
                  )}
                  {accessRequest.status === 'rejected' && (
                    <Tag icon={<CloseCircleTwoTone twoToneColor={colors.danger} />} color="red">
                      已拒绝
                    </Tag>
                  )}
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    申请时间：{accessRequest.createdAt}
                  </Typography.Text>
                </Space>
              </div>
            )}
          </Space>
        )}
      </Card>

      {/* ===== 个人 API ===== */}
      <Card
        size="small"
        title="个人 API"
        extra={
          personal.isActive ? (
            <Tag color="green">已启用</Tag>
          ) : (
            <Tag>未启用</Tag>
          )
        }
        style={{ marginBottom: 16 }}
      >
        <Form
          form={personalForm}
          layout="vertical"
          initialValues={{
            provider: personal.provider,
            baseUrl: personal.baseUrl,
            apiKey: '',
            models: personal.models.join(', '),
          }}
        >
          <Form.Item name="provider" label="服务商" rules={[{ required: true }]}>
            <Segmented options={providerOptions} />
          </Form.Item>
          <Form.Item name="baseUrl" label="Base URL" rules={[{ required: true }]}>
            <Input placeholder="https://api.deepseek.com/v1" />
          </Form.Item>
          <Form.Item
            name="apiKey"
            label="API Key"
            rules={[{ required: true, message: '请输入 API Key' }]}
            extra={
              personal.apiKeyMasked
                ? `当前：${personal.apiKeyMasked}（重新填写则覆盖）`
                : '将加密存储，接口仅返回掩码'
            }
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>
          <Form.Item name="models" label="可用模型（逗号分隔）" rules={[{ required: true }]}>
            <Input placeholder="deepseek-chat" />
          </Form.Item>
          <Button
            type="primary"
            loading={saving === 'personal'}
            onClick={handleSavePersonal}
          >
            保存并启用
          </Button>
        </Form>
      </Card>

      {/* ===== 我的用量 ===== */}
      <Card size="small" title="我的用量" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="使用方式">
            {my.source === 'company' ? '公司 API' : '个人 API'}
          </Descriptions.Item>
          <Descriptions.Item label="模型">{my.model}</Descriptions.Item>
          <Descriptions.Item label="调用次数">{my.calls}</Descriptions.Item>
          <Descriptions.Item label="Prompt Tokens">
            {my.promptTokens.toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="Completion Tokens">
            {my.completionTokens.toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="费用">${my.cost.toFixed(2)}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* ===== 管理员：员工用量看板 ===== */}
      {user.isAdmin && (
        <Card size="small" title="员工用量管理（管理员）" style={{ marginBottom: 16 }}>
          <Table<UsageRecord>
            size="small"
            rowKey="userId"
            dataSource={usageRecords}
            pagination={false}
            columns={[
              { title: '员工', dataIndex: 'userName', width: 90 },
              {
                title: '使用方式',
                dataIndex: 'source',
                width: 100,
                render: (v: string) =>
                  v === 'company' ? (
                    <Tag color="blue">公司</Tag>
                  ) : (
                    <Tag color="green">个人</Tag>
                  ),
              },
              { title: '模型', dataIndex: 'model', width: 120 },
              { title: '调用', dataIndex: 'calls', width: 70 },
              {
                title: 'Tokens',
                render: (_, r) =>
                  `${(r.promptTokens + r.completionTokens).toLocaleString()}`,
                width: 110,
              },
              {
                title: '费用/额度',
                render: (_, r) => (
                  <div style={{ minWidth: 140 }}>
                    <Progress
                      percent={r.quotaLimit ? Math.round((r.cost / r.quotaLimit) * 100) : 0}
                      size="small"
                      format={() => `$${r.cost.toFixed(2)} / $${r.quotaLimit}`}
                    />
                  </div>
                ),
              },
              {
                title: '操作',
                width: 120,
                render: (_, r) => (
                  <Button
                    size="small"
                    onClick={() => {
                      setQuotaTarget(r);
                      setQuotaModalOpen(true);
                    }}
                  >
                    设置额度
                  </Button>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* ===== 管理员：待审批申请 ===== */}
      {user.isAdmin && accessRequest?.status === 'pending' && (
        <Card size="small" title="待审批申请（管理员）" style={{ marginBottom: 16 }}>
          <Space>
            <Typography.Text>
              {accessRequest.userName} 申请使用公司 API
            </Typography.Text>
            <Button
              type="primary"
              size="small"
              onClick={async () => {
                try {
                  await approveRequest(accessRequest.id, true);
                  message.success('已通过');
                } catch {
                  /* 拦截器已提示 */
                }
              }}
            >
              通过
            </Button>
            <Button
              size="small"
              danger
              onClick={async () => {
                try {
                  await approveRequest(accessRequest.id, false);
                  message.success('已拒绝');
                } catch {
                  /* 拦截器已提示 */
                }
              }}
            >
              拒绝
            </Button>
          </Space>
        </Card>
      )}

      {/* ===== 额度设置弹窗 ===== */}
      <Modal
        title="设置月度额度"
        open={quotaModalOpen}
        onCancel={() => setQuotaModalOpen(false)}
        onOk={async () => {
          if (quotaTarget) {
            try {
              await setQuotaLimit(quotaTarget.userId, quotaTarget.quotaLimit);
              message.success('额度已更新');
            } catch {
              /* 拦截器已提示 */
            }
          }
          setQuotaModalOpen(false);
        }}
        okText="保存"
        cancelText="取消"
      >
        {quotaTarget && (
          <div>
            <Typography.Paragraph>
              为 <Typography.Text strong>{quotaTarget.userName}</Typography.Text> 设置月度额度
            </Typography.Paragraph>
            <InputNumber
              addonAfter="美元 / 月"
              min={0}
              value={quotaTarget.quotaLimit}
              style={{ width: '100%' }}
              onChange={(v) =>
                setQuotaTarget({ ...quotaTarget, quotaLimit: v ?? 0 })
              }
            />
          </div>
        )}
      </Modal>
    </Spin>
  );
}
