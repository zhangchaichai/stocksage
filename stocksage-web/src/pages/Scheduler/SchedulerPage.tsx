import React, { useEffect, useState } from 'react';
import {
  Typography, Table, Button, Space, Tag, Switch, Modal, Form,
  Input, Select, Popconfirm, message, Card, Row, Col, Statistic,
  InputNumber, Slider, Checkbox, DatePicker, Spin, Divider,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, PlayCircleOutlined,
  ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { schedulerApi, screenerApi, workflowApi } from '../../api/endpoints';
import { useI18n } from '../../i18n';
import type { ScheduledTask, StrategyListItem, Workflow } from '../../types';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

// ── Constants ─────────────────────────────────────────────────────────────────

const TASK_TYPE_OPTIONS = [
  { value: 'screener', labelKey: 'screener' },
  { value: 'workflow_run', labelKey: 'workflowRun' },
  { value: 'workflow_backtest', labelKey: 'workflowBacktest' },
  { value: 'screener_backtest', labelKey: 'screenerBacktest' },
  { value: 'memory_forgetting', labelKey: 'memoryForgetting' },
] as const;

const TASK_TYPE_COLORS: Record<string, string> = {
  screener: 'blue',
  workflow_run: 'green',
  workflow_backtest: 'orange',
  screener_backtest: 'purple',
  memory_forgetting: 'default',
};

const POOL_OPTIONS = [
  { value: 'hs300', label: '沪深300' },
  { value: 'zz500', label: '中证500' },
  { value: 'zz1000', label: '中证1000' },
  { value: 'kc50', label: '科创50' },
  { value: 'cyb', label: '创业板' },
  { value: 'main_sh', label: '沪市主板' },
  { value: 'main_sz', label: '深市主板' },
  { value: 'all_a', label: 'A股全市场' },
];

const MARKET_FILTER_OPTIONS = [
  { value: 'sh_main', label: '沪市主板' },
  { value: 'sz_main', label: '深市主板' },
  { value: 'cyb', label: '创业板' },
  { value: 'kcb', label: '科创板' },
  { value: 'bj', label: '北交所' },
];

// ── Component ─────────────────────────────────────────────────────────────────

const SchedulerPage: React.FC = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [form] = Form.useForm();
  const taskType = Form.useWatch('task_type', form);

  // ── Fetched reference data ──────────────────────────────────────────────

  const [strategies, setStrategies] = useState<StrategyListItem[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);

  // Fetch strategies when task type is screener or screener_backtest
  useEffect(() => {
    if (taskType === 'screener' || taskType === 'screener_backtest') {
      setLoadingStrategies(true);
      screenerApi.listStrategies()
        .then(res => setStrategies(res.data))
        .catch(() => {})
        .finally(() => setLoadingStrategies(false));
    }
  }, [taskType]);

  // Fetch workflows when task type is workflow_run or workflow_backtest
  useEffect(() => {
    if (taskType === 'workflow_run' || taskType === 'workflow_backtest') {
      setLoadingWorkflows(true);
      workflowApi.list(0, 200)
        .then(res => setWorkflows(res.data.items))
        .catch(() => {})
        .finally(() => setLoadingWorkflows(false));
    }
  }, [taskType]);

  // ── Queries & Mutations ─────────────────────────────────────────────────

  const { data: tasks, isLoading } = useQuery({
    queryKey: ['scheduler', 'tasks'],
    queryFn: () => schedulerApi.list().then(r => r.data),
  });

  const createMutation = useMutation({
    mutationFn: schedulerApi.create,
    onSuccess: () => {
      message.success(t.scheduler.created);
      queryClient.invalidateQueries({ queryKey: ['scheduler'] });
      setModalOpen(false);
      form.resetFields();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || 'Failed'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) =>
      schedulerApi.update(id, data),
    onSuccess: () => {
      message.success(t.scheduler.updated);
      queryClient.invalidateQueries({ queryKey: ['scheduler'] });
      setModalOpen(false);
      setEditingTask(null);
      form.resetFields();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || 'Failed'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => schedulerApi.delete(id),
    onSuccess: () => {
      message.success(t.scheduler.deleted);
      queryClient.invalidateQueries({ queryKey: ['scheduler'] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      schedulerApi.update(id, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduler'] });
    },
  });

  const triggerMutation = useMutation({
    mutationFn: (id: string) => schedulerApi.trigger(id),
    onSuccess: () => {
      message.success(t.scheduler.triggered);
      queryClient.invalidateQueries({ queryKey: ['scheduler'] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || 'Failed'),
  });

  // ── Modal helpers ───────────────────────────────────────────────────────

  const openCreate = () => {
    setEditingTask(null);
    form.resetFields();
    form.setFieldsValue({
      timezone: 'Asia/Shanghai',
      enabled: true,
      // screener defaults
      top_n: 20,
      enable_ai_score: false,
      pool: 'hs300',
      // backtest defaults
      period_days: 30,
      // memory defaults
      max_anchor_age_days: 365,
    });
    setModalOpen(true);
  };

  const openEdit = (task: ScheduledTask) => {
    setEditingTask(task);
    const cfg = task.config || {};
    const base: Record<string, unknown> = {
      name: task.name,
      task_type: task.task_type,
      cron_expr: task.cron_expr,
      timezone: task.timezone,
      enabled: task.enabled,
    };

    // Unpack config into individual form fields based on task type
    if (task.task_type === 'screener') {
      base.strategy_id = cfg.strategy_id;
      base.pool = cfg.pool || 'hs300';
      base.top_n = cfg.top_n ?? 20;
      base.enable_ai_score = cfg.enable_ai_score ?? false;
      base.market_filters = cfg.market_filters;
      if (cfg.date_from && cfg.date_to) {
        base.date_range = [dayjs(cfg.date_from as string), dayjs(cfg.date_to as string)];
      }
    } else if (task.task_type === 'workflow_run') {
      base.workflow_id = cfg.workflow_id;
      base.symbol = cfg.symbol;
      base.stock_name = cfg.stock_name;
    } else if (task.task_type === 'workflow_backtest') {
      base.period_days = cfg.period_days ?? 30;
      base.symbol = cfg.symbol;
    } else if (task.task_type === 'screener_backtest') {
      base.strategy_id = cfg.strategy_id;
      base.period_days = cfg.period_days ?? 30;
    } else if (task.task_type === 'memory_forgetting') {
      base.max_anchor_age_days = cfg.max_anchor_age_days ?? 365;
    }

    form.setFieldsValue(base);
    setModalOpen(true);
  };

  /** Pack individual form fields into a config JSON object */
  const buildConfig = (values: any): Record<string, unknown> => {
    const tt = values.task_type;
    const config: Record<string, unknown> = {};

    if (tt === 'screener') {
      if (values.strategy_id) config.strategy_id = values.strategy_id;
      config.pool = values.pool || 'hs300';
      config.top_n = values.top_n ?? 20;
      config.enable_ai_score = values.enable_ai_score ?? false;
      if (values.date_range?.[0] && values.date_range?.[1]) {
        config.date_from = values.date_range[0].format('YYYY-MM-DD');
        config.date_to = values.date_range[1].format('YYYY-MM-DD');
      }
      if (values.market_filters?.length > 0) {
        config.market_filters = values.market_filters;
      }
    } else if (tt === 'workflow_run') {
      config.workflow_id = values.workflow_id;
      config.symbol = values.symbol;
      if (values.stock_name) config.stock_name = values.stock_name;
    } else if (tt === 'workflow_backtest') {
      config.period_days = values.period_days ?? 30;
      if (values.symbol) config.symbol = values.symbol;
    } else if (tt === 'screener_backtest') {
      if (values.strategy_id) config.strategy_id = values.strategy_id;
      config.period_days = values.period_days ?? 30;
    } else if (tt === 'memory_forgetting') {
      config.max_anchor_age_days = values.max_anchor_age_days ?? 365;
    }

    return config;
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const config = buildConfig(values);

    const payload = {
      name: values.name,
      task_type: values.task_type,
      cron_expr: values.cron_expr,
      timezone: values.timezone,
      enabled: values.enabled,
      config,
    };

    if (editingTask) {
      updateMutation.mutate({ id: editingTask.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const taskTypeLabel = (tt: string) => {
    const s = t.scheduler as any;
    const map: Record<string, string> = {
      screener: s.screener,
      workflow_run: s.workflowRun,
      workflow_backtest: s.workflowBacktest,
      screener_backtest: s.screenerBacktest,
      memory_forgetting: s.memoryForgetting,
    };
    return map[tt] || tt;
  };

  // ── Stats ───────────────────────────────────────────────────────────────

  const totalTasks = tasks?.length || 0;
  const enabledTasks = tasks?.filter(t => t.enabled).length || 0;
  const failedTasks = tasks?.filter(t => t.last_run_status === 'failed').length || 0;

  // ── Dynamic config form per task type ───────────────────────────────────

  const renderConfigFields = () => {
    if (!taskType) return null;

    switch (taskType) {
      case 'screener':
        return (
          <>
            <Divider orientation="left" style={{ marginTop: 8, marginBottom: 16, fontSize: 13 }}>
              {t.scheduler.config}
            </Divider>
            <Form.Item name="strategy_id" label={t.scheduler.selectStrategy}>
              {loadingStrategies ? (
                <Spin size="small" />
              ) : (
                <Select
                  placeholder={t.scheduler.selectStrategy}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={strategies.map(s => ({
                    value: s.id,
                    label: `${s.name}${s.description ? ` — ${s.description}` : ''}`,
                  }))}
                  notFoundContent={t.scheduler.noStrategies}
                />
              )}
            </Form.Item>
            <Form.Item name="pool" label={t.scheduler.pool}>
              <Select options={POOL_OPTIONS} />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="top_n" label={t.scheduler.topN}>
                  <Slider min={5} max={50} step={5} marks={{ 5: '5', 10: '10', 20: '20', 30: '30', 50: '50' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="enable_ai_score" valuePropName="checked" label=" ">
                  <Checkbox>{t.scheduler.enableAiScore}</Checkbox>
                </Form.Item>
                <Text type="secondary" style={{ fontSize: 12, marginTop: -12, display: 'block' }}>
                  {t.scheduler.enableAiScoreDesc}
                </Text>
              </Col>
            </Row>
            <Form.Item name="date_range" label={t.scheduler.dateRange}>
              <RangePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="market_filters" label={t.scheduler.marketFilters}>
              <Select
                mode="multiple"
                allowClear
                options={MARKET_FILTER_OPTIONS}
                placeholder={t.scheduler.marketFilters}
              />
            </Form.Item>
          </>
        );

      case 'workflow_run':
        return (
          <>
            <Divider orientation="left" style={{ marginTop: 8, marginBottom: 16, fontSize: 13 }}>
              {t.scheduler.config}
            </Divider>
            <Form.Item
              name="workflow_id"
              label={t.scheduler.selectWorkflow}
              rules={[{ required: true }]}
            >
              {loadingWorkflows ? (
                <Spin size="small" />
              ) : (
                <Select
                  placeholder={t.scheduler.selectWorkflow}
                  showSearch
                  optionFilterProp="label"
                  options={workflows.map(w => ({
                    value: w.id,
                    label: w.name + (w.description ? ` — ${w.description}` : ''),
                  }))}
                />
              )}
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name="symbol"
                  label={t.scheduler.stockSymbol}
                  rules={[{ required: true }]}
                >
                  <Input placeholder={t.scheduler.symbolPlaceholder} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="stock_name" label={t.scheduler.stockName}>
                  <Input placeholder={t.scheduler.stockNamePlaceholder} />
                </Form.Item>
              </Col>
            </Row>
          </>
        );

      case 'workflow_backtest':
        return (
          <>
            <Divider orientation="left" style={{ marginTop: 8, marginBottom: 16, fontSize: 13 }}>
              {t.scheduler.config}
            </Divider>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="period_days" label={t.scheduler.periodDays}>
                  <InputNumber min={1} max={365} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="symbol" label={t.scheduler.stockSymbol}>
                  <Input placeholder={t.scheduler.symbolPlaceholder} allowClear />
                </Form.Item>
              </Col>
            </Row>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {taskType === 'workflow_backtest' && !form.getFieldValue('symbol')
                ? '不填写股票代码则回测所有已有操作记录'
                : ''}
            </Text>
          </>
        );

      case 'screener_backtest':
        return (
          <>
            <Divider orientation="left" style={{ marginTop: 8, marginBottom: 16, fontSize: 13 }}>
              {t.scheduler.config}
            </Divider>
            <Form.Item name="strategy_id" label={t.scheduler.selectStrategy}>
              {loadingStrategies ? (
                <Spin size="small" />
              ) : (
                <Select
                  placeholder={t.scheduler.selectStrategy}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={strategies.map(s => ({
                    value: s.id,
                    label: `${s.name}${s.description ? ` — ${s.description}` : ''}`,
                  }))}
                  notFoundContent={t.scheduler.noStrategies}
                />
              )}
            </Form.Item>
            <Form.Item name="period_days" label={t.scheduler.periodDays}>
              <InputNumber min={1} max={365} style={{ width: '100%' }} />
            </Form.Item>
          </>
        );

      case 'memory_forgetting':
        return (
          <>
            <Divider orientation="left" style={{ marginTop: 8, marginBottom: 16, fontSize: 13 }}>
              {t.scheduler.config}
            </Divider>
            <Form.Item name="max_anchor_age_days" label={t.scheduler.maxAnchorAgeDays}>
              <InputNumber min={30} max={3650} style={{ width: '100%' }} />
            </Form.Item>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t.scheduler.maxAnchorAgeDaysDesc}
            </Text>
          </>
        );

      default:
        return null;
    }
  };

  // ── Table columns ───────────────────────────────────────────────────────

  const columns = [
    {
      title: t.scheduler.name,
      dataIndex: 'name',
      key: 'name',
      width: 180,
      ellipsis: true,
    },
    {
      title: t.scheduler.taskType,
      dataIndex: 'task_type',
      key: 'task_type',
      width: 120,
      render: (tt: string) => (
        <Tag color={TASK_TYPE_COLORS[tt] || 'default'}>{taskTypeLabel(tt)}</Tag>
      ),
    },
    {
      title: t.scheduler.cronExpr,
      dataIndex: 'cron_expr',
      key: 'cron_expr',
      width: 140,
      render: (v: string) => <code>{v}</code>,
    },
    {
      title: t.scheduler.enabled,
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: ScheduledTask) => (
        <Switch
          checked={enabled}
          size="small"
          onChange={(checked) => toggleMutation.mutate({ id: record.id, enabled: checked })}
        />
      ),
    },
    {
      title: t.scheduler.lastRun,
      dataIndex: 'last_run_at',
      key: 'last_run_at',
      width: 160,
      render: (v: string | null) =>
        v ? new Date(v).toLocaleString() : <span style={{ color: '#999' }}>{t.scheduler.never}</span>,
    },
    {
      title: t.scheduler.lastStatus,
      dataIndex: 'last_run_status',
      key: 'last_run_status',
      width: 100,
      render: (v: string | null) => {
        if (!v) return '-';
        return v === 'completed'
          ? <Tag icon={<CheckCircleOutlined />} color="success">{t.scheduler.completed}</Tag>
          : <Tag icon={<CloseCircleOutlined />} color="error">{t.scheduler.failed}</Tag>;
      },
    },
    {
      title: t.scheduler.runCount,
      dataIndex: 'run_count',
      key: 'run_count',
      width: 80,
      align: 'center' as const,
    },
    {
      title: t.common.actions,
      key: 'actions',
      width: 200,
      render: (_: unknown, record: ScheduledTask) => (
        <Space size="small">
          <Button size="small" onClick={() => openEdit(record)}>
            {t.common.edit}
          </Button>
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => triggerMutation.mutate(record.id)}
            loading={triggerMutation.isPending}
          >
            {t.scheduler.triggerNow}
          </Button>
          <Popconfirm
            title={t.scheduler.deleteConfirm}
            onConfirm={() => deleteMutation.mutate(record.id)}
            okText={t.common.yes}
            cancelText={t.common.no}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t.scheduler.title}</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          {t.scheduler.createTask}
        </Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title={t.common.total}
              value={totalTasks}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title={t.scheduler.enabled}
              value={enabledTasks}
              valueStyle={{ color: '#3f8600' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title={t.scheduler.failed}
              value={failedTasks}
              valueStyle={{ color: failedTasks > 0 ? '#cf1322' : undefined }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Table
        dataSource={tasks || []}
        columns={columns}
        loading={isLoading}
        rowKey="id"
        pagination={{ pageSize: 20, showSizeChanger: false }}
        scroll={{ x: 1100 }}
      />

      <Modal
        title={editingTask ? t.scheduler.editTask : t.scheduler.createTask}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditingTask(null); }}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        width={680}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          {/* ── Basic fields ─────────────────────────────────────────── */}
          <Form.Item
            name="name"
            label={t.scheduler.name}
            rules={[{ required: true, message: t.scheduler.namePlaceholder }]}
          >
            <Input placeholder={t.scheduler.namePlaceholder} />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="task_type"
                label={t.scheduler.taskType}
                rules={[{ required: true }]}
              >
                <Select
                  options={TASK_TYPE_OPTIONS.map(o => ({
                    value: o.value,
                    label: taskTypeLabel(o.value),
                  }))}
                  disabled={!!editingTask}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="cron_expr"
                label={t.scheduler.cronExpr}
                rules={[{ required: true }]}
                extra={t.scheduler.cronHelp}
              >
                <Input placeholder="0 9 * * 1-5" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="timezone" label={t.scheduler.timezone}>
                <Select
                  options={[
                    { value: 'Asia/Shanghai', label: 'Asia/Shanghai' },
                    { value: 'Asia/Hong_Kong', label: 'Asia/Hong_Kong' },
                    { value: 'US/Eastern', label: 'US/Eastern' },
                    { value: 'UTC', label: 'UTC' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="enabled" label={t.scheduler.enabled} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>

          {/* ── Dynamic config fields based on task_type ─────────── */}
          {renderConfigFields()}
        </Form>
      </Modal>
    </div>
  );
};

export default SchedulerPage;
