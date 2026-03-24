import React, { useState } from 'react';
import {
  Typography, Table, Button, Space, Tag, Modal, Form, Input, InputNumber,
  message, Card, Row, Col, Statistic, Descriptions, List, Select, Tabs,
} from 'antd';
import {
  ExperimentOutlined, TrophyOutlined, FallOutlined,
  RiseOutlined, FundOutlined, BarChartOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { screenerBacktestApi, screenerApi } from '../../api/endpoints';
import { useI18n } from '../../i18n';
import type { ScreenerBacktestResult } from '../../types';

const { Title, Text, Paragraph } = Typography;

const VERDICT_COLORS: Record<string, string> = {
  effective: 'success',
  marginal: 'warning',
  ineffective: 'error',
};

const ScreenerBacktestPage: React.FC = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [runModalOpen, setRunModalOpen] = useState(false);
  const [detailModal, setDetailModal] = useState<ScreenerBacktestResult | null>(null);
  const [form] = Form.useForm();

  // Fetch results
  const { data: results, isLoading } = useQuery({
    queryKey: ['screener-backtest', 'results'],
    queryFn: () => screenerBacktestApi.listResults().then(r => r.data),
  });

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ['screener-backtest', 'stats'],
    queryFn: () => screenerBacktestApi.getStats().then(r => r.data),
  });

  // Fetch screener jobs for the run form
  const { data: screenerJobs } = useQuery({
    queryKey: ['screener', 'jobs'],
    queryFn: () => screenerApi.listJobs(0, 100).then(r => r.data),
  });

  const runMutation = useMutation({
    mutationFn: screenerBacktestApi.run,
    onSuccess: () => {
      message.success(t.screenerBacktest.backtestSubmitted);
      queryClient.invalidateQueries({ queryKey: ['screener-backtest'] });
      setRunModalOpen(false);
      form.resetFields();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || 'Failed'),
  });

  const handleRun = async () => {
    const values = await form.validateFields();
    runMutation.mutate({ job_id: values.job_id, period_days: values.period_days || 30 });
  };

  const verdictLabel = (v: string) => {
    const s = t.screenerBacktest as any;
    const map: Record<string, string> = {
      effective: s.effective, marginal: s.marginal, ineffective: s.ineffective,
    };
    return map[v] || v;
  };

  const completedJobs = (screenerJobs || []).filter((j: any) => j.status === 'completed');

  const columns = [
    {
      title: t.screenerBacktest.strategyId,
      dataIndex: 'strategy_id',
      key: 'strategy_id',
      width: 140,
      render: (v: string | null) => v || '-',
    },
    {
      title: t.screenerBacktest.periodDays,
      dataIndex: 'period_days',
      key: 'period_days',
      width: 80,
      align: 'center' as const,
    },
    {
      title: t.screenerBacktest.totalStocks,
      dataIndex: 'total_stocks',
      key: 'total_stocks',
      width: 80,
      align: 'center' as const,
    },
    {
      title: t.screenerBacktest.avgReturn,
      dataIndex: 'avg_return_pct',
      key: 'avg_return_pct',
      width: 100,
      render: (v: number | null) => v != null ? (
        <span style={{ color: v >= 0 ? '#3f8600' : '#cf1322' }}>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </span>
      ) : '-',
    },
    {
      title: t.screenerBacktest.winRate,
      dataIndex: 'win_rate',
      key: 'win_rate',
      width: 80,
      render: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '-',
    },
    {
      title: t.screenerBacktest.sharpe,
      dataIndex: 'sharpe_ratio',
      key: 'sharpe_ratio',
      width: 80,
      render: (v: number | null) => v != null ? v.toFixed(2) : '-',
    },
    {
      title: t.screenerBacktest.overallVerdict,
      key: 'verdict',
      width: 100,
      render: (_: unknown, record: ScreenerBacktestResult) => {
        const verdict = record.diagnosis?.overall_verdict;
        if (!verdict) return '-';
        return <Tag color={VERDICT_COLORS[verdict]}>{verdictLabel(verdict)}</Tag>;
      },
    },
    {
      title: t.screenerBacktest.backtestDate,
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: t.common.actions,
      key: 'actions',
      width: 80,
      render: (_: unknown, record: ScreenerBacktestResult) => (
        <Button size="small" onClick={() => setDetailModal(record)}>
          {t.common.view}
        </Button>
      ),
    },
  ];

  const stockColumns = [
    { title: t.screenerBacktest.symbol, dataIndex: 'symbol', key: 'symbol', width: 90 },
    { title: t.screenerBacktest.stockName, dataIndex: 'name', key: 'name', width: 100, ellipsis: true },
    {
      title: t.screenerBacktest.entryPrice,
      dataIndex: 'entry_price',
      key: 'entry_price',
      width: 90,
      render: (v: number | null) => v != null ? v.toFixed(2) : '-',
    },
    {
      title: t.screenerBacktest.currentPrice,
      dataIndex: 'current_price',
      key: 'current_price',
      width: 90,
      render: (v: number | null) => v != null ? v.toFixed(2) : '-',
    },
    {
      title: t.screenerBacktest.priceChange,
      dataIndex: 'price_change_pct',
      key: 'price_change_pct',
      width: 90,
      render: (v: number | null) => v != null ? (
        <span style={{ color: v >= 0 ? '#3f8600' : '#cf1322', fontWeight: 600 }}>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </span>
      ) : '-',
    },
    {
      title: t.screenerBacktest.maxGain,
      dataIndex: 'max_gain_pct',
      key: 'max_gain_pct',
      width: 80,
      render: (v: number | null) => v != null ? (
        <span style={{ color: '#3f8600' }}>+{v.toFixed(1)}%</span>
      ) : '-',
    },
    {
      title: t.screenerBacktest.maxDrawdown,
      dataIndex: 'max_drawdown_pct',
      key: 'max_drawdown_pct',
      width: 80,
      render: (v: number | null) => v != null ? (
        <span style={{ color: '#cf1322' }}>{v.toFixed(1)}%</span>
      ) : '-',
    },
  ];

  const diagnosis = detailModal?.diagnosis;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t.screenerBacktest.title}</Title>
        <Button type="primary" icon={<ExperimentOutlined />} onClick={() => setRunModalOpen(true)}>
          {t.screenerBacktest.runBacktest}
        </Button>
      </div>

      {/* Stats cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title={t.screenerBacktest.totalBacktests}
              value={stats?.total_backtests || 0}
              prefix={<BarChartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title={t.screenerBacktest.avgReturn}
              value={stats?.avg_return || 0}
              precision={2}
              suffix="%"
              valueStyle={{ color: (stats?.avg_return || 0) >= 0 ? '#3f8600' : '#cf1322' }}
              prefix={(stats?.avg_return || 0) >= 0 ? <RiseOutlined /> : <FallOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title={t.screenerBacktest.avgWinRate}
              value={stats?.avg_win_rate || 0}
              precision={1}
              suffix="%"
              prefix={<TrophyOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title={t.screenerBacktest.avgSharpe}
              value={stats?.avg_sharpe || 0}
              precision={2}
              prefix={<FundOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Results table */}
      <Table
        dataSource={results || []}
        columns={columns}
        loading={isLoading}
        rowKey="id"
        pagination={{ pageSize: 20, showSizeChanger: false }}
        scroll={{ x: 1000 }}
        locale={{ emptyText: t.screenerBacktest.noResults }}
      />

      {/* Run modal */}
      <Modal
        title={t.screenerBacktest.runBacktest}
        open={runModalOpen}
        onOk={handleRun}
        onCancel={() => setRunModalOpen(false)}
        confirmLoading={runMutation.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="job_id"
            label={t.screenerBacktest.jobId}
            rules={[{ required: true }]}
          >
            <Select
              placeholder={t.screenerBacktest.jobIdPlaceholder}
              showSearch
              optionFilterProp="label"
              options={completedJobs.map((j: any) => ({
                value: j.id,
                label: `${j.strategy_id || 'custom'} — ${new Date(j.created_at).toLocaleDateString()} (${(j.results?.length || 0)} stocks)`,
              }))}
            />
          </Form.Item>
          <Form.Item name="period_days" label={t.screenerBacktest.periodDays} initialValue={30}>
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Detail modal */}
      <Modal
        title={t.screenerBacktest.results}
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={null}
        width={900}
        destroyOnClose
      >
        {detailModal && (
          <Tabs items={[
            {
              key: 'overview',
              label: t.screenerBacktest.stats,
              children: (
                <Descriptions bordered size="small" column={2}>
                  <Descriptions.Item label={t.screenerBacktest.strategyId}>
                    {detailModal.strategy_id || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t.screenerBacktest.periodDays}>
                    {detailModal.period_days}
                  </Descriptions.Item>
                  <Descriptions.Item label={t.screenerBacktest.totalStocks}>
                    {detailModal.total_stocks}
                  </Descriptions.Item>
                  <Descriptions.Item label={t.screenerBacktest.avgReturn}>
                    <span style={{ color: (detailModal.avg_return_pct || 0) >= 0 ? '#3f8600' : '#cf1322', fontWeight: 600 }}>
                      {(detailModal.avg_return_pct || 0) >= 0 ? '+' : ''}{(detailModal.avg_return_pct || 0).toFixed(2)}%
                    </span>
                  </Descriptions.Item>
                  <Descriptions.Item label={t.screenerBacktest.winRate}>
                    {(detailModal.win_rate || 0).toFixed(1)}%
                  </Descriptions.Item>
                  <Descriptions.Item label={t.screenerBacktest.sharpe}>
                    {detailModal.sharpe_ratio != null ? detailModal.sharpe_ratio.toFixed(2) : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t.screenerBacktest.maxGain}>
                    <span style={{ color: '#3f8600' }}>
                      +{(detailModal.max_gain_pct || 0).toFixed(2)}%
                    </span>
                  </Descriptions.Item>
                  <Descriptions.Item label={t.screenerBacktest.maxLoss}>
                    <span style={{ color: '#cf1322' }}>
                      {(detailModal.max_loss_pct || 0).toFixed(2)}%
                    </span>
                  </Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'stocks',
              label: t.screenerBacktest.stockDetails,
              children: (
                <Table
                  dataSource={detailModal.stock_details || []}
                  columns={stockColumns}
                  rowKey="symbol"
                  pagination={false}
                  size="small"
                  scroll={{ y: 400 }}
                />
              ),
            },
            {
              key: 'diagnosis',
              label: t.screenerBacktest.diagnosis,
              children: diagnosis ? (
                <div>
                  <Space style={{ marginBottom: 16 }}>
                    <Tag color={VERDICT_COLORS[diagnosis.overall_verdict]} style={{ fontSize: 14, padding: '4px 12px' }}>
                      {verdictLabel(diagnosis.overall_verdict)}
                    </Tag>
                    <Text strong>{t.screenerBacktest.score}: {diagnosis.score?.toFixed(2)}</Text>
                  </Space>

                  <Descriptions bordered size="small" column={1} style={{ marginBottom: 16 }}>
                    <Descriptions.Item label={t.screenerBacktest.rootCause}>
                      {diagnosis.root_cause}
                    </Descriptions.Item>
                  </Descriptions>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Card size="small" title={<span style={{ color: '#3f8600' }}>{t.screenerBacktest.strengths}</span>}>
                        <List
                          size="small"
                          dataSource={diagnosis.strengths || []}
                          renderItem={(item: string) => <List.Item>{item}</List.Item>}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title={<span style={{ color: '#cf1322' }}>{t.screenerBacktest.weaknesses}</span>}>
                        <List
                          size="small"
                          dataSource={diagnosis.weaknesses || []}
                          renderItem={(item: string) => <List.Item>{item}</List.Item>}
                        />
                      </Card>
                    </Col>
                  </Row>

                  <Row gutter={16} style={{ marginTop: 16 }}>
                    <Col span={12}>
                      <Card size="small" title={<span style={{ color: '#3f8600' }}>{t.screenerBacktest.bestPicks}</span>}>
                        <List
                          size="small"
                          dataSource={diagnosis.best_picks || []}
                          renderItem={(item: string) => <List.Item>{item}</List.Item>}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title={<span style={{ color: '#cf1322' }}>{t.screenerBacktest.worstPicks}</span>}>
                        <List
                          size="small"
                          dataSource={diagnosis.worst_picks || []}
                          renderItem={(item: string) => <List.Item>{item}</List.Item>}
                        />
                      </Card>
                    </Col>
                  </Row>

                  {diagnosis.improvement_suggestions?.length > 0 && (
                    <Card size="small" title={t.screenerBacktest.suggestions} style={{ marginTop: 16 }}>
                      <List
                        size="small"
                        dataSource={diagnosis.improvement_suggestions}
                        renderItem={(item) => (
                          <List.Item>
                            <Space direction="vertical" style={{ width: '100%' }}>
                              <Space>
                                <Tag color="blue">{item.type}</Tag>
                                <Tag color={item.priority === 'high' ? 'red' : item.priority === 'medium' ? 'orange' : 'default'}>
                                  {item.priority}
                                </Tag>
                                <Text type="secondary">
                                  {t.screenerBacktest.score}: {(item.confidence * 100).toFixed(0)}%
                                </Text>
                              </Space>
                              <Text>{item.suggestion}</Text>
                            </Space>
                          </List.Item>
                        )}
                      />
                    </Card>
                  )}
                </div>
              ) : (
                <Paragraph type="secondary">{t.backtest.noDiagnosis}</Paragraph>
              ),
            },
          ]} />
        )}
      </Modal>
    </div>
  );
};

export default ScreenerBacktestPage;
