import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Col, Row, Statistic, Typography, Input, Select, Button, Table, Tag, Space, message } from 'antd';
import { PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { runApi, workflowApi } from '../../api/endpoints';
import type { WorkflowRun } from '../../types';
import { useI18n } from '../../i18n';

const statusColors: Record<string, string> = {
  queued: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
};

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [symbol, setSymbol] = useState('');
  const [selectedWf, setSelectedWf] = useState<string | undefined>();

  const { data: runsData } = useQuery({
    queryKey: ['runs', 'recent'],
    queryFn: () => runApi.list(0, 10).then((r) => r.data),
  });

  const { data: wfData } = useQuery({
    queryKey: ['workflows', 'list'],
    queryFn: () => workflowApi.list(0, 100).then((r) => r.data),
  });

  const handleQuickRun = async () => {
    if (!selectedWf || !symbol.trim()) {
      message.warning('Please select a workflow and enter a symbol');
      return;
    }
    try {
      const { data } = await runApi.submit({ workflow_id: selectedWf, symbol: symbol.trim() });
      message.success(t.dashboard.runSubmitted);
      navigate(`/runs/${data.id}`);
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Failed to submit');
    }
  };

  const runs = runsData?.items || [];
  const total = runsData?.total || 0;
  const completed = runs.filter((r) => r.status === 'completed').length;
  const failed = runs.filter((r) => r.status === 'failed').length;

  const columns = [
    { title: t.runs.symbol, dataIndex: 'symbol', key: 'symbol' },
    {
      title: t.common.status,
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={statusColors[s]}>{s}</Tag>,
    },
    { title: t.common.created, dataIndex: 'created_at', key: 'created_at', render: (v: string) => new Date(v).toLocaleString() },
    {
      title: t.common.actions,
      key: 'action',
      render: (_: unknown, record: WorkflowRun) => (
        <Button type="link" size="small" onClick={() => navigate(`/runs/${record.id}`)}>
          {t.common.view}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={4}>{t.dashboard.title}</Typography.Title>

      {/* Stats */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card><Statistic title={t.dashboard.totalRuns} value={total} prefix={<PlayCircleOutlined />} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title={t.dashboard.completed} value={completed} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#3f8600' }} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title={t.dashboard.failed} value={failed} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#cf1322' }} /></Card>
        </Col>
      </Row>

      {/* Quick Analysis */}
      <Card title={t.dashboard.quickAnalysis} style={{ marginBottom: 24 }}>
        <Space>
          <Input
            placeholder={t.dashboard.symbolPlaceholder}
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            style={{ width: 200 }}
          />
          <Select
            placeholder={t.dashboard.selectWorkflow}
            style={{ width: 250 }}
            value={selectedWf}
            onChange={setSelectedWf}
            options={(wfData?.items || []).map((w) => ({ label: w.name, value: w.id }))}
          />
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleQuickRun}>
            {t.common.run}
          </Button>
        </Space>
      </Card>

      {/* Recent Runs */}
      <Card title={t.dashboard.recentRuns}>
        <Table columns={columns} dataSource={runs} rowKey="id" pagination={false} size="small" />
      </Card>
    </div>
  );
};

export default DashboardPage;
