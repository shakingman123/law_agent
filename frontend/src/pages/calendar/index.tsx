import { useState } from 'react';
import {
  Card,
  Calendar as AntCalendar,
  Segmented,
  Button,
  List,
  Tag,
  Switch,
  Typography,
  Space,
  Modal,
  Form,
  Input,
  DatePicker,
  Select,
  App,
} from 'antd';
import { PlusOutlined, BellOutlined } from '@ant-design/icons';
import { colors } from '../../theme/tokens';

type ViewMode = '日' | '周' | '月';

interface ScheduleItem {
  id: string;
  title: string;
  date: string;
  level: 'urgent' | 'normal' | 'meeting';
  caseName?: string;
}

// Mock 数据
const mockSchedules: ScheduleItem[] = [
  {
    id: '1',
    title: '张某案 上诉期截止',
    date: '2026-08-22',
    level: 'urgent',
    caseName: '张某诉李某合同纠纷',
  },
  {
    id: '2',
    title: '王某案 举证期限',
    date: '2026-08-25',
    level: 'urgent',
    caseName: '王某离婚案',
  },
  {
    id: '3',
    title: '赵某案 答辩期',
    date: '2026-08-26',
    level: 'normal',
    caseName: '赵某交通事故案',
  },
  {
    id: '4',
    title: '团队周会',
    date: '2026-08-21',
    level: 'meeting',
  },
];

const levelConfig = {
  urgent: { color: colors.danger, label: '紧急' },
  normal: { color: colors.amber, label: '一般' },
  meeting: { color: colors.primary, label: '会议' },
};

/**
 * 日程列表页
 * 依据 figma-design-spec.md §4：日/周/月切换 + 待办列表 + 通知渠道开关
 * 事件卡按紧急度着色：红=举证期/上诉期、琥珀=一般期限、蓝=会议
 */
export default function CalendarPage() {
  const [view, setView] = useState<ViewMode>('月');
  const [modalOpen, setModalOpen] = useState(false);
  const [notifyChannels, setNotifyChannels] = useState({
    feishu: true,
    wechat: true,
    dingtalk: false,
  });
  const [form] = Form.useForm();
  const { message } = App.useApp();

  const handleCreate = () => {
    form.validateFields().then(() => {
      message.success('日程已创建');
      setModalOpen(false);
      form.resetFields();
    });
  };

  return (
    <div style={{ padding: 24, height: '100%', overflow: 'auto' }}>
      <Card
        title={
          <Space>
            <Typography.Title level={4} style={{ margin: 0 }}>
              日程列表
            </Typography.Title>
          </Space>
        }
        extra={
          <Space>
            <Segmented<ViewMode>
              value={view}
              onChange={(v) => setView(v)}
              options={['日', '周', '月']}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
              新建日程
            </Button>
          </Space>
        }
        styles={{ body: { padding: 16 } }}
      >
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <AntCalendar
              fullscreen={view === '月'}
              mode={view === '日' ? 'month' : (view.toLowerCase() as 'month' | 'year')}
              cellRender={(date) => {
                const dateStr = date.format('YYYY-MM-DD');
                const items = mockSchedules.filter((s) => s.date === dateStr);
                if (items.length === 0) return null;
                return (
                  <div style={{ padding: '2px 4px' }}>
                    {items.map((item) => (
                      <div
                        key={item.id}
                        style={{
                          fontSize: 11,
                          padding: '1px 4px',
                          marginBottom: 2,
                          borderRadius: 4,
                          background: levelConfig[item.level].color + '20',
                          color: levelConfig[item.level].color,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {item.title}
                      </div>
                    ))}
                  </div>
                );
              }}
            />
          </div>

          <div style={{ width: 320 }}>
            <Card
              size="small"
              title={<span><BellOutlined style={{ marginRight: 6 }} />待办提醒</span>}
              style={{ marginBottom: 16 }}
            >
              <List
                size="small"
                dataSource={mockSchedules}
                renderItem={(item) => (
                  <List.Item>
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography.Text strong>{item.title}</Typography.Text>
                        <Tag color={levelConfig[item.level].color}>
                          {levelConfig[item.level].label}
                        </Tag>
                      </div>
                      <div style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>
                        <div>{item.date}</div>
                        {item.caseName && <div>案件：{item.caseName}</div>}
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            </Card>

            <Card size="small" title="通知渠道">
              <Space direction="vertical" style={{ width: '100%' }}>
                <ChannelRow
                  label="飞书"
                  checked={notifyChannels.feishu}
                  onChange={(v) => setNotifyChannels((s) => ({ ...s, feishu: v }))}
                />
                <ChannelRow
                  label="微信"
                  checked={notifyChannels.wechat}
                  onChange={(v) => setNotifyChannels((s) => ({ ...s, wechat: v }))}
                />
                <ChannelRow
                  label="钉钉"
                  checked={notifyChannels.dingtalk}
                  onChange={(v) => setNotifyChannels((s) => ({ ...s, dingtalk: v }))}
                />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  紧急事项提前1天，一般事项提前5天
                </Typography.Text>
              </Space>
            </Card>
          </div>
        </div>
      </Card>

      <Modal
        title="新建日程"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="日程标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="如：XX案 上诉期截止" />
          </Form.Item>
          <Form.Item name="date" label="截止日期" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="level" label="紧急程度" rules={[{ required: true, message: '请选择' }]}>
            <Select
              placeholder="请选择"
              options={[
                { value: 'urgent', label: '紧急（提前1天）' },
                { value: 'normal', label: '一般（提前5天）' },
                { value: 'meeting', label: '会议' },
              ]}
            />
          </Form.Item>
          <Form.Item name="caseName" label="关联案件">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function ChannelRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Typography.Text>{label}</Typography.Text>
      <Switch checked={checked} onChange={onChange} />
    </div>
  );
}
