import React, { useState } from 'react';
import {
  Card,
  Col,
  Row,
  Statistic,
  Table,
  Typography,
  Button,
  Modal,
  Form,
  Select,
  Input,
  InputNumber,
  DatePicker,
  Tag,
  Space,
  Spin,
  Popconfirm,
  Empty,
  message,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { portfolioApi, runApi } from '../../api/endpoints';
import type { InvestmentAction, PortfolioSummary, WorkflowRun } from '../../types';
import { useI18n } from '../../i18n';

const { Title } = Typography;

const actionTypeColors: Record<string, string> = {
  buy: 'green',
  sell: 'red',
  hold: 'blue',
  watch: 'orange',
};

const PortfolioPage: React.FC = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  // ---- Queries ----

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['portfolio-summary'],
    queryFn: () => portfolioApi.getSummary().then((r) => r.data),
  });

  const { data: actions, isLoading: loadingActions } = useQuery({
    queryKey: ['portfolio-actions'],
    queryFn: () => portfolioApi.listActions({ limit: 50 }).then((r) => r.data),
  });

  const { data: runsData } = useQuery({
    queryKey: ['runs', 'list'],
    queryFn: () => runApi.list(0, 100).then((r) => r.data),
  });

  // ---- Mutations ----

  const deleteMutation = useMutation({
    mutationFn: (id: string) => portfolioApi.deleteAction(id),
    onSuccess: () => {
      message.success(t.portfolio.actionDeleted);
      queryClient.invalidateQueries({ queryKey: ['portfolio-actions'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio-summary'] });
    },
  });

  const createMutation = useMutation({
    mutationFn: (values: any) =>
      portfolioApi.recordAction({
        ...values,
        action_date: values.action_date.format('YYYY-MM-DD'),
      }),
    onSuccess: () => {
      message.success(t.portfolio.actionCreated);
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['portfolio-actions'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio-summary'] });
    },
  });

  // ---- Holdings Table Columns ----

  const holdingsColumns = [
    {
      title: t.portfolio.symbol,
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t.portfolio.stockName,
      dataIndex: 'stock_name',
      key: 'stock_name',
    },
    {
      title: t.portfolio.quantity,
      dataIndex: 'quantity',
      key: 'quantity',
    },
    {
      title: t.portfolio.avgCost,
      dataIndex: 'avg_cost',
      key: 'avg_cost',
      render: (val: number) => `¥${val.toFixed(2)}`,
    },
  ];

  // ---- Actions Table Columns ----

  const actionsColumns = [
    {
      title: t.portfolio.actionDate,
      dataIndex: 'action_date',
      key: 'action_date',
    },
    {
      title: t.portfolio.symbol,
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t.portfolio.stockName,
      dataIndex: 'stock_name',
      key: 'stock_name',
    },
    {
      title: t.portfolio.actionType,
      dataIndex: 'action_type',
      key: 'action_type',
      render: (type: InvestmentAction['action_type']) => (
        <Tag color={actionTypeColors[type]}>
          {t.portfolio[type]}
        </Tag>
      ),
    },
    {
      title: t.portfolio.price,
      dataIndex: 'price',
      key: 'price',
      render: (val: number) => `¥${val.toFixed(2)}`,
    },
    {
      title: t.portfolio.quantity,
      dataIndex: 'quantity',
      key: 'quantity',
      render: (val: number | null) => val ?? '-',
    },
    {
      title: t.portfolio.amount,
      dataIndex: 'amount',
      key: 'amount',
      render: (val: number | null) => (val != null ? `¥${val.toFixed(2)}` : '-'),
    },
    {
      title: t.portfolio.reason,
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true,
      render: (val: string | null) => val ?? '-',
    },
    {
      title: t.common.actions,
      key: 'actions',
      render: (_: unknown, record: InvestmentAction) => (
        <Popconfirm
          title={t.portfolio.deleteConfirm}
          onConfirm={() => deleteMutation.mutate(record.id)}
          okText={t.common.yes}
          cancelText={t.common.no}
        >
          <Button type="link" danger size="small" icon={<DeleteOutlined />}>
            {t.common.delete}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  // ---- Loading State ----

  if (loadingSummary && loadingActions) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      {/* Title Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>{t.portfolio.title}</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          {t.portfolio.recordAction}
        </Button>
      </div>

      {/* Summary Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title={t.portfolio.totalCost}
              value={summary?.total_cost ?? 0}
              prefix="¥"
              precision={2}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title={t.portfolio.holdingCount}
              value={summary?.holding_count ?? 0}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title={t.common.total}
              value={actions?.total ?? 0}
            />
          </Card>
        </Col>
      </Row>

      {/* Holdings Table */}
      <Card title={t.portfolio.holdings} style={{ marginBottom: 24 }}>
        {(summary?.holdings ?? []).length === 0 ? (
          <Empty description={t.portfolio.noHoldings} />
        ) : (
          <Table
            columns={holdingsColumns}
            dataSource={summary?.holdings ?? []}
            rowKey="symbol"
            pagination={false}
            size="small"
          />
        )}
      </Card>

      {/* Recent Actions Table */}
      <Card title={t.portfolio.recentActions}>
        <Table
          columns={actionsColumns}
          dataSource={actions?.items ?? []}
          rowKey="id"
          loading={loadingActions}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>

      {/* Record Action Modal */}
      <Modal
        title={t.portfolio.recordAction}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        okText={t.common.submit}
        cancelText={t.common.cancel}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => createMutation.mutate(values)}
        >
          <Form.Item
            name="symbol"
            label={t.portfolio.symbol}
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="stock_name"
            label={t.portfolio.stockName}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="action_type"
            label={t.portfolio.actionType}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 'buy', label: t.portfolio.buy },
                { value: 'sell', label: t.portfolio.sell },
                { value: 'hold', label: t.portfolio.hold },
                { value: 'watch', label: t.portfolio.watch },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="price"
            label={t.portfolio.price}
            rules={[{ required: true }]}
          >
            <InputNumber style={{ width: '100%' }} min={0} precision={2} />
          </Form.Item>

          <Form.Item
            name="quantity"
            label={t.portfolio.quantity}
          >
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>

          <Form.Item
            name="amount"
            label={t.portfolio.amount}
          >
            <InputNumber style={{ width: '100%' }} min={0} precision={2} />
          </Form.Item>

          <Form.Item
            name="reason"
            label={t.portfolio.reason}
          >
            <Input.TextArea rows={3} />
          </Form.Item>

          <Form.Item
            name="action_date"
            label={t.portfolio.actionDate}
            rules={[{ required: true }]}
          >
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="run_id"
            label={t.portfolio.linkedRun}
          >
            <Select
              allowClear
              loading={!runsData}
              options={(runsData?.items ?? []).map((run: WorkflowRun) => ({
                value: run.id,
                label: `${run.symbol} - ${run.id.slice(0, 8)}`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PortfolioPage;
