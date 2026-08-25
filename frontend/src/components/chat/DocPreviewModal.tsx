import { useEffect, useState } from 'react';
import { Modal, Button, Input, Typography, Spin, App } from 'antd';
import {
  CheckOutlined,
  EditOutlined,
  FilePdfOutlined,
  FileWordOutlined,
} from '@ant-design/icons';
import type { DraftResult } from '../../api/chat';
import { chatApi } from '../../api/chat';
import { colors } from '../../theme/tokens';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

interface DocPreviewModalProps {
  open: boolean;
  result: DraftResult | null;
  onClose: () => void;
  /** 定稿完成回调（更新消息流 + 关闭弹窗） */
  onFinalized: (fileUrl: string, pdfUrl: string, docType: string) => void;
}

/**
 * 文书预览弹窗
 * 依据 figma-design-spec.md §3：A4 纸样式预览 + 「微调重写 / 确认生成」双按钮。
 *
 * 流程：
 * 1. agent 生成草稿 → 弹窗展示 A4 预览
 * 2. 用户「确认生成」→ /resume confirmed=true → 生成 docx+pdf → 显示下载链接
 * 3. 用户填写补充信息后「微调重写」→ /resume confirmed=false, feedback → 重新生成，停留在预览
 */
export default function DocPreviewModal({
  open,
  result,
  onClose,
  onFinalized,
}: DocPreviewModalProps) {
  const { message } = App.useApp();
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // 内部维护最新草稿（微调后更新），初始取 result.draft
  const [draft, setDraft] = useState('');
  const [missing, setMissing] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [fileUrl, setFileUrl] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');

  // result 变化时同步内部草稿状态
  useEffect(() => {
    if (!result) return;
    setFeedback('');
    setSubmitting(false);
    setDraft(result.draft);
    setMissing(result.missing_fields);
    setDone(false);
    setFileUrl('');
    setPdfUrl('');
  }, [result?.thread_id, result?.draft]);

  const handleResume = async (confirmed: boolean) => {
    if (!result) return;
    setSubmitting(true);
    try {
      const res = await chatApi.resumeDraft(result.thread_id, {
        confirmed,
        feedback: confirmed ? undefined : feedback,
      });
      if (res.done) {
        setDone(true);
        setFileUrl(res.file_url);
        setPdfUrl(res.pdf_url);
        onFinalized(res.file_url, res.pdf_url, res.doc_type);
      } else if (res.awaiting_review) {
        // 微调后新草稿
        setDraft(res.draft);
        setMissing(res.missing_fields);
        setFeedback('');
      }
      if (res.error) {
        message.error(res.error);
      }
    } catch {
      message.error('操作失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  if (!result) return null;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={720}
      footer={null}
      title={
        <span>
          文书预览
          {result.doc_type && (
            <Text type="secondary" style={{ fontSize: 13, marginLeft: 8 }}>
              {result.doc_type}
            </Text>
          )}
        </span>
      }
    >
      {/* A4 纸样式预览 */}
      <div
        style={{
          maxHeight: 440,
          overflowY: 'auto',
          background: colors.background,
          padding: 16,
          borderRadius: 8,
        }}
      >
        <div
          style={{
            background: '#fff',
            padding: '32px 40px',
            minHeight: 360,
            boxShadow: '0 1px 4px rgba(0,0,0,.08)',
            fontFamily: '"宋体", SimSun, serif',
            fontSize: 14,
            lineHeight: 1.8,
            whiteSpace: 'pre-wrap',
            color: '#000',
          }}
        >
          {draft || result?.draft || '（草稿生成中...）'}
        </div>
      </div>

      {/* 缺失字段提示 */}
      {missing.length > 0 && !done && (
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            以下信息未从案件/输入中获取，已由模型补全：{missing.join('、')}
          </Text>
        </div>
      )}

      {/* 定稿后：下载链接 */}
      {done ? (
        <div
          style={{
            marginTop: 16,
            padding: 16,
            background: colors.panel,
            borderRadius: 8,
            textAlign: 'center',
          }}
        >
          <Paragraph style={{ marginBottom: 12 }}>
            <CheckOutlined style={{ color: '#52c41a', marginRight: 8 }} />
            文书已生成，请下载：
          </Paragraph>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
            <Button type="primary" icon={<FileWordOutlined />} href={fileUrl} target="_blank">
              下载 Word
            </Button>
            <Button icon={<FilePdfOutlined />} href={pdfUrl} target="_blank">
              下载 PDF
            </Button>
          </div>
          <Button type="link" onClick={onClose} style={{ marginTop: 8 }}>
            关闭
          </Button>
        </div>
      ) : (
        /* 未定稿：微调 + 确认 */
        <div style={{ marginTop: 16 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            如需补充信息或修改，请在下方填写后点击「微调重写」：
          </Text>
          <TextArea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="例：诉讼请求增加「被告承担本案诉讼费」；事实与理由补充..."
            autoSize={{ minRows: 2, maxRows: 4 }}
            style={{ marginTop: 6, marginBottom: 12 }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button
              icon={<EditOutlined />}
              onClick={() => handleResume(false)}
              disabled={submitting || !feedback.trim()}
              loading={submitting}
            >
              微调重写
            </Button>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              onClick={() => handleResume(true)}
              loading={submitting}
            >
              确认生成
            </Button>
          </div>
        </div>
      )}

      {submitting && (
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <Spin tip="模型处理中..." />
        </div>
      )}
    </Modal>
  );
}
