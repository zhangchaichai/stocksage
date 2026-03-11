import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Table, Tag, Typography } from 'antd';
import { EyeOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { runApi } from '../../api/endpoints';
import type { WorkflowRun } from '../../types';
import { useI18n } from '../../i18n';

const statusColors: Record<string, string> = {
  queued: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
};

const RunListPage: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useI18n();

  const { data, isLoading } = useQuery({
    queryKey: ['runs', 'list'],
    queryFn: () => runApi.list(0, 50).then((r) => r.data),
  });

  const columns = [
    {
      title: t.runs.symbol,
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: t.runs.stockName,
      dataIndex: 'stock_name',
      key: 'stock_name',
    },
    {
      title: t.common.status,
      dataIndex: 'status',
      key: 'status',
      render: (status: WorkflowRun['status']) => (
        <Tag color={statusColors[status]}>{status}</Tag>
      ),
    },
    {
      title: t.common.created,
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: t.common.actions,
      key: 'actions',
      render: (_: unknown, record: WorkflowRun) => (
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => navigate(`/runs/${record.id}`)}
        >
          {t.common.view}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>{t.runs.title}</Typography.Title>

      <Table
        columns={columns}
        dataSource={data?.items || []}
        rowKey="id"
        loading={isLoading}
        pagination={{
          total: data?.total || 0,
          pageSize: 50,
          showSizeChanger: false,
          showTotal: (total) => t.runs.totalCount.replace('{count}', String(total)),
        }}
      />
    </div>
  );
};

export default RunListPage;
