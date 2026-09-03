import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Button,
  Typography,
  Tag,
  List,
  Space,
  Spin,
  Empty,
  Upload,
  App,
  Descriptions,
} from 'antd';
import type { UploadFile } from 'antd';
import {
  ArrowLeftOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileImageOutlined,
  VideoCameraOutlined,
  PaperClipOutlined,
  DownloadOutlined,
  InboxOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { casesApi, type Case, type CaseDocument } from '../../api/cases';
import { colors } from '../../theme/tokens';
import FilePreviewModal from '../../components/chat/FilePreviewModal';

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

function formatFileSize(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * 案件详情页
 * 展示案件基本信息 + 文件资料列表，支持上传新资料。
 * 从工作台案件栏「进入」按钮或文档库点击案件均可到达。
 */
export default function CaseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [previewTarget, setPreviewTarget] = useState<CaseDocument | null>(null);

  const caseId = id ? parseInt(id, 10) : 0;

  // 判断文件能否在线预览
  const canPreviewDoc = (doc: CaseDocument): boolean => {
    const ext = doc.file_name.split('.').pop()?.toLowerCase() || '';
    const EMBED = new Set(['pdf']);
    const IMG = new Set(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']);
    const VID = new Set(['mp4', 'mov', 'avi', 'webm', 'mkv', 'm4v']);
    const TXT = new Set(['docx', 'txt']);
    return EMBED.has(ext) || IMG.has(ext) || VID.has(ext) || TXT.has(ext);
  };

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    casesApi
      .get(caseId)
      .then((data) => {
        setCaseData(data);
        // 同步 touch 更新最近打开时间
        casesApi.touch(caseId).catch(() => undefined);
      })
      .catch(() => {
        message.error('案件加载失败');
      })
      .finally(() => setLoading(false));
  }, [caseId, message]);

  const handleUpload = async (file: File): Promise<void> => {
    setUploading(true);
    try {
      await casesApi.uploadDocument(caseId, file);
      message.success(`${file.name} 上传成功`);
      // 刷新案件数据
      const updated = await casesApi.get(caseId);
      setCaseData(updated);
      setFileList([]);
    } catch {
      message.error('上传失败');
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!caseData) {
    return (
      <div style={{ padding: 24, height: '100%' }}>
        <Empty description="案件不存在" />
      </div>
    );
  }

  const documents = caseData.documents || [];

  return (
    <>
    <div style={{ padding: 24, height: '100%', overflow: 'auto', background: colors.background }}>
      {/* 返回栏 */}
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(-1)}
        >
          返回
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {caseData.name}
        </Typography.Title>
        <Tag color={scopeConfig[caseData.scope]?.color || colors.primary}>
          {scopeConfig[caseData.scope]?.label || caseData.scope}
        </Tag>
      </div>

      {/* 基本信息 */}
      <Card title="案件基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="原告">{caseData.plaintiff}</Descriptions.Item>
          <Descriptions.Item label="被告">{caseData.defendant}</Descriptions.Item>
          <Descriptions.Item label="管辖法院">{caseData.court}</Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {caseData.created_at.slice(0, 10)}
          </Descriptions.Item>
          {caseData.summary && (
            <Descriptions.Item label="案件概况" span={2}>
              {caseData.summary}
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      {/* 文件资料 */}
      <Card
        title={
          <Space>
            <PaperClipOutlined />
            <span>文件资料 ({documents.length})</span>
          </Space>
        }
        extra={
          <Upload
            multiple
            fileList={fileList}
            showUploadList={false}
            beforeUpload={(file) => {
              handleUpload(file);
              return false;
            }}
            onChange={({ fileList }) => setFileList(fileList)}
          >
            <Button
              type="primary"
              icon={<InboxOutlined />}
              loading={uploading}
            >
              上传资料
            </Button>
          </Upload>
        }
      >
        {documents.length === 0 ? (
          <Empty description="暂无文件资料" />
        ) : (
          <List
            dataSource={documents}
            renderItem={(doc: CaseDocument) => (
              <List.Item
                actions={[
                  canPreviewDoc(doc) && (
                    <Button
                      key="preview"
                      type="link"
                      icon={<EyeOutlined />}
                      style={{ padding: 0 }}
                      onClick={() => setPreviewTarget(doc)}
                    >
                      预览
                    </Button>
                  ),
                  <a
                    key="download"
                    href={doc.file_url}
                    download={doc.file_name}
                  >
                    <Button
                      type="link"
                      icon={<DownloadOutlined />}
                      style={{ padding: 0 }}
                    >
                      下载
                    </Button>
                  </a>,
                ].filter(Boolean)}
              >
                <List.Item.Meta
                  avatar={fileIcon[doc.file_type || ''] || <FileTextOutlined />}
                  title={
                    <Typography.Text ellipsis style={{ maxWidth: 400 }}>
                      {doc.file_name}
                    </Typography.Text>
                  }
                  description={`${formatFileSize(doc.file_size)} · ${doc.created_at.slice(0, 10)}`}
                />
              </List.Item>
            )}
          />
        )}
      </Card>
    </div>

    <FilePreviewModal
      open={!!previewTarget}
      fileUrl={previewTarget?.file_url || ''}
      fileName={previewTarget?.file_name || ''}
      fileType={previewTarget?.file_type || null}
      onClose={() => setPreviewTarget(null)}
    />
    </>
  );
}
