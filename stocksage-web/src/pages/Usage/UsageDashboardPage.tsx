import React, { useState } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Select,
  Typography,
  Progress,
  Spin,
  Empty,
} from 'antd';
import {
  ThunderboltOutlined,
  PlayCircleOutlined,
  DashboardOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { usageApi } from '../../api/endpoints';
import type { DailyUsage } from '../../types';
import { useI18n } from '../../i18n';

const { Title } = Typography;

const UsageDashboardPage: React.FC = () => {
  const { t } = useI18n();
  const [period, setPeriod] = useState('all');

  const periodOptions = [
    { value: 'all', label: t.usage.allTime },
    { value: 'week', label: t.usage.thisWeek },
    { value: 'month', label: t.usage.thisMonth },
  ];

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['usage-summary', period],
    queryFn: () => usageApi.summary(period),
    select: (res) => res.data,
  });

  const { data: dashboard, isLoading: dailyLoading } = useQuery({
    queryKey: ['usage-daily'],
    queryFn: () => usageApi.daily(30),
    select: (res) => res.data,
  });

  const { data: quota, isLoading: quotaLoading } = useQuery({
    queryKey: ['usage-quota'],
    queryFn: () => usageApi.quota(),
    select: (res) => res.data,
  });

  const columns = [
    {
      title: t.usage.date,
      dataIndex: 'date',
      key: 'date',
      sorter: (a: DailyUsage, b: DailyUsage) => a.date.localeCompare(b.date),
    },
    {
      title: t.usage.inputTokens,
      dataIndex: 'tokens_input',
      key: 'tokens_input',
      render: (val: number) => val.toLocaleString(),
      sorter: (a: DailyUsage, b: DailyUsage) => a.tokens_input - b.tokens_input,
    },
    {
      title: t.usage.outputTokens,
      dataIndex: 'tokens_output',
      key: 'tokens_output',
      render: (val: number) => val.toLocaleString(),
      sorter: (a: DailyUsage, b: DailyUsage) => a.tokens_output - b.tokens_output,
    },
    {
      title: t.usage.totalRuns,
      dataIndex: 'runs_count',
      key: 'runs_count',
      sorter: (a: DailyUsage, b: DailyUsage) => a.runs_count - b.runs_count,
    },
  ];

  const isLoading = summaryLoading || dailyLoading || quotaLoading;

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  const quotaPercent = quota
    ? Math.round((quota.used_today / Math.max(quota.daily_limit, 1)) * 100)
    : 0;

  // Find max tokens for the bar chart scaling
  const dailyData = dashboard?.daily ?? [];
  const maxTokens = dailyData.reduce(
    (max, d) => Math.max(max, d.tokens_input + d.tokens_output),
    1,
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>{t.usage.title}</Title>
        <Select
          value={period}
          onChange={setPeriod}
          options={periodOptions}
          style={{ width: 160 }}
        />
      </div>

      {/* Summary Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title={t.usage.totalTokens}
              value={summary?.total_tokens ?? 0}
              prefix={<ThunderboltOutlined />}
              groupSeparator=","
            />
            <div style={{ marginTop: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t.usage.inputTokens}: {(summary?.total_tokens_input ?? 0).toLocaleString()}
                {' | '}
                {t.usage.outputTokens}: {(summary?.total_tokens_output ?? 0).toLocaleString()}
              </Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title={t.usage.totalRuns}
              value={summary?.total_runs ?? 0}
              prefix={<PlayCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title={t.usage.quota}
              value={quota?.remaining ?? 0}
              suffix={`/ ${quota?.daily_limit ?? 0}`}
              prefix={<DashboardOutlined />}
            />
            <Progress
              percent={quotaPercent}
              status={quotaPercent >= 90 ? 'exception' : 'active'}
              style={{ marginTop: 8 }}
            />
          </Card>
        </Col>
      </Row>

      {/* Daily Usage Bar Chart (CSS-based) */}
      <Card title={t.usage.dailyUsage} style={{ marginBottom: 24 }}>
        {dailyData.length === 0 ? (
          <Empty description={t.common.noData} />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-end',
                gap: 2,
                height: 200,
                padding: '0 4px',
                minWidth: dailyData.length * 24,
              }}
            >
              {dailyData.map((day) => {
                const inputHeight = (day.tokens_input / maxTokens) * 180;
                const outputHeight = (day.tokens_output / maxTokens) * 180;
                return (
                  <div
                    key={day.date}
                    style={{
                      flex: 1,
                      minWidth: 20,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: 0,
                    }}
                    title={`${day.date}\nInput: ${day.tokens_input.toLocaleString()}\nOutput: ${day.tokens_output.toLocaleString()}\nRuns: ${day.runs_count}`}
                  >
                    <div
                      style={{
                        width: '80%',
                        backgroundColor: '#91caff',
                        height: inputHeight,
                        borderRadius: '2px 2px 0 0',
                      }}
                    />
                    <div
                      style={{
                        width: '80%',
                        backgroundColor: '#1677ff',
                        height: outputHeight,
                        borderRadius: '0 0 2px 2px',
                      }}
                    />
                  </div>
                );
              })}
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginTop: 8,
                fontSize: 11,
                color: '#999',
              }}
            >
              <span>{dailyData[0]?.date}</span>
              <span>{dailyData[dailyData.length - 1]?.date}</span>
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 8, justifyContent: 'center' }}>
              <span>
                <span style={{ display: 'inline-block', width: 12, height: 12, backgroundColor: '#91caff', marginRight: 4, borderRadius: 2, verticalAlign: 'middle' }} />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t.usage.inputTokens}</Typography.Text>
              </span>
              <span>
                <span style={{ display: 'inline-block', width: 12, height: 12, backgroundColor: '#1677ff', marginRight: 4, borderRadius: 2, verticalAlign: 'middle' }} />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t.usage.outputTokens}</Typography.Text>
              </span>
            </div>
          </div>
        )}
      </Card>

      {/* Daily Breakdown Table */}
      <Card title={t.usage.dailyBreakdown}>
        <Table
          dataSource={dailyData}
          columns={columns}
          rowKey="date"
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>
    </div>
  );
};

export default UsageDashboardPage;
