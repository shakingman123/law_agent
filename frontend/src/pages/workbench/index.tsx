import { Layout, Tag, Typography, Button, Tooltip } from 'antd';
import { CloseOutlined, FolderOutlined } from '@ant-design/icons';
import { colors } from '../../theme/tokens';
import ChatBox from '../../components/chat/ChatBox';
import CasePanel from '../../components/cases/CasePanel';
import { useCaseStore } from '../../stores/caseStore';

const { Content, Sider } = Layout;

/**
 * 工作台主页
 * 依据 figma-design-spec.md §3：中央对话框(自适应) + 右侧案件栏(288)
 * 对话窗口由 ChatBox 实现，案件栏由 CasePanel 实现（含新建案件）。
 *
 * 案件状态栏：选中案件后在对话框上方显示当前案件上下文，
 * 对话时自动携带 case_id/case_name，LLM 可从案件信息中提取上下文。
 */
export default function Workbench() {
  const { currentCaseId, selectCase, getCurrentCase } = useCaseStore();
  const currentCase = getCurrentCase();

  return (
    <Layout style={{ height: '100%' }}>
      <Content
        style={{
          padding: 16,
          background: colors.background,
          height: '100vh',
        }}
      >
        <div
          style={{
            background: colors.panel,
            borderRadius: 12,
            height: 'calc(100% - 8px)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* 案件状态栏 */}
          {currentCase && currentCaseId !== null && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 16px',
                background: colors.primaryBg,
                borderBottom: `1px solid ${colors.border}`,
                fontSize: 13,
              }}
            >
              <FolderOutlined style={{ color: colors.primary, flexShrink: 0 }} />
              <Typography.Text style={{ color: colors.primary, fontWeight: 600 }}>
                当前案件：{currentCase.name}
              </Typography.Text>
              <Tag style={{ margin: 0, fontSize: 11 }}>
                {currentCase.plaintiff} 诉 {currentCase.defendant}
              </Tag>
              {currentCase.court && (
                <Typography.Text style={{ fontSize: 12, color: colors.muted }}>
                  {currentCase.court}
                </Typography.Text>
              )}
              <div style={{ flex: 1 }} />
              <Tooltip title="退出案件上下文">
                <Button
                  type="text"
                  size="small"
                  icon={<CloseOutlined />}
                  style={{ color: colors.muted, flexShrink: 0 }}
                  onClick={() => selectCase(null)}
                />
              </Tooltip>
            </div>
          )}
          <ChatBox />
        </div>
      </Content>
      <Sider
        width={288}
        theme="light"
        style={{
          background: colors.panel,
          borderLeft: `1px solid ${colors.border}`,
          height: '100vh',
        }}
      >
        <CasePanel />
      </Sider>
    </Layout>
  );
}
