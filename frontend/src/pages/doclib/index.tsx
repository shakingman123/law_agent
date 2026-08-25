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
} from 'antd';
import {
  SearchOutlined,
  LockOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileImageOutlined,
  VideoCameraOutlined,
  FolderOutlined,
} from '@ant-design/icons';
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
 */
export default function DocLib() {
  const [unlocked, setUnlocked] = useState(false);
  const [password, setPassword] = useState('');
  const [tab, setTab] = useState<Tab>('全部');
  const [keyword, setKeyword] = useState('');
  const [unlockTarget, setUnlockTarget] = useState<DocCase | null>(null);
  const { message } = App.useApp();
  const { allCases, loading, loadAll } = useCaseStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (unlocked) {
      loadAll();
    }
  }, [unlocked, loadAll]);

  const docCases = allCases.map(mapCaseToDoc);

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
          </Space>
        }
        styles={{ body: { padding: 16 } }}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin />
          </div>
        ) : filteredCases.length === 0 ? (
          <Empty description="暂无匹配案件" />
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
