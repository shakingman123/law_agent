import { useEffect, useState } from 'react';
import {
  Card,
  Input,
  Button,
  Segmented,
  List,
  Tag,
  Typography,
  Space,
  Modal,
  Avatar,
  Empty,
  App,
  Spin,
  Form,
  Select,
  Upload,
} from 'antd';
import {
  SearchOutlined,
  LockOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileImageOutlined,
  VideoCameraOutlined,
  FolderOutlined,
  PlusOutlined,
  PaperClipOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { colors } from '../../theme/tokens';
import { useCaseStore } from '../../stores/caseStore';
import type { Case } from '../../api/cases';
import { useNavigate } from 'react-router-dom';

type Tab = '全部' | '私库' | '公库';

interface DocCase {
  id: number;
  title: string;
  updatedAt: string;
  scope: 'private' | 'public';
  fileTypes: string[];
}

const scopeConfig: Record<string, { color: string; label: string }> = {
  private: { color: colors.green, label: '私库' },
  public: { color: colors.primary, label: '协作' },
};

const fileIcon: Record<string, React.ReactNode> = {
  docx: <FileTextOutlined style={{ color: colors.primary }} />,
  pdf: <FilePdfOutlined style={{ color: colors.danger }} />,
  image: <FileImageOutlined style={{ color: colors.green }} />,
  video: <VideoCameraOutlined style={{ color: colors.amber }} />,
};

/** 将后端 Case 映射为文档库卡片结构 */
const mapCaseToDoc = (c: Case): DocCase => ({
  id: c.id,
  title: c.name,
  updatedAt: c.updated_at.slice(0, 10),
  scope: c.scope,
  fileTypes: [...new Set(c.documents.map((d) => d.file_type).filter(Boolean))] as string[],
});

/**
 * 文档库页
 * 依据 figma-design-spec.md §5：密码门禁 → 搜索栏 → 案件卡片（按更新时间排序）→ 未解锁弹窗
 * 案件数据从后端 /api/cases 拉取（含上传的资料文档）
 * 「新建文档」逻辑与工作台右侧新建案件保持一致：创建案件后可直接在文档库中管理
 */
export default function DocLib() {
  const [unlocked, setUnlocked] = useState(false);
  const [password, setPassword] = useState('');
  const [tab, setTab] = useState<Tab>('全部');
  const [keyword, setKeyword] = useState('');
  const [unlockTarget, setUnlockTarget] = useState<DocCase | null>(null);
  const { message } = App.useApp();
  const { allCases, loading, loadAll, createCase } = useCaseStore();
  const navigate = useNavigate();

  // 新建案件弹窗状态（与工作台右侧新建案件保持一致）
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  useEffect(() => {
    if (unlocked) {
      loadAll();
    }
  }, [unlocked, loadAll]);

  const docCases = allCases.map(mapCaseToDoc);

  const closeModal = () => {
    setModalOpen(false);
    form.resetFields();
    setFileList([]);
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const files = fileList
        .map((f) => f.originFileObj as File)
        .filter(Boolean);
      const created = await createCase(values, files);
      message.success('案件已创建');
      closeModal();
      navigate(`/cases/${created.id}`);
    } catch (e: any) {
      if (e?.errorFields) return; // antd 校验错误不弹 toast
      message.error(e?.response?.data?.detail || '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  // 门禁态
  if (!unlocked) {
    return (
      <div
        style={{
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: colors.background,
        }}
      >
        <Card style={{ width: 380, textAlign: 'center', padding: '24px 32px' }}>
          <LockOutlined style={{ fontSize: 48, color: colors.primary, marginBottom: 16 }} />
          <Typography.Title level={4} style={{ marginBottom: 8 }}>
            文档库
          </Typography.Title>
          <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
            请输入文档库独立密码以进入
          </Typography.Text>
          <Input.Password
            size="large"
            placeholder="请输入密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onPressEnter={() => {
              if (!password) {
                message.error('请输入密码');
                return;
              }
              setUnlocked(true);
              message.success('已进入文档库');
            }}
          />
          <Button
            type="primary"
            size="large"
            block
            style={{ marginTop: 12 }}
            onClick={() => {
              if (!password) {
                message.error('请输入密码');
                return;
              }
              setUnlocked(true);
              message.success('已进入文档库');
            }}
          >
            进入文档库
          </Button>
        </Card>
      </div>
    );
  }

  // 列表态
  const filteredCases = docCases.filter((c) => {
    if (tab === '私库' && c.scope !== 'private') return false;
    if (tab === '公库' && c.scope !== 'public') return false;
    if (keyword && !c.title.includes(keyword)) return false;
    return true;
  });

  return (
    <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
      <Card
        title={
          <Typography.Title level={4} style={{ margin: 0 }}>
            文档库
          </Typography.Title>
        }
        extra={
          <Space>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索案件/文件名"
              allowClear
              style={{ width: 240 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <Segmented<Tab>
              value={tab}
              onChange={setTab}
              options={['全部', '私库', '公库']}
            />
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                form.resetFields();
                setFileList([]);
                setModalOpen(true);
              }}
            >
              新建文档
            </Button>
          </Space>
        }
        styles={{ body: { padding: 16 } }}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin />
          </div>
        ) : filteredCases.length === 0 ? (
          <Empty description="暂无匹配案件">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
              创建第一个案件
            </Button>
          </Empty>
        ) : (
          <List
            grid={{ gutter: 16, column: 3 }}
            dataSource={filteredCases}
            renderItem={(item) => (
              <List.Item>
                <Card
                  hoverable
                  size="small"
                  onClick={() => navigate(`/cases/${item.id}`)}
                >
                  <div style={{ display: 'flex', gap: 12 }}>
                    <Avatar
                      shape="square"
                      size={48}
                      style={{ background: colors.primaryBg, color: colors.primary }}
                    >
                      <FolderOutlined />
                    </Avatar>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Typography.Text strong ellipsis style={{ display: 'block' }}>
                        {item.title}
                      </Typography.Text>
                      <div style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>
                        更新于 {item.updatedAt}
                      </div>
                      <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <Tag color={scopeConfig[item.scope].color}>
                          {scopeConfig[item.scope].label}
                        </Tag>
                        <Space size={8}>
                          {item.fileTypes.map((t) => (
                            <span key={t}>{fileIcon[t] || <FileTextOutlined />}</span>
                          ))}
                        </Space>
                      </div>
                    </div>
                  </div>
                </Card>
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* 新建文档弹窗 — 与工作台右侧新建案件保持一致 */}
      <Modal
        title="新建文档（案件）"
        open={modalOpen}
        onCancel={closeModal}
        width={520}
        footer={[
          <Button key="cancel" onClick={closeModal}>
            取消
          </Button>,
          <Button
            key="ok"
            type="primary"
            loading={submitting}
            onClick={handleCreate}
          >
            创建
          </Button>,
        ]}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ scope: 'private' }}
          style={{ marginTop: 8 }}
        >
          <Form.Item
            name="name"
            label="案件名称"
            rules={[{ required: true, message: '请输入案件名称' }]}
          >
            <Input placeholder="如：张某诉李某合同纠纷" />
          </Form.Item>
          <Form.Item
            name="plaintiff"
            label="原告"
            rules={[{ required: true, message: '请输入原告' }]}
          >
            <Input placeholder="原告姓名/单位" />
          </Form.Item>
          <Form.Item
            name="defendant"
            label="被告"
            rules={[{ required: true, message: '请输入被告' }]}
          >
            <Input placeholder="被告姓名/单位" />
          </Form.Item>
          <Form.Item
            name="court"
            label="管辖法院"
            rules={[{ required: true, message: '请输入管辖法院' }]}
          >
            <Input placeholder="如：北京市朝阳区人民法院" />
          </Form.Item>
          <Form.Item name="summary" label="案件基本情况">
            <Input.TextArea rows={3} placeholder="简要描述案件情况（选填）" />
          </Form.Item>
          <Form.Item name="scope" label="可见范围">
            <Select
              options={[
                { value: 'private', label: '私库（仅自己可见）' },
                { value: 'public', label: '公库（协作可见）' },
              ]}
            />
          </Form.Item>
          <Form.Item label="案件资料">
            <Upload
              multiple
              fileList={fileList}
              beforeUpload={() => false}
              onChange={({ fileList }) => setFileList(fileList)}
              onRemove={(file) => {
                setFileList((list) => list.filter((f) => f.uid !== file.uid));
              }}
            >
              <Button icon={<PaperClipOutlined />}>上传资料</Button>
            </Upload>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              可上传判决书、证据、合同等文件
            </Typography.Text>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="案件未解锁"
        open={!!unlockTarget}
        onCancel={() => setUnlockTarget(null)}
        footer={null}
      >
        {unlockTarget && (
          <div>
            <Typography.Paragraph>
              案件 <Typography.Text strong>{unlockTarget.title}</Typography.Text> 不在你当前职级可见范围内。
            </Typography.Paragraph>
            <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
              <Button
                block
                onClick={() => {
                  message.success('已查看脱敏版（仅上诉书/判决书）');
                  setUnlockTarget(null);
                }}
              >
                查看脱敏版（仅上诉书/判决书）
              </Button>
              <Button
                block
                type="primary"
                onClick={() => {
                  message.success('已向经手律师发起阅读申请');
                  setUnlockTarget(null);
                }}
              >
                向经手律师申请解锁
              </Button>
            </Space>
          </div>
        )}
      </Modal>
    </div>
  );
}
