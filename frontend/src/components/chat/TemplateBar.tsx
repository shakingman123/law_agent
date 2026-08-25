import { useEffect, useState, useMemo } from 'react';
import {
  Grid,
  Tag,
  Tooltip,
  Modal,
  Form,
  Input,
  Select,
  Upload,
  Button,
  App,
} from 'antd';
import {
  FileTextOutlined,
  PlusOutlined,
  GlobalOutlined,
  LockOutlined,
  UploadOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { templatesApi, type DocTemplate } from '../../api/templates';
import { colors } from '../../theme/tokens';

interface TemplateBarProps {
  selectedId: number | null;
  onSelect: (tpl: DocTemplate | null) => void;
}

const DOC_TYPE_OPTIONS = [
  { value: '起诉状', label: '起诉状' },
  { value: '答辩状', label: '答辩状' },
  { value: '反诉状', label: '反诉状' },
  { value: '上诉状', label: '上诉状' },
  { value: '代理词', label: '代理词' },
  { value: '再审申请书', label: '再审申请书' },
  { value: '申请书', label: '申请书' },
  { value: '异议书', label: '异议书' },
  { value: '授权委托书', label: '授权委托书' },
  { value: '身份证明书', label: '身份证明书' },
  { value: '其他', label: '其他' },
];

/** 模板卡片专用色板 */
const TPL_COLORS = {
  primary: '#4F6EF7',
  primaryBg: 'rgba(79, 110, 247, 0.06)',
  primaryBorder: 'rgba(79, 110, 247, 0.3)',
  text: '#1A1A2E',
  secondary: '#6B7280',
  border: '#E3E8EF',
  panel: '#FFFFFF',
  shadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
  shadowHover: '0 4px 12px rgba(79, 110, 247, 0.12)',
};

/** 从模板内容中提取 {{占位符}} */
function extractPlaceholders(content: string): string[] {
  const regex = /\{\{([^}]+)\}\}/g;
  const matches: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = regex.exec(content)) !== null) {
    const ph = m[1].trim();
    if (ph && !matches.includes(ph)) {
      matches.push(ph);
    }
  }
  return matches;
}

/**
 * 模板库卡片网格（对话框下方）
 * 响应式布局：宽屏 4 列 / 中屏 3 列 / 窄屏 2 列
 * 卡片：图标 + 名称 + 副标题（分类），悬停上浮
 * 新建卡片：虚线边框
 * 网格区域可滚动（高度约为单行的 2 倍）
 */
export default function TemplateBar({ selectedId, onSelect }: TemplateBarProps) {
  const screens = Grid.useBreakpoint();
  const [templates, setTemplates] = useState<DocTemplate[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  const [content, setContent] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [extracting, setExtracting] = useState(false);
  const { message } = App.useApp();

  // 响应式列数：宽屏 4 / 中屏 3 / 窄屏 2
  const colCount = screens.lg || screens.xl ? 4 : screens.md ? 3 : 2;

  const loadTemplates = () => {
    templatesApi.list().then(setTemplates).catch(() => {});
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  // 自动提取占位符
  const extractedPlaceholders = useMemo(() => extractPlaceholders(content), [content]);

  const handleFileUpload = async (file: File) => {
    const fileName = file.name;
    const ext = fileName.split('.').pop()?.toLowerCase() || '';
    // .txt/.md 本地读取，.pdf/.docx 上传后端提取
    if (ext === 'txt' || ext === 'md' || ext === 'markdown') {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = (e.target?.result as string) || '';
        setContent(text);
        message.success(`已读取 ${fileName}`);
      };
      reader.onerror = () => message.error('文件读取失败');
      reader.readAsText(file, 'utf-8');
      return false;
    }
    // PDF / Word → 后端提取
    setExtracting(true);
    message.loading({ content: '正在提取文本...', key: 'tpl-extract', duration: 0 });
    try {
      const result = await templatesApi.extractFile(file);
      message.destroy('tpl-extract');
      setContent(result.text);
      message.success(`已提取 ${fileName}（${result.char_count} 字）`);
    } catch {
      message.destroy('tpl-extract');
      message.error('文件提取失败，请检查文件格式');
    } finally {
      setExtracting(false);
    }
    return false;
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      if (!content.trim()) {
        message.warning('模板内容不能为空');
        return;
      }
      setSubmitting(true);
      await templatesApi.create({
        name: values.name,
        doc_type: values.doc_type,
        content,
        placeholders: extractedPlaceholders,
      });
      message.success('模板已创建');
      setModalOpen(false);
      form.resetFields();
      setContent('');
      setFileList([]);
      loadTemplates();
    } catch {
      // 校验失败或创建失败
    } finally {
      setSubmitting(false);
    }
  };

  const closeModal = () => {
    setModalOpen(false);
    form.resetFields();
    setContent('');
    setFileList([]);
  };

  const handleDelete = (tpl: DocTemplate) => {
    Modal.confirm({
      title: '删除模板',
      content: `确定删除「${tpl.name}」？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await templatesApi.remove(tpl.id);
          message.success('已删除');
          if (selectedId === tpl.id) onSelect(null);
          loadTemplates();
        } catch {
          message.error('删除失败');
        }
      },
    });
  };

  /** 模板卡片基础样式 */
  const cardStyle = (active: boolean): React.CSSProperties => ({
    padding: '12px 16px',
    borderRadius: 10,
    border: active
      ? `1px solid ${TPL_COLORS.primary}`
      : `1px solid ${TPL_COLORS.border}`,
    background: active ? TPL_COLORS.primaryBg : TPL_COLORS.panel,
    boxShadow: active ? 'none' : TPL_COLORS.shadow,
    transition: 'all 0.2s ease',
    cursor: 'pointer',
    position: 'relative',
    minHeight: 56,
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  });

  /** 新建卡片样式（虚线边框） */
  const newCardStyle: React.CSSProperties = {
    padding: '12px 16px',
    borderRadius: 10,
    border: `1px dashed ${TPL_COLORS.primaryBorder}`,
    background: TPL_COLORS.primaryBg,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    minHeight: 56,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  };

  return (
    <div
      style={{
        padding: '12px 16px 16px',
        borderTop: `1px solid ${colors.border}`,
        background: colors.background,
        flexShrink: 0,
      }}
    >
      {/* 标题 */}
      <div
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: TPL_COLORS.text,
          marginBottom: 12,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <FileTextOutlined style={{ color: TPL_COLORS.primary }} />
        模板库
        {selectedId && (
          <Tag
            color={TPL_COLORS.primary}
            closable
            onClose={() => onSelect(null)}
            style={{ marginLeft: 8, fontSize: 11 }}
          >
            已选模板
          </Tag>
        )}
      </div>

      {/* 卡片网格（可滚动，高度约为单行 2 倍） */}
      <div
        className="tpl-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${colCount}, 1fr)`,
          gap: 12,
          maxHeight: 98,
          overflowY: 'auto',
          paddingRight: 8,
        }}
      >
        {templates.map((tpl) => {
          const active = tpl.id === selectedId;
          const isPublic = tpl.scope === 'public';
          return (
            <Tooltip
              key={tpl.id}
              title={`${tpl.doc_type} · 占位符：${tpl.placeholders.join('、') || '无'}`}
            >
              <div
                className="tpl-card"
                style={cardStyle(active)}
                onClick={() => onSelect(active ? null : tpl)}
              >
                {/* 删除按钮（私有模板，hover 显示） */}
                {!isPublic && (
                  <DeleteOutlined
                    className="tpl-card-del"
                    style={{
                      position: 'absolute',
                      top: 8,
                      right: 8,
                      fontSize: 13,
                      color: TPL_COLORS.secondary,
                      cursor: 'pointer',
                      padding: 2,
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(tpl);
                    }}
                  />
                )}
                {/* 图标 */}
                {isPublic ? (
                  <GlobalOutlined
                    style={{ color: TPL_COLORS.primary, fontSize: 16 }}
                  />
                ) : (
                  <LockOutlined
                    style={{ color: TPL_COLORS.secondary, fontSize: 16 }}
                  />
                )}
                {/* 名称 */}
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: TPL_COLORS.text,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {tpl.name}
                </div>
                {/* 副标题（分类） */}
                <div style={{ fontSize: 12, color: TPL_COLORS.secondary }}>
                  {tpl.doc_type}
                </div>
              </div>
            </Tooltip>
          );
        })}

        {/* 新建卡片 */}
        <div
          className="tpl-new-card"
          style={newCardStyle}
          onClick={() => setModalOpen(true)}
        >
          <PlusOutlined style={{ fontSize: 20, color: TPL_COLORS.primary }} />
          <span style={{ fontSize: 12, color: TPL_COLORS.primary, fontWeight: 500 }}>
            新建模板
          </span>
        </div>
      </div>

      {/* 悬停效果 + 滚动条样式 */}
      <style>{`
        .tpl-card {
          transition: all 0.2s ease;
        }
        .tpl-card:hover {
          transform: translateY(-2px);
          box-shadow: ${TPL_COLORS.shadowHover};
        }
        .tpl-card-del {
          opacity: 0;
          transition: opacity 0.2s;
        }
        .tpl-card:hover .tpl-card-del {
          opacity: 1;
        }
        .tpl-card-del:hover {
          color: ${colors.danger} !important;
        }
        .tpl-new-card {
          transition: all 0.2s ease;
        }
        .tpl-new-card:hover {
          transform: translateY(-2px);
          border-color: ${TPL_COLORS.primary};
          background: ${TPL_COLORS.primaryBg};
          box-shadow: ${TPL_COLORS.shadowHover};
        }
        .tpl-grid::-webkit-scrollbar {
          width: 6px;
        }
        .tpl-grid::-webkit-scrollbar-track {
          background: transparent;
        }
        .tpl-grid::-webkit-scrollbar-thumb {
          background: #D1D5DB;
          border-radius: 3px;
        }
        .tpl-grid::-webkit-scrollbar-thumb:hover {
          background: #9CA3AF;
        }
      `}</style>

      {/* 新建模板弹窗 */}
      <Modal
        title="新建模板"
        open={modalOpen}
        onCancel={closeModal}
        width={640}
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
          initialValues={{ doc_type: '起诉状' }}
          style={{ marginTop: 8 }}
        >
          <Form.Item
            name="name"
            label="模板名称"
            rules={[{ required: true, message: '请输入模板名称' }]}
          >
            <Input placeholder="如：民间借贷起诉状" />
          </Form.Item>
          <Form.Item
            name="doc_type"
            label="模板分类"
            rules={[{ required: true, message: '请选择模板分类' }]}
          >
            <Select options={DOC_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item label="模板内容" required>
            <div style={{ marginBottom: 4, display: 'flex', gap: 8, alignItems: 'center' }}>
              <Upload
                accept=".txt,.md,.markdown,.pdf,.docx"
                fileList={fileList}
                showUploadList={false}
                beforeUpload={(file) => {
                  setFileList([file as unknown as UploadFile]);
                  return handleFileUpload(file as unknown as File);
                }}
              >
                <Button size="small" icon={<UploadOutlined />} loading={extracting}>
                  上传文件
                </Button>
              </Upload>
              <span style={{ fontSize: 11, color: colors.muted }}>
                支持 .txt / .md / .pdf / .docx
              </span>
            </div>
            <Input.TextArea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={10}
              placeholder={
                '在此粘贴或编辑模板内容。\n' +
                '使用 {{占位符}} 标记需要填充的字段，例如：\n' +
                '原告：{{原告}}\n被告：{{被告}}\n\n诉讼请求：\n{{诉讼请求}}'
              }
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
            {extractedPlaceholders.length > 0 && (
              <div style={{ marginTop: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12, color: colors.muted }}>已识别占位符：</span>
                {extractedPlaceholders.map((ph) => (
                  <Tag key={ph} style={{ margin: 0, fontSize: 11 }}>
                    {ph}
                  </Tag>
                ))}
              </div>
            )}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
