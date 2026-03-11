import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Table, Tag, Space, Typography, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workflowApi } from '../../api/endpoints';
import type { Workflow } from '../../types';
import { useI18n } from '../../i18n';

const WorkflowListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useI18n();

  const { data, isLoading } = useQuery({
    queryKey: ['workflows', 'list'],
    queryFn: () => workflowApi.list(0, 50).then((r) => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => workflowApi.delete(id),
    onSuccess: () => {
      message.success(t.workflows.deleted);
      queryClient.invalidateQueries({ queryKey: ['workflows', 'list'] });
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || 'Failed to delete workflow');
    },
  });

  const columns = [
    {
      title: t.common.name,
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t.common.version,
      dataIndex: 'version',
      key: 'version',
    },
    {
      title: t.common.public,
      dataIndex: 'is_public',
      key: 'is_public',
      render: (isPublic: boolean) => (
        <Tag color={isPublic ? 'green' : 'default'}>
          {isPublic ? t.common.public : t.common.private}
        </Tag>
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
      render: (_: unknown, record: Workflow) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => navigate(`/workflows/${record.id}/edit`)}
          >
            {t.common.edit}
          </Button>
          <Popconfirm
            title={t.workflows.deleteTitle}
            description={t.workflows.deleteConfirm}
            onConfirm={() => deleteMutation.mutate(record.id)}
            okText={t.common.yes}
            cancelText={t.common.no}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t.common.delete}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>{t.workflows.title}</Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/workflows/new')}
        >
          {t.workflows.createNew}
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={data?.items || []}
        rowKey="id"
        loading={isLoading}
        pagination={{
          total: data?.total || 0,
          pageSize: 50,
          showSizeChanger: false,
          showTotal: (total) => t.workflows.totalCount.replace('{count}', String(total)),
        }}
      />
    </div>
  );
};

export default WorkflowListPage;
