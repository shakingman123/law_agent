import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  Popconfirm,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  CloudUploadOutlined,
  DeleteOutlined,
  FileTextOutlined,
  GlobalOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  knowledgeApi,
  type KnowledgeDoc,
  type KnowledgeKey,
  type KnowledgeSearchHit,
} from '../../api/knowledge';

/** 三个知识库的配置：key 与后端 collection_key 对应 */
const LIB_TABS: { key: KnowledgeKey; label: string; desc: string }[] = [
  { key: 'law', label: '法条库', desc: '民法典 / 刑法 / 司法解释等法律条文，供法条检索 Agent 引用' },
  { key: 'case', label: '判例库', desc: '公司脱敏判例、指导案例' },
  { key: 'wechat', label: '观点库', desc: '公众号法律观点文章' },
];

const PAGE_SIZE = 20;

/** 单个知识库面板：上传 + 列表管理 + 语义搜索 */
function KnowledgePanel({ libKey }: { libKey: KnowledgeKey }) {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [nextOffset, setNextOffset] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [keyword, setKeyword] = useState('');
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<KnowledgeSearchHit[] | null>(null);

  const [urlInput, setUrlInput] = useState('');
  const [ingesting, setIngesting] = useState(false);

  /** 加载列表（reset=true 回到第一页） */
  const load = useCallback(
    async (reset = false) => {
      setLoading(true);
      try {
        const r = await knowledgeApi.list(libKey, PAGE_SIZE, reset ? '' : nextOffset || '');
        setDocs((prev) => (reset ? r.points : [...prev, ...r.points]));
        setNextOffset(r.next_offset);
      } catch {
        /* 拦截器已提示 */
      } finally {
        setLoading(false);
      }
    },
    [libKey, nextOffset],
  );

  useEffect(() => {
    load(true);
    // 切换库时重置搜索状态
    setKeyword('');
    setHits(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libKey]);

  const onSearch = async (q: string) => {
    const query = q.trim();
    if (!query) {
      setHits(null);
      return;
    }
    setSearching(true);
    try {
      const r = await knowledgeApi.search(query, libKey, 10);
      setHits(r.hits);
    } catch {
      /* 拦截器已提示 */
    } finally {
      setSearching(false);
    }
  };

  const onRemove = async (id: string) => {
    try {
      await knowledgeApi.remove(libKey, id);
      message.success('已删除');
      if (hits !== null) {
        setHits((prev) => (prev ? prev.filter((h) => h.content !== docs.find((d) => d.id === id)?.content) : prev));
      }
      load(true);
    } catch {
      /* 拦截器已提示 */
    }
  };

  const onIngestUrl = async () => {
    const url = urlInput.trim();
    if (!url) {
      message.warning('请输入网页 URL');
      return;
    }
    setIngesting(true);
    try {
      const r = await knowledgeApi.ingestUrl(url, libKey);
      message.success(`网页「${r.title}」入库成功，共切分 ${r.ingested_chunks} 块`);
      setUrlInput('');
      load(true);
    } catch {
      /* 拦截器已提示 */
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* URL 抓取入库 */}
      <Input.Search
        prefix={<GlobalOutlined style={{ color: '#999' }} />}
        placeholder="粘贴网页 URL（需公开可访问），抓取正文后自动入库…"
        value={urlInput}
        onChange={(e) => setUrlInput(e.target.value)}
        onSearch={onIngestUrl}
        enterButton={
          <Button type="primary" loading={ingesting}>
            抓取入库
          </Button>
        }
        allowClear
        style={{ maxWidth: 640 }}
      />

      {/* 上传区 */}
      <Upload.Dragger
        multiple
        accept=".txt,.md,.pdf,.docx,.html,.htm"
        showUploadList={{ showRemoveIcon: false }}
        customRequest={async ({ file, onSuccess, onError }) => {
          setUploading(true);
          try {
            const r = await knowledgeApi.upload(file as File, libKey);
            message.success(`${r.file_name} 入库成功，共切分 ${r.ingested_chunks} 块`);
            onSuccess?.(r);
            load(true);
          } catch (e) {
            onError?.(e as Error);
          } finally {
            setUploading(false);
          }
        }}
        style={{ background: '#fff' }}
      >
        <Spin spinning={uploading}>
          <p className="ant-upload-drag-icon">
            <CloudUploadOutlined style={{ fontSize: 40, color: '#1677ff' }} />
          </p>
          <p className="ant-upload-text">点击或拖拽文件上传到{LIB_TABS.find((t) => t.key === libKey)?.label}</p>
          <p className="ant-upload-hint">
            支持 .txt / .md / .pdf / .docx / .html，单个文件 ≤ 20MB，上传后自动切块并向量化入库
          </p>
        </Spin>
      </Upload.Dragger>

      {/* 搜索 + 刷新 */}
      <Space.Compact style={{ width: '100%', maxWidth: 560 }}>
        <Input
          prefix={<SearchOutlined style={{ color: '#999' }} />}
          placeholder="语义搜索本库已入库内容…"
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value);
            if (!e.target.value.trim()) setHits(null);
          }}
          onPressEnter={() => onSearch(keyword)}
          allowClear
        />
        <Button type="primary" loading={searching} onClick={() => onSearch(keyword)}>
          搜索
        </Button>
      </Space.Compact>

      {/* 搜索结果 */}
      {hits !== null ? (
        <Card size="small" title={`搜索结果（${hits.length} 条，按相关度排序）`} extra={<Button type="link" onClick={() => { setHits(null); setKeyword(''); }}>返回列表</Button>}>
          {hits.length === 0 ? (
            <Empty description="没有找到相关内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={hits}
              renderItem={(h, idx) => (
                <List.Item
                  actions={[
                    <Tag key="score" color="blue">
                      相关度 {(h.score * 100).toFixed(0)}%
                    </Tag>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space size={8}>
                        <Tag>[{idx + 1}]</Tag>
                        <span>{h.title || '（无标题）'}</span>
                        <Tag>{h.source}</Tag>
                      </Space>
                    }
                    description={
                      <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 0, color: '#666' }}>
                        {h.content}
                      </Typography.Paragraph>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      ) : (
        /* 已入库条目列表 */
        <Card
          size="small"
          title={`已入库条目`}
          extra={
            <Button icon={<ReloadOutlined />} size="small" onClick={() => load(true)}>
              刷新
            </Button>
          }
        >
          <Spin spinning={loading}>
            {docs.length === 0 && !loading ? (
              <Empty description="暂无入库内容，先上传一个文件吧" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <>
                <List
                  dataSource={docs}
                  renderItem={(d) => (
                    <List.Item
                      actions={[
                        <Popconfirm key="del" title="确认删除该条目？" description="删除后法条检索将无法引用该内容" onConfirm={() => onRemove(d.id)}>
                          <Button danger type="text" size="small" icon={<DeleteOutlined />}>
                            删除
                          </Button>
                        </Popconfirm>,
                      ]}
                    >
                      <List.Item.Meta
                        avatar={<FileTextOutlined style={{ fontSize: 22, color: '#1677ff' }} />}
                        title={
                          <Space size={8} wrap>
                            <span>{d.title || '（无标题）'}</span>
                            {typeof d.chunk_index === 'number' && typeof d.total_chunks === 'number' && (
                              <Tag>
                                第 {d.chunk_index + 1}/{d.total_chunks} 块
                              </Tag>
                            )}
                            {d.file_name && <Tag color="cyan">{d.file_name}</Tag>}
                          </Space>
                        }
                        description={
                          <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0, color: '#666' }}>
                            {d.content}
                          </Typography.Paragraph>
                        }
                      />
                    </List.Item>
                  )}
                />
                {nextOffset && (
                  <div style={{ textAlign: 'center', marginTop: 12 }}>
                    <Button loading={loading} onClick={() => load(false)}>
                      加载更多
                    </Button>
                  </div>
                )}
              </>
            )}
          </Spin>
        </Card>
      )}
    </div>
  );
}

/** 知识库管理页（仅管理员）：三库上传 + 检索管理 */
export default function KnowledgePage() {
  return (
    <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
      <Card
        title={
          <Typography.Title level={4} style={{ margin: 0 }}>
            知识库
          </Typography.Title>
        }
        styles={{ body: { padding: 16 } }}
      >
        <Tabs
          items={LIB_TABS.map((t) => ({
            key: t.key,
            label: t.label,
            children: <KnowledgePanel libKey={t.key} />,
          }))}
        />
      </Card>
    </div>
  );
}
