import React, { useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Button,
  Typography,
  Spin,
  message,
  Tabs,
  Modal,
  Input,
  Space,
  Tooltip,
} from 'antd';
import {
  CheckOutlined,
  CloseOutlined,
  EditOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { evolutionApi } from '../../api/endpoints';
import type { EvolutionSuggestion } from '../../types';
import { useI18n } from '../../i18n';

const { Title, Text, Paragraph } = Typography;

const priorityColor = (p: string) => {
  switch (p) {
    case 'high': return 'red';
    case 'medium': return 'orange';
    case 'low': return 'blue';
    default: return 'default';
  }
};

const typeLabel = (type: string, t: any) => {
  switch (type) {
    case 'skill_weight': return t.evolution.skillWeight;
    case 'skill_prompt': return t.evolution.skillPrompt;
    case 'workflow_structure': return t.evolution.workflowStructure;
    case 'new_skill': return t.evolution.newSkill;
    default: return type;
  }
};

const statusColor = (s: string) => {
  switch (s) {
    case 'pending': return 'processing';
    case 'accepted': return 'success';
    case 'applied': return 'success';
    case 'rejected': return 'error';
    default: return 'default';
  }
};

const EvolutionPage: React.FC = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [modifyModal, setModifyModal] = useState<EvolutionSuggestion | null>(null);
  const [modifyText, setModifyText] = useState('');

  const { data: suggestions, isLoading: loadingPending } = useQuery({
    queryKey: ['evolution-suggestions', 'pending'],
    queryFn: () => evolutionApi.listSuggestions({ status: 'pending', limit: 100 }).then(r => r.data),
  });

  const { data: history, isLoading: loadingHistory } = useQuery({
    queryKey: ['evolution-history'],
    queryFn: () => evolutionApi.getHistory({ limit: 100 }).then(r => r.data),
  });

  const acceptMutation = useMutation({
    mutationFn: (id: string) => evolutionApi.accept(id),
    onSuccess: () => {
      message.success(t.evolution.accepted);
      queryClient.invalidateQueries({ queryKey: ['evolution-suggestions'] });
      queryClient.invalidateQueries({ queryKey: ['evolution-history'] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => evolutionApi.reject(id),
    onSuccess: () => {
      message.success(t.evolution.rejected);
      queryClient.invalidateQueries({ queryKey: ['evolution-suggestions'] });
      queryClient.invalidateQueries({ queryKey: ['evolution-history'] });
    },
  });

  const modifyMutation = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      evolutionApi.modify(id, { suggestion_text: text }),
    onSuccess: () => {
      message.success(t.evolution.modified);
      setModifyModal(null);
      queryClient.invalidateQueries({ queryKey: ['evolution-suggestions'] });
      queryClient.invalidateQueries({ queryKey: ['evolution-history'] });
    },
  });

  if (loadingPending && loadingHistory) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  const pendingColumns = [
    {
      title: t.evolution.evolutionType,
      dataIndex: 'evolution_type',
      key: 'evolution_type',
      render: (val: string) => <Tag>{typeLabel(val, t)}</Tag>,
    },
    {
      title: t.evolution.targetName,
      dataIndex: 'target_name',
      key: 'target_name',
    },
    {
      title: t.evolution.suggestionText,
      dataIndex: 'suggestion_text',
      key: 'suggestion_text',
      width: 300,
      render: (val: string) => (
        <Tooltip title={val}>
          <Text ellipsis style={{ maxWidth: 280 }}>{val}</Text>
        </Tooltip>
      ),
    },
    {
      title: t.evolution.priority,
      dataIndex: 'priority',
      key: 'priority',
      render: (val: string) => (
        <Tag color={priorityColor(val)}>
          {t.evolution[val as 'high' | 'medium' | 'low'] ?? val}
        </Tag>
      ),
    },
    {
      title: t.evolution.confidence,
      dataIndex: 'confidence',
      key: 'confidence',
      render: (val: number) => `${(val * 100).toFixed(0)}%`,
    },
    {
      title: t.common.actions,
      key: 'actions',
      width: 200,
      render: (_: unknown, record: EvolutionSuggestion) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<CheckOutlined />}
            loading={acceptMutation.isPending}
            onClick={() => acceptMutation.mutate(record.id)}
          >
            {t.evolution.accept}
          </Button>
          <Button
            danger
            size="small"
            icon={<CloseOutlined />}
            loading={rejectMutation.isPending}
            onClick={() => rejectMutation.mutate(record.id)}
          >
            {t.evolution.reject}
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setModifyText(record.suggestion_text);
              setModifyModal(record);
            }}
          />
        </Space>
      ),
    },
  ];

  const historyColumns = [
    {
      title: t.evolution.evolutionType,
      dataIndex: 'evolution_type',
      key: 'evolution_type',
      render: (val: string) => <Tag>{typeLabel(val, t)}</Tag>,
    },
    {
      title: t.evolution.targetName,
      dataIndex: 'target_name',
      key: 'target_name',
    },
    {
      title: t.evolution.suggestionText,
      dataIndex: 'suggestion_text',
      key: 'suggestion_text',
      width: 300,
      render: (val: string) => (
        <Tooltip title={val}>
          <Text ellipsis style={{ maxWidth: 280 }}>{val}</Text>
        </Tooltip>
      ),
    },
    {
      title: t.evolution.status,
      dataIndex: 'status',
      key: 'status',
      render: (val: string) => <Tag color={statusColor(val)}>{val}</Tag>,
    },
    {
      title: t.evolution.appliedAt,
      dataIndex: 'applied_at',
      key: 'applied_at',
      render: (val: string | null) => val ? new Date(val).toLocaleString() : '-',
    },
  ];

  const tabItems = [
    {
      key: 'pending',
      label: `${t.evolution.suggestions} (${suggestions?.length ?? 0})`,
      children: (
        <Table
          dataSource={suggestions ?? []}
          columns={pendingColumns}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          size="small"
          locale={{ emptyText: t.evolution.noSuggestions }}
        />
      ),
    },
    {
      key: 'history',
      label: t.evolution.history,
      children: (
        <Table
          dataSource={history ?? []}
          columns={historyColumns}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          size="small"
        />
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>
          <RocketOutlined style={{ marginRight: 8 }} />
          {t.evolution.title}
        </Title>
      </div>

      <Card>
        <Tabs items={tabItems} />
      </Card>

      <Modal
        open={!!modifyModal}
        title={t.evolution.modify}
        onCancel={() => setModifyModal(null)}
        onOk={() => {
          if (modifyModal) {
            modifyMutation.mutate({ id: modifyModal.id, text: modifyText });
          }
        }}
        confirmLoading={modifyMutation.isPending}
      >
        <Paragraph type="secondary" style={{ marginBottom: 16 }}>
          {modifyModal?.target_name} — {modifyModal ? typeLabel(modifyModal.evolution_type, t) : ''}
        </Paragraph>
        <Input.TextArea
          rows={4}
          value={modifyText}
          onChange={(e) => setModifyText(e.target.value)}
        />
      </Modal>
    </div>
  );
};

export default EvolutionPage;
