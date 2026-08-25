import { useEffect, useState } from 'react';
import {
  Button,
  Typography,
  Empty,
  Modal,
  Form,
  Input,
  Select,
  Upload,
  Tag,
  Tooltip,
  App,
  Spin,
} from 'antd';
import {
  PlusOutlined,
  FolderOutlined,
  PaperClipOutlined,
  RightOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useCaseStore } from '../../stores/caseStore';
import { colors } from '../../theme/tokens';

/**
 * 工作台右侧案件栏
 * 依据 figma-design-spec.md §3：案件列表 + 折叠/新增；新建案件弹窗 520px
 * 案件名称/原告/被告/管辖法院/基本情况 必填，可上传资料
 */
export default function CasePanel() {
  const { recentCases, currentCaseId, loading, loadRecent, createCase, selectCase } =
    useCaseStore();
  const navigate = useNavigate();
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const { message } = App.useApp();

  useEffect(() => {
    loadRecent();
  }, [loadRecent]);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const files = fileList
        .map((f) => f.originFileObj)
        .filter((f) => !!f) as File[];
      await createCase(values, files);
      message.success('案件已创建');
      setModalOpen(false);
      form.resetFields();
      setFileList([]);
    } catch {
      // 校验失败或创建失败，错误已由拦截器/校验提示
    } finally {
      setSubmitting(false);
    }
  };

  const closeModal = () => {
    setModalOpen(false);
    form.resetFields();
    setFileList([]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 标题栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: `1px solid ${colors.border}`,
        }}
      >
        <Typography.Text strong>案件</Typography.Text>
        <Tooltip title="新增案件">
          <Button
            type="text"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setModalOpen(true)}
          />
        </Tooltip>
      </div>

      {/* 案件列表 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
        {loading && recentCases.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin size="small" />
          </div>
        ) : recentCases.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ color: colors.muted, fontSize: 12 }}>
                最近 1 周暂无案件
              </span>
            }
          />
        ) : (
          // 渲染层按 id 去重，确保相同案件只出现一次
          (() => {
            const seen = new Set<number>();
            return recentCases
              .filter((c) => {
                if (seen.has(c.id)) return false;
                seen.add(c.id);
                return true;
              })
              .map((c) => (
            <div
              key={c.id}
              onClick={() => selectCase(c.id)}
              style={{
                padding: 10,
                marginBottom: 8,
                borderRadius: 10,
                border: `1px solid ${
                  currentCaseId === c.id ? colors.primary : colors.border
                }`,
                background: currentCaseId === c.id ? colors.primaryBg : colors.panel,
                cursor: 'pointer',
                transition: 'all .15s',
              }}
            >
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <FolderOutlined
                  style={{ color: colors.primary, marginTop: 2, flexShrink: 0 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Typography.Text
                    strong
                    ellipsis
                    style={{ display: 'block', fontSize: 13 }}
                  >
                    {c.name}
                  </Typography.Text>
                  <div style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>
                    {c.plaintiff} 诉 {c.defendant}
                  </div>
                  <div
                    style={{
                      marginTop: 6,
                      display: 'flex',
                      gap: 6,
                      alignItems: 'center',
                      flexWrap: 'wrap',
                    }}
                  >
                    <Tag
                      color={c.scope === 'private' ? colors.green : colors.primary}
                      style={{ margin: 0, fontSize: 11 }}
                    >
                      {c.scope === 'private' ? '私库' : '协作'}
                    </Tag>
                    {c.documents.length > 0 && (
                      <span style={{ fontSize: 11, color: colors.muted }}>
                        <PaperClipOutlined /> {c.documents.length}
                      </span>
                    )}
                  </div>
                </div>
                <Tooltip title="进入案件库">
                  <Button
                    type="text"
                    size="small"
                    icon={<RightOutlined />}
                    style={{ flexShrink: 0, color: colors.muted }}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/cases/${c.id}`);
                    }}
                  />
                </Tooltip>
              </div>
            </div>
          ))
          })()
        )}
        <div style={{ fontSize: 11, color: colors.muted, textAlign: 'center', marginTop: 8 }}>
          仅显示最近 1 周
        </div>
      </div>

      {/* 新建案件弹窗 */}
      <Modal
        title="新建案件"
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
    </div>
  );
}
