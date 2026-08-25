import { useEffect, useState } from 'react';
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
  InputNumber,
  Popconfirm,
  Spin,
  App,
} from 'antd';
import { PlusOutlined, BellOutlined, DeleteOutlined } from '@ant-design/icons';
import { colors } from '../../theme/tokens';
import { schedulesApi, type ScheduleItem, type ScheduleLevel } from '../../api/schedules';

type ViewMode = '日' | '周' | '月';

const levelConfig: Record<
  ScheduleLevel,
  { color: string; label: string }
> = {
  urgent: { color: colors.danger, label: '紧急' },
  normal: { color: colors.amber, label: '一般' },
  meeting: { color: colors.primary, label: '会议' },
};

/**
 * 日程列表页
 * 依据 figma-design-spec.md §4：日/周/月切换 + 待办列表 + 通知渠道开关
 * 事件卡按紧急度着色：红=举证期/上诉期、琥珀=一般期限、蓝=会议
 * 数据通过 /api/schedules 持久化，按当前用户隔离
 */
export default function CalendarPage() {
  const [view, setView] = useState<ViewMode>('月');
  const [modalOpen, setModalOpen] = useState(false);
  const [notifyChannels, setNotifyChannels] = useState({
    feishu: true,
    wechat: true,
    dingtalk: false,
  });
  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const { message } = App.useApp();
  // 监听提醒预设选择，决定是否展示自定义天数输入框
  const remindPreset = Form.useWatch('remindPreset', form);

  const loadSchedules = async () => {
    setLoading(true);
    try {
      const list = await schedulesApi.list();
      setSchedules(list);
    } catch {
      /* 错误已由 request 拦截器提示 */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSchedules();
  }, []);

  const handleCreate = async () => {
    try {
      const v = await form.validateFields();
      setSubmitting(true);
      // 由提醒预设推导 remind_advance：custom 用自定义天数，其余用预设值
      let remind_advance: number | null;
      if (v.remindPreset === 'custom') {
        remind_advance = v.remindCustomDays ?? null;
      } else {
        remind_advance = Number(v.remindPreset);
      }
      const created = await schedulesApi.create({
        title: v.title,
        date: v.date.format('YYYY-MM-DD'),
        level: v.level,
        remind_advance,
        case_name: v.caseName || undefined,
      });
      setSchedules((prev) =>
        [...prev, created].sort((a, b) => a.date.localeCompare(b.date)),
      );
      message.success('日程已创建');
      setModalOpen(false);
      form.resetFields();
    } catch (e: any) {
      // 校验失败不弹错误；请求失败由拦截器提示
      if (e?.errorFields) return;
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await schedulesApi.remove(id);
      setSchedules((prev) => prev.filter((s) => s.id !== id));
      message.success('日程已删除');
    } catch {
      /* 拦截器已提示 */
    } finally {
      setDeletingId(null);
    }
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
            <Spin spinning={loading}>
              <AntCalendar
                fullscreen={view === '月'}
                mode={view === '日' ? 'month' : (view.toLowerCase() as 'month' | 'year')}
                cellRender={(date) => {
                  const dateStr = date.format('YYYY-MM-DD');
                  const items = schedules.filter((s) => s.date === dateStr);
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
            </Spin>
          </div>

          <div style={{ width: 320 }}>
            <Card
              size="small"
              title={<span><BellOutlined style={{ marginRight: 6 }} />待办提醒</span>}
              style={{ marginBottom: 16 }}
            >
              <List
                size="small"
                loading={loading}
                dataSource={schedules}
                locale={{ emptyText: '暂无日程' }}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Popconfirm
                        key="delete"
                        title="确认删除该日程？"
                        okText="删除"
                        okType="danger"
                        cancelText="取消"
                        onConfirm={() => handleDelete(item.id)}
                      >
                        <Button
                          size="small"
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          loading={deletingId === item.id}
                        />
                      </Popconfirm>,
                    ]}
                  >
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography.Text strong>{item.title}</Typography.Text>
                        <Tag color={levelConfig[item.level].color}>
                          {levelConfig[item.level].label}
                        </Tag>
                      </div>
                      <div style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>
                        <div>
                          {item.date}
                          {item.remind_advance != null && (
                            <span style={{ marginLeft: 8 }}>
                              ·{' '}
                              {item.remind_advance === 0
                                ? '当天提醒'
                                : `提前${item.remind_advance}天提醒`}
                            </span>
                          )}
                        </div>
                        {item.case_name && <div>案件：{item.case_name}</div>}
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
                  提醒时间可在新建日程时选择：当天 / 提前1天 / 提前3天 / 自定义
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
        confirmLoading={submitting}
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
                { value: 'urgent', label: '紧急' },
                { value: 'normal', label: '一般' },
                { value: 'meeting', label: '会议' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="remindPreset"
            label="提醒时间"
            initialValue="1"
            rules={[{ required: true, message: '请选择提醒时间' }]}
          >
            <Select
              options={[
                { value: '0', label: '当天提醒' },
                { value: '1', label: '提前1天' },
                { value: '3', label: '提前3天' },
                { value: 'custom', label: '自定义天数' },
              ]}
            />
          </Form.Item>
          {remindPreset === 'custom' && (
            <Form.Item
              name="remindCustomDays"
              label="提前天数"
              rules={[{ required: true, message: '请输入天数' }]}
            >
              <InputNumber min={0} max={365} addonAfter="天" style={{ width: '100%' }} />
            </Form.Item>
          )}
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
