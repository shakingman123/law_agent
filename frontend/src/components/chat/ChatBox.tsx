import { useEffect, useRef, useState } from 'react';
import {
  Input,
  Button,
  Typography,
  Empty,
  Tooltip,
  Upload,
  Tag,
  Spin,
  Modal,
} from 'antd';
import type { UploadFile } from 'antd';
import {
  SendOutlined,
  PaperClipOutlined,
  RobotOutlined,
  LinkOutlined,
  FileTextOutlined,
  BookOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '../../stores/authStore';
import { useLlmStore } from '../../stores/llmStore';
import { useCaseStore } from '../../stores/caseStore';
import { useChatStore } from '../../stores/chatStore';
import { chatApi, type DraftResult } from '../../api/chat';
import { filesApi, type FileUploadResult } from '../../api/files';
import type { ChatMessage, Citation } from '../../api/conversations';
import type { DocTemplate } from '../../api/templates';
import { colors } from '../../theme/tokens';
import { useNavigate } from 'react-router-dom';
import TemplateBar from './TemplateBar';
import DocPreviewModal from './DocPreviewModal';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Attachment {
  uid: string;
  fileName: string;
  url: string;
}

/**
 * 对话窗口
 * 依据 figma-design-spec.md §3：消息流 + 输入区（附件 + 输入框 + 发送）
 *
 * 消息持久化：
 * - 历史消息从后端 /conversations/{id} 加载，存 chatStore（全局 state）
 * - 切换页面/刷新后回到工作台，chatStore.init() 重新拉取当前会话历史
 * - 发送消息时本地先占位追加，后端回复到达后更新最后一条 agent 消息
 */
export default function ChatBox() {
  const { user } = useAuthStore();
  const { companyConfig, personalConfig, loadAll } = useLlmStore();
  const { getCurrentCase } = useCaseStore();
  const { messages, currentConversationId, loading, init, appendLocalMessage, updateLastAgentMessage } =
    useChatStore();
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [useRag, setUseRag] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState<DocTemplate | null>(null);
  const [draftResult, setDraftResult] = useState<DraftResult | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [citationModal, setCitationModal] = useState<Citation | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamControllerRef = useRef<(() => void) | null>(null);
  const streamBufferRef = useRef('');

  useEffect(() => {
    if (user) {
      loadAll(user.isAdmin);
      init(user.id.toString());  // 传递 userId，确保用户切换时能重新加载
    } else {
      // 用户登出，清空聊天状态
      const { reset } = useChatStore.getState();
      reset();
    }
  }, [user, loadAll, init]);

  const hasCompanyApi = !!companyConfig?.isActive;
  const hasPersonalApi = !!personalConfig?.isActive;
  const llmReady = hasCompanyApi || hasPersonalApi;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    return () => {
      streamControllerRef.current?.();
    };
  }, []);

  const handleUpload = async (file: File): Promise<void> => {
    try {
      const result: FileUploadResult = await filesApi.upload(file);
      setAttachments((prev) => [
        ...prev,
        { uid: `${Date.now()}`, fileName: result.file_name, url: result.url },
      ]);
    } catch {
      // 错误已由拦截器/调用方处理
    }
  };

  const handleSend = async () => {
    // 只要任一 API（公司/个人）已配置即可发送；所选源未配置时后端会自动降级到另一源
    if (!llmReady) {
      navigate('/settings');
      return;
    }
    if (!input.trim() || sending) return;

    const text = input.trim();
    const sentAttachments = attachments.map((a) => a.url);
    const currentCase = getCurrentCase();

    // 选中模板 → 走文书撰写流程（/draft），生成后弹预览
    if (selectedTemplate) {
      setInput('');
      setAttachments([]);
      setFileList([]);
      setSending(true);
      const now = Date.now();
      appendLocalMessage({
        id: -now,
        conversation_id: currentConversationId ?? 0,
        role: 'user',
        content: text,
        attachments: sentAttachments.map((url) => ({ url })),
        rag_sources: [],
        created_at: new Date().toISOString(),
      });
      appendLocalMessage({
        id: -(now + 1),
        conversation_id: currentConversationId ?? 0,
        role: 'agent',
        content: '正在生成文书草稿...',
        attachments: [],
        rag_sources: [],
        created_at: new Date().toISOString(),
      });
      try {
        const res = await chatApi.startDraft({
          user_input: text,
          case_id: currentCase?.id,
          case_name: currentCase?.name,
          template_id: selectedTemplate.id,
        });
        if (res.error) {
          updateLastAgentMessage(`生成失败：${res.error}`);
        } else if (res.awaiting_review && res.draft) {
          // 弹出预览
          setDraftResult(res);
          setPreviewOpen(true);
          updateLastAgentMessage(
            `已生成《${res.doc_type}》草稿，请在预览窗口确认或微调。`,
          );
        } else if (res.done) {
          updateLastAgentMessage('文书已生成，请下载。');
        }
      } catch (err: unknown) {
        const isTimeout =
          (err as { code?: string; message?: string })?.code === 'ECONNABORTED' ||
          /timeout/i.test((err as { message?: string })?.message || '');
        updateLastAgentMessage(
          isTimeout ? '文书生成超时，请稍后重试' : '生成失败，请稍后重试',
        );
      } finally {
        setSending(false);
      }
      return;
    }

    // 普通对话流程（/stream SSE）
    const now = Date.now();
    const userMsg: ChatMessage = {
      id: -now,
      conversation_id: currentConversationId ?? 0,
      role: 'user',
      content: text,
      attachments: sentAttachments.map((url) => ({ url })),
      rag_sources: [],
      created_at: new Date().toISOString(),
    };
    const agentMsg: ChatMessage = {
      id: -(now + 1),
      conversation_id: currentConversationId ?? 0,
      role: 'agent',
      content: '',
      attachments: [],
      rag_sources: [],
      created_at: new Date().toISOString(),
    };
    appendLocalMessage(userMsg);
    appendLocalMessage(agentMsg);
    setInput('');
    setAttachments([]);
    setFileList([]);
    setSending(true);

    streamBufferRef.current = '';
    streamControllerRef.current = chatApi.streamMessage(
      {
        message: text,
        conversation_id: currentConversationId ?? undefined,
        attachments: sentAttachments,
        case_id: currentCase?.id,
        case_name: currentCase?.name,
        use_rag: useRag,
      },
      {
        onMeta: (meta) => {
          if (meta.rag_sources?.length) {
            updateLastAgentMessage('', meta.rag_sources, meta.conversation_id);
          } else if (meta.conversation_id) {
            updateLastAgentMessage('', undefined, meta.conversation_id);
          }
        },
        onToken: (token) => {
          streamBufferRef.current += token;
          updateLastAgentMessage(streamBufferRef.current);
        },
        onDone: (data) => {
          updateLastAgentMessage(
            streamBufferRef.current || '（无回复）',
            undefined,
            data.conversation_id,
          );
          setSending(false);
        },
        onError: (error) => {
          updateLastAgentMessage(error);
          setSending(false);
        },
      },
    );
  };

  const placeholder = !llmReady
    ? '暂未添加模型api，请在设置中添加～'
    : selectedTemplate
      ? `已选「${selectedTemplate.name}」模板，请描述文书要求（如：诉讼请求、事实理由）`
      : '输入法律问题，或在下方选择模板生成文书（如：帮我写一份上诉状）';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 消息流 */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 24px',
          background: colors.background,
        }}
      >
        {loading && messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin />
          </div>
        ) : messages.length === 0 ? (
          <div
            style={{
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <span style={{ color: colors.muted, fontSize: 13 }}>
                  {llmReady ? '开始与法律助手对话' : '暂未添加模型 API，无法开始对话'}
                </span>
              }
            >
              {!llmReady && (
                <Button type="primary" size="small" onClick={() => navigate('/settings')}>
                  前往设置添加 API
                </Button>
              )}
            </Empty>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              style={{
                display: 'flex',
                gap: 12,
                marginBottom: 16,
                flexDirection: m.role === 'user' ? 'row-reverse' : 'row',
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: m.role === 'user' ? colors.primary : colors.muted,
                  color: '#fff',
                }}
              >
                {m.role === 'agent' ? <RobotOutlined /> : (user?.name?.[0] || 'U')}
              </div>
              <div
                style={{
                  maxWidth: '70%',
                  padding: '10px 14px',
                  borderRadius: 12,
                  background: m.role === 'user' ? colors.primary : colors.panel,
                  color: m.role === 'user' ? '#fff' : colors.text,
                  fontSize: 14,
                  lineHeight: 1.6,
                  whiteSpace: m.role === 'user' ? 'pre-wrap' : 'normal',
                  wordBreak: 'break-word',
                }}
              >
                {m.content ? (
                  m.role === 'agent' ? (
                    <div className="chat-markdown">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ ...props }) => (
                            <h3 style={{ fontSize: 16, margin: '8px 0 4px' }} {...props} />
                          ),
                          h2: ({ ...props }) => (
                            <h4 style={{ fontSize: 15, margin: '8px 0 4px' }} {...props} />
                          ),
                          h3: ({ ...props }) => (
                            <h5 style={{ fontSize: 14, margin: '6px 0 4px' }} {...props} />
                          ),
                          p: ({ ...props }) => (
                            <p style={{ margin: '4px 0' }} {...props} />
                          ),
                          ul: ({ ...props }) => (
                            <ul style={{ paddingLeft: 20, margin: '4px 0' }} {...props} />
                          ),
                          ol: ({ ...props }) => (
                            <ol style={{ paddingLeft: 20, margin: '4px 0' }} {...props} />
                          ),
                          li: ({ ...props }) => (
                            <li style={{ margin: '2px 0' }} {...props} />
                          ),
                          table: ({ ...props }) => (
                            <table
                              style={{
                                borderCollapse: 'collapse',
                                width: '100%',
                                margin: '8px 0',
                                fontSize: 13,
                              }}
                              {...props}
                            />
                          ),
                          th: ({ ...props }) => (
                            <th
                              style={{
                                border: `1px solid ${colors.border}`,
                                padding: '4px 8px',
                                background: colors.background,
                                textAlign: 'left',
                              }}
                              {...props}
                            />
                          ),
                          td: ({ ...props }) => (
                            <td
                              style={{
                                border: `1px solid ${colors.border}`,
                                padding: '4px 8px',
                              }}
                              {...props}
                            />
                          ),
                          a: ({ ...props }) => (
                            <a
                              style={{ color: colors.primary }}
                              target="_blank"
                              rel="noopener noreferrer"
                              {...props}
                            />
                          ),
                          strong: ({ ...props }) => (
                            <strong style={{ fontWeight: 600 }} {...props} />
                          ),
                        }}
                      >
                        {m.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    m.content
                  )
                ) : m.role === 'agent' ? (
                  <Spin size="small" />
                ) : null}
                {/* 用户附件 */}
                {m.attachments && m.attachments.length > 0 && (
                  <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {m.attachments.map((a, i) => (
                      <Tag
                        key={i}
                        icon={<LinkOutlined />}
                        style={{
                          background: 'rgba(255,255,255,.2)',
                          border: 'none',
                          color: '#fff',
                        }}
                      >
                        {a.url.split('/').pop() || a.url}
                      </Tag>
                    ))}
                  </div>
                )}
                {/* RAG 引用来源（可点击查看详情） */}
                {m.rag_sources && m.rag_sources.length > 0 && (
                  <div
                    style={{
                      marginTop: 8,
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 6,
                      fontSize: 12,
                    }}
                  >
                    <span style={{ color: colors.muted }}>参考来源：</span>
                    {m.rag_sources.map((c, i) => (
                      <Tag
                        key={i}
                        icon={<LinkOutlined />}
                        style={{
                          cursor: 'pointer',
                          margin: 0,
                          background: m.role === 'user' ? 'rgba(255,255,255,.2)' : undefined,
                          border: 'none',
                          color: m.role === 'user' ? '#fff' : colors.primary,
                        }}
                        onClick={() => setCitationModal(c)}
                      >
                        [{c.index}] {c.title}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* 附件预览条 */}
      {attachments.length > 0 && (
        <div
          style={{
            padding: '8px 24px',
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            background: colors.panel,
            borderBottom: `1px solid ${colors.border}`,
          }}
        >
          {attachments.map((a) => (
            <Tag
              key={a.uid}
              closable
              icon={<LinkOutlined />}
              onClose={() =>
                setAttachments((list) => list.filter((x) => x.uid !== a.uid))
              }
            >
              {a.fileName}
            </Tag>
          ))}
        </div>
      )}

      {/* 输入区 */}
      <div
        style={{
          borderTop: `1px solid ${colors.border}`,
          padding: '12px 24px 16px',
          background: colors.panel,
        }}
      >
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <Tooltip title={useRag ? '知识库检索已开启：回答将引用参考资料' : '知识库检索已关闭：直接让模型回答'}>
            <Button
              icon={<BookOutlined />}
              type={useRag ? 'primary' : 'default'}
              onClick={() => setUseRag((v) => !v)}
              style={{ flexShrink: 0 }}
            />
          </Tooltip>
          <Tooltip title={llmReady ? '添加附件' : '请先配置模型 API'}>
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
                icon={<PaperClipOutlined />}
                disabled={!llmReady}
                style={{ flexShrink: 0 }}
              />
            </Upload>
          </Tooltip>
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={placeholder}
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            style={{ flex: 1, resize: 'none' }}
            onFocus={() => {
              if (!llmReady) navigate('/settings');
            }}
          />
          <Button
            type="primary"
            icon={selectedTemplate ? <FileTextOutlined /> : <SendOutlined />}
            onClick={handleSend}
            disabled={!llmReady || !input.trim() || sending}
            loading={sending}
            style={{ flexShrink: 0 }}
          >
            {selectedTemplate ? '生成文书' : '发送'}
          </Button>
        </div>
        {!llmReady && (
          <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
            未配置模型 API，点击输入框或
            <Typography.Link onClick={() => navigate('/settings')} style={{ fontSize: 11 }}>
              前往设置
            </Typography.Link>
            添加
          </Typography.Text>
        )}
      </div>

      {/* 模板库条（公共/私有模板选择） */}
      <TemplateBar
        selectedId={selectedTemplate?.id ?? null}
        onSelect={setSelectedTemplate}
      />

      {/* 文书预览弹窗（确认生成 / 微调重写） */}
      <DocPreviewModal
        open={previewOpen}
        result={draftResult}
        onClose={() => {
          setPreviewOpen(false);
          setDraftResult(null);
        }}
        onFinalized={(fileUrl, pdfUrl, docType) => {
          // 定稿完成：更新最后一条 agent 消息为下载链接
          updateLastAgentMessage(
            `《${docType}》已生成，请下载：\n[Word] ${fileUrl}\n[PDF] ${pdfUrl}`,
          );
        }}
      />

      {/* 参考资料引用详情弹窗 */}
      <Modal
        title={
          citationModal ? (
            <span>
              参考资料 [{citationModal.index}] — {citationModal.title}
            </span>
          ) : (
            '参考资料'
          )
        }
        open={!!citationModal}
        onCancel={() => setCitationModal(null)}
        footer={null}
        width={600}
      >
        {citationModal && (
          <div>
            {citationModal.source && (
              <Tag color="blue" style={{ marginBottom: 8 }}>
                来源：{citationModal.source}
              </Tag>
            )}
            <Typography.Paragraph
              style={{
                whiteSpace: 'pre-wrap',
                maxHeight: 400,
                overflowY: 'auto',
                color: colors.text,
              }}
            >
              {citationModal.content || '（暂无内容）'}
            </Typography.Paragraph>
          </div>
        )}
      </Modal>
    </div>
  );
}
