import React from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Button,
  Typography,
  Progress,
  Spin,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { backtestApi } from '../../api/endpoints';
import type { BacktestResult } from '../../types';
import { useI18n } from '../../i18n';

const { Title } = Typography;

const directionColor = (dir: string) => {
  switch (dir) {
    case 'up':
      return 'green';
    case 'down':
      return 'red';
    case 'neutral':
      return 'blue';
    default:
      return 'default';
  }
};

const directionLabel = (dir: string, t: any) => {
  switch (dir) {
    case 'up':
      return t.backtest.up;
    case 'down':
      return t.backtest.down;
    case 'neutral':
      return t.backtest.neutral;
    default:
      return dir;
  }
};

const BacktestDashboardPage: React.FC = () => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: stats, isLoading: loadingStats } = useQuery({
    queryKey: ['backtest-stats'],
    queryFn: () => backtestApi.getStats().then(r => r.data),
  });

  const { data: results, isLoading: loadingResults } = useQuery({
    queryKey: ['backtest-results'],
    queryFn: () => backtestApi.listResults({ limit: 100 }).then(r => r.data),
  });

  const runAllMutation = useMutation({
    mutationFn: () => backtestApi.runAll({ period_days: 30 }),
    onSuccess: () => {
      message.success(t.backtest.batchComplete);
      queryClient.invalidateQueries({ queryKey: ['backtest-stats'] });
      queryClient.invalidateQueries({ queryKey: ['backtest-results'] });
    },
  });

  const isLoading = loadingStats || loadingResults;

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  const columns = [
    {
      title: t.backtest.symbol,
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t.backtest.actionPrice,
      dataIndex: 'action_price',
      key: 'action_price',
      render: (val: number) => `¥${val.toFixed(2)}`,
    },
    {
      title: t.backtest.periodDays,
      dataIndex: 'period_days',
      key: 'period_days',
    },
    {
      title: t.backtest.currentPrice,
      dataIndex: 'current_price',
      key: 'current_price',
      render: (val: number) => `¥${val.toFixed(2)}`,
    },
    {
      title: t.backtest.priceChange,
      dataIndex: 'price_change_pct',
      key: 'price_change_pct',
      render: (val: number) => (
        <span style={{ color: val > 0 ? '#52c41a' : val < 0 ? '#ff4d4f' : undefined }}>
          {val > 0 ? '+' : ''}{val.toFixed(2)}%
        </span>
      ),
    },
    {
      title: t.backtest.predictedDirection,
      dataIndex: 'predicted_direction',
      key: 'predicted_direction',
      render: (val: string) => (
        <Tag color={directionColor(val)}>{directionLabel(val, t)}</Tag>
      ),
    },
    {
      title: t.backtest.actualDirection,
      dataIndex: 'actual_direction',
      key: 'actual_direction',
      render: (val: string) => (
        <Tag color={directionColor(val)}>{directionLabel(val, t)}</Tag>
      ),
    },
    {
      title: t.backtest.directionCorrect,
      dataIndex: 'direction_correct',
      key: 'direction_correct',
      render: (val: boolean) =>
        val ? (
          <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} />
        ) : (
          <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />
        ),
    },
    {
      title: t.backtest.date,
      dataIndex: 'created_at',
      key: 'created_at',
      render: (val: string) => new Date(val).toLocaleDateString(),
      sorter: (a: BacktestResult, b: BacktestResult) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, record: BacktestResult) => (
        <Button type="link" size="small" onClick={() => navigate(`/backtest/${record.id}`)}>
          {t.backtest.view}
        </Button>
      ),
    },
  ];

  const dimensionEntries = stats?.dimension_accuracy
    ? Object.entries(stats.dimension_accuracy)
    : [];

  return (
    <div>
      {/* Title Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          {t.backtest.title}
        </Title>
        <Button
          type="primary"
          icon={<ExperimentOutlined />}
          loading={runAllMutation.isPending}
          onClick={() => runAllMutation.mutate()}
        >
          {t.backtest.runAll}
        </Button>
      </div>

      {/* Statistics Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.directionAccuracy}
              value={stats?.direction_accuracy ?? 0}
              suffix="%"
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.avgReturn}
              value={stats?.avg_return ?? 0}
              suffix="%"
              valueStyle={{
                color:
                  (stats?.avg_return ?? 0) > 0
                    ? '#52c41a'
                    : (stats?.avg_return ?? 0) < 0
                      ? '#ff4d4f'
                      : undefined,
              }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.winRate}
              value={stats?.win_rate ?? 0}
              suffix="%"
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.totalBacktests}
              value={stats?.total_actions ?? 0}
            />
          </Card>
        </Col>
      </Row>

      {/* Risk Indicators (Phase 4) */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.avgSharpe}
              value={stats?.avg_sharpe ?? 0}
              precision={4}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.avgSortino}
              value={stats?.avg_sortino ?? 0}
              precision={4}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.avgVar95}
              value={stats?.avg_var_95 ?? 0}
              precision={4}
              suffix="%"
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title={t.backtest.dealerSignalAccuracy}
              value={stats?.dealer_signal_accuracy ?? 0}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      {/* Dimension Accuracy */}
      <Card title={t.backtest.dimensionAccuracy} style={{ marginBottom: 24 }}>
        {dimensionEntries.length > 0 ? (
          <Row gutter={[24, 16]}>
            {dimensionEntries.map(([dimension, value]) => {
              let status: 'success' | 'normal' | 'exception' = 'exception';
              if (value > 70) status = 'success';
              else if (value > 40) status = 'normal';

              return (
                <Col key={dimension} xs={24} sm={12} md={8} lg={6}>
                  <div style={{ marginBottom: 8 }}>
                    <Typography.Text strong>{dimension}</Typography.Text>
                  </div>
                  <Progress percent={Math.round(value)} status={status} />
                </Col>
              );
            })}
          </Row>
        ) : (
          <Typography.Text type="secondary">{t.backtest.noDimension}</Typography.Text>
        )}
      </Card>

      {/* Wyckoff Phase Accuracy (Phase 4) */}
      <Card title={t.backtest.wyckoffAccuracy} style={{ marginBottom: 24 }}>
        {stats?.wyckoff_accuracy && Object.keys(stats.wyckoff_accuracy).length > 0 ? (
          <Row gutter={[24, 16]}>
            {Object.entries(stats.wyckoff_accuracy).map(([phase, value]) => {
              let status: 'success' | 'normal' | 'exception' = 'exception';
              if (value > 70) status = 'success';
              else if (value > 40) status = 'normal';

              const phaseLabel = (t.backtest as Record<string, string>)[phase] || phase;
              return (
                <Col key={phase} xs={24} sm={12} md={6}>
                  <div style={{ marginBottom: 8 }}>
                    <Typography.Text strong>{phaseLabel}</Typography.Text>
                  </div>
                  <Progress percent={Math.round(value)} status={status} />
                </Col>
              );
            })}
          </Row>
        ) : (
          <Typography.Text type="secondary">{t.backtest.noDimension}</Typography.Text>
        )}
      </Card>

      {/* Backtest Results Table */}
      <Card title={t.backtest.results}>
        <Table
          dataSource={results ?? []}
          columns={columns}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>
    </div>
  );
};

export default BacktestDashboardPage;
