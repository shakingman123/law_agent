import { useEffect, useState } from 'react';
import { Modal, Spin, Empty, Typography } from 'antd';
import { colors } from '../../theme/tokens';
import request from '../../api/request';

const { Text, Paragraph } = Typography;

interface FilePreviewModalProps {
  open: boolean;
  fileUrl: string;
  fileName: string;
  /** 后端存储的 file_type（可能是 docx/pdf/image/video/...） */
  fileType: string | null;
  onClose: () => void;
}

/**
 * 通用文件预览弹窗。
 *
 * 预览策略：
 * - PDF / 图片 / 视频  → iframe / img / video 直接用 fileUrl 内联预览（浏览器原生）
 * - docx / doc         → 调 GET /api/files/preview-text?path=xxx 提取纯文本展示
 * - txt                → fetch 原始文本
 * - 其他格式           → 提示"请下载后用对应软件打开"
 */
export default function FilePreviewModal({
  open,
  fileUrl,
  fileName,
  onClose,
}: FilePreviewModalProps) {
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ext = fileName.split('.').pop()?.toLowerCase() || '';

  // 能内联预览（iframe/img/video）的格式
  const EMBED_TYPES = new Set(['pdf']);
  const IMAGE_EXTS = new Set(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']);
  const VIDEO_EXTS = new Set(['mp4', 'mov', 'avi', 'webm', 'mkv', 'm4v']);
  const TEXT_PREVIEW_EXTS = new Set(['doc', 'docx', 'txt']);

  const canEmbed = EMBED_TYPES.has(ext);
  const isImage = IMAGE_EXTS.has(ext);
  const isVideo = VIDEO_EXTS.has(ext);
  const canTextPreview = TEXT_PREVIEW_EXTS.has(ext);

  // 弹窗打开时按需加载文本（docx / txt）
  useEffect(() => {
    if (!open) {
      setText(null);
      setError(null);
      return;
    }
    if (canTextPreview) {
      // 从 fileUrl 提取 path（去掉 /api/files/ 前缀）
      const path = fileUrl.replace(/^\/api\/files\//, '');
      if (!path) return;

      setLoading(true);
      request
        .get<{ text: string; file_type: string; max_excerpt: boolean }>(
          '/files/preview-text',
          { params: { path } },
        )
        .then((r) => setText(r.data.text))
        .catch((e) => setError(e?.response?.data?.detail || '预览加载失败'))
        .finally(() => setLoading(false));
    }
  }, [open, fileUrl, canTextPreview]);

  const titleText = (
    <span>
      文件预览
      <Text type="secondary" style={{ fontSize: 13, marginLeft: 8 }}>
        {fileName}
      </Text>
    </span>
  );

  const body = (() => {
    if (canEmbed || isImage || isVideo) {
      // 浏览器原生支持的格式，直接用 fileUrl 内联
      return (
        <div style={{ height: 560, overflow: 'auto', background: colors.background }}>
          {isImage && (
            <img
              src={fileUrl}
              alt={fileName}
              style={{ maxWidth: '100%', maxHeight: 560, display: 'block', margin: '0 auto' }}
            />
          )}
          {isVideo && (
            <video
              src={fileUrl}
              controls
              style={{ width: '100%', maxHeight: 560 }}
            />
          )}
          {canEmbed && (
            <iframe
              src={fileUrl}
              title={fileName}
              style={{ width: '100%', height: 560, border: 'none' }}
            />
          )}
        </div>
      );
    }

    if (canTextPreview) {
      if (loading) {
        return (
          <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin tip="正在提取文件内容..." />
          </div>
        );
      }
      if (error) {
        return (
          <Empty
            description={
              <span style={{ color: colors.muted }}>
                {error}
                <br />
                <a href={fileUrl} download={fileName}>
                  点击下载
                </a>
              </span>
            }
          />
        );
      }
      return (
        <div
          style={{
            height: 560,
            overflowY: 'auto',
            background: '#fff',
            padding: '20px 28px',
            borderRadius: 4,
            border: `1px solid ${colors.border}`,
            fontFamily: '"宋体", SimSun, serif',
            fontSize: 14,
            lineHeight: 1.8,
            whiteSpace: 'pre-wrap',
          }}
        >
          {text || '（文件内容为空）'}
        </div>
      );
    }

    // 不支持预览的格式
    return (
      <Empty
        description={
          <div>
            <Paragraph>该文件格式暂不支持在线预览</Paragraph>
            <Paragraph type="secondary" style={{ marginTop: -8 }}>
              请下载后用对应软件打开
            </Paragraph>
            <a href={fileUrl} download={fileName}>
              下载文件：{fileName}
            </a>
          </div>
        }
      />
    );
  })();

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={canEmbed || isImage || isVideo ? 900 : 720}
      footer={null}
      title={titleText}
    >
      {body}
    </Modal>
  );
}
