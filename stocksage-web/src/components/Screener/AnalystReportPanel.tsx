import React from 'react';
import { Card, Table, Tabs, Tag, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import type { AnalystReports } from '../../types';

const { Text } = Typography;

interface AnalystReportPanelProps {
  reports: AnalystReports;
}

const AnalystReportPanel: React.FC<AnalystReportPanelProps> = ({ reports }) => {
  const { analysts, synthesis, meta } = reports;

  const pickColumns = [
    { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 90 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100 },
    {
      title: '综合评分',
      dataIndex: 'score',
      key: 'score',
      width: 90,
      sorter: (a: any, b: any) => (a.score || 0) - (b.score || 0),
      defaultSortOrder: 'descend' as const,
      render: (v: number) =>
        v != null ? (
          <Tag color={v >= 8 ? 'green' : v >= 6 ? 'orange' : 'default'}>
            {v.toFixed(1)}
          </Tag>
        ) : (
          <Tag>-</Tag>
        ),
    },
    {
      title: '推荐理由',
      dataIndex: 'reason',
      key: 'reason',
      render: (v: string) =>
        v ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {v}
          </Text>
        ) : null,
    },
  ];

  // Build tab items: one per analyst + synthesis
  const tabItems = [
    ...analysts.map((a) => ({
      key: a.id,
      label: (
        <span>
          {a.icon} {a.title}
        </span>
      ),
      children: (
        <div className="analyst-report-content" style={{ maxHeight: 600, overflow: 'auto', padding: '0 4px' }}>
          <ReactMarkdown>{a.report}</ReactMarkdown>
        </div>
      ),
    })),
    {
      key: 'synthesis',
      label: <span>🎯 综合推荐</span>,
      children: (
        <div>
          {synthesis.top_picks?.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                Top {synthesis.top_picks.length} 推荐
              </Text>
              <Table
                dataSource={synthesis.top_picks}
                columns={pickColumns}
                rowKey="symbol"
                size="small"
                pagination={false}
              />
            </div>
          )}
          <div className="analyst-report-content" style={{ maxHeight: 500, overflow: 'auto', padding: '0 4px' }}>
            <ReactMarkdown>{synthesis.report}</ReactMarkdown>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div>
      {/* Meta bar */}
      <Card
        size="small"
        style={{ marginBottom: 12, background: '#fafafa' }}
        bodyStyle={{ padding: '8px 16px' }}
      >
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12 }}>
          {/* 优先显示时间段，其次显示单一数据日期 */}
          {(meta as any).date_range_desc ? (
            <span>
              <Text type="secondary">数据时间段：</Text>
              <Tag color="green">{(meta as any).date_range_desc}</Tag>
            </span>
          ) : meta.data_date ? (
            <span>
              <Text type="secondary">数据基准日：</Text>
              <Tag color="green">{meta.data_date}</Tag>
            </span>
          ) : null}
          {meta.report_date && (
            <span>
              <Text type="secondary">报告时间：</Text>
              {meta.report_date}
            </span>
          )}
          <span>
            <Text type="secondary">候选池：</Text>
            <Tag color="blue">{meta.candidate_count} 只</Tag>
          </span>
          <span>
            <Text type="secondary">策略：</Text>
            {meta.strategy}
          </span>
          <span>
            <Text type="secondary">耗时：</Text>
            {meta.duration_sec}s
          </span>
          <span>
            <Text type="secondary">Token：</Text>
            ~{Math.round((meta.total_input_tokens + meta.total_output_tokens) / 1000)}K
          </span>
        </div>
      </Card>

      <Tabs items={tabItems} size="small" defaultActiveKey="synthesis" />
    </div>
  );
};

export default AnalystReportPanel;
