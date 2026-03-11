import React, { useState } from 'react';
import {
  Button,
  Table,
  Tag,
  Space,
  Typography,
  Modal,
  Form,
  Input,
  Select,
  message,
  Popconfirm,
  Card,
  Row,
  Col,
  Collapse,
  Divider,
  Drawer,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  TeamOutlined,
  ExperimentOutlined,
  AimOutlined,
  EyeOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { skillApi } from '../../api/endpoints';
import type { CustomSkill, BuiltinSkill } from '../../types';
import { useI18n } from '../../i18n';

const SKILL_TYPES = ['agent', 'data', 'decision', 'expert', 'debate'];

const skillTypeColors: Record<string, string> = {
  agent: 'blue',
  data: 'cyan',
  decision: 'orange',
  expert: 'purple',
  debate: 'magenta',
};

const categoryColors: Record<string, string> = {
  Data: '#1677ff',
  Analyst: '#52c41a',
  Debate: '#fa8c16',
  Expert: '#722ed1',
  Decision: '#eb2f96',
};

const categoryIcons: Record<string, React.ReactNode> = {
  Data: <DatabaseOutlined />,
  Analyst: <LineChartOutlined />,
  Debate: <TeamOutlined />,
  Expert: <ExperimentOutlined />,
  Decision: <AimOutlined />,
};

interface SkillFormValues {
  name: string;
  type: string;
  definition_md: string;
}

const SkillsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [form] = Form.useForm<SkillFormValues>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<CustomSkill | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedBuiltin, setSelectedBuiltin] = useState<BuiltinSkill | null>(null);

  // Custom skills
  const { data, isLoading } = useQuery({
    queryKey: ['skills', 'list'],
    queryFn: () => skillApi.list(0, 50).then((r) => r.data),
  });

  // Built-in skills
  const { data: builtins } = useQuery({
    queryKey: ['skills', 'builtins'],
    queryFn: () => skillApi.builtins().then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: (values: SkillFormValues) => skillApi.create(values),
    onSuccess: () => {
      message.success(t.skills.skillCreated);
      queryClient.invalidateQueries({ queryKey: ['skills', 'list'] });
      closeModal();
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || 'Failed to create skill');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: string; values: Partial<SkillFormValues> }) =>
      skillApi.update(id, values),
    onSuccess: () => {
      message.success(t.skills.skillUpdated);
      queryClient.invalidateQueries({ queryKey: ['skills', 'list'] });
      closeModal();
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || 'Failed to update skill');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => skillApi.delete(id),
    onSuccess: () => {
      message.success(t.skills.skillDeleted);
      queryClient.invalidateQueries({ queryKey: ['skills', 'list'] });
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || 'Failed to delete skill');
    },
  });

  const openCreateModal = () => {
    setEditingSkill(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEditModal = (skill: CustomSkill) => {
    setEditingSkill(skill);
    form.setFieldsValue({
      name: skill.name,
      type: skill.type,
      definition_md: skill.definition_md,
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingSkill(null);
    form.resetFields();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingSkill) {
        updateMutation.mutate({ id: editingSkill.id, values });
      } else {
        createMutation.mutate(values);
      }
    } catch {
      // validation errors handled by form
    }
  };

  const openBuiltinDetail = (skill: BuiltinSkill) => {
    setSelectedBuiltin(skill);
    setDrawerOpen(true);
  };

  // Group built-in skills by category
  const builtinsByCategory = (builtins || []).reduce<Record<string, BuiltinSkill[]>>(
    (acc, skill) => {
      const cat = skill.category || 'Other';
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(skill);
      return acc;
    },
    {},
  );

  const columns = [
    {
      title: t.common.name,
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t.common.type,
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => (
        <Tag color={skillTypeColors[type] || 'default'}>{type}</Tag>
      ),
    },
    {
      title: t.common.version,
      dataIndex: 'version',
      key: 'version',
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
      render: (_: unknown, record: CustomSkill) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          >
            {t.common.edit}
          </Button>
          <Popconfirm
            title={t.skills.deleteTitle}
            description={t.skills.deleteConfirm}
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

  const collapseItems = Object.entries(builtinsByCategory).map(([category, skills]) => ({
    key: category,
    label: (
      <Space>
        <span style={{ color: categoryColors[category] || '#1677ff' }}>
          {categoryIcons[category] || <ThunderboltOutlined />}
        </span>
        <span>{category}</span>
        <Tag>{skills.length}</Tag>
      </Space>
    ),
    children: (
      <Row gutter={[12, 12]}>
        {skills.map((skill) => (
          <Col xs={24} sm={12} md={8} key={skill.name}>
            <Card
              size="small"
              hoverable
              style={{ borderLeft: `3px solid ${categoryColors[category] || '#1677ff'}` }}
              onClick={() => openBuiltinDetail(skill)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Typography.Text strong style={{ fontSize: 13 }}>
                    {skill.name.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                  </Typography.Text>
                  <br />
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {skill.description || skill.type}
                  </Typography.Text>
                </div>
                <Button type="text" size="small" icon={<EyeOutlined />}>
                  {t.skills.viewDefinition}
                </Button>
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    ),
  }));

  return (
    <div>
      {/* Built-in Skills Section */}
      <Typography.Title level={4} style={{ marginBottom: 8 }}>
        {t.skills.builtinSkills}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {t.skills.builtinSkillsDesc}
      </Typography.Paragraph>

      {collapseItems.length > 0 && (
        <Collapse
          defaultActiveKey={Object.keys(builtinsByCategory)}
          size="small"
          items={collapseItems}
          style={{ marginBottom: 24 }}
        />
      )}

      <Divider />

      {/* Custom Skills Section */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>{t.skills.myCustomSkills}</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
          {t.skills.createSkill}
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
          showTotal: (total) => t.skills.totalCount.replace('{count}', String(total)),
        }}
      />

      {/* Create/Edit Modal */}
      <Modal
        title={editingSkill ? t.skills.editSkill : t.skills.createSkill}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={closeModal}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        okText={editingSkill ? t.common.save : t.common.create}
        width={640}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label={t.common.name}
            rules={[{ required: true, message: 'Please enter a skill name' }]}
          >
            <Input placeholder={t.skills.namePlaceholder} />
          </Form.Item>
          <Form.Item
            name="type"
            label={t.common.type}
            rules={[{ required: true, message: 'Please select a skill type' }]}
          >
            <Select placeholder={t.skills.selectType}>
              {SKILL_TYPES.map((st) => (
                <Select.Option key={st} value={st}>
                  {st.charAt(0).toUpperCase() + st.slice(1)}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="definition_md"
            label={t.skills.definition}
            rules={[{ required: true, message: 'Please enter the skill definition' }]}
          >
            <Input.TextArea rows={10} placeholder={t.skills.definitionPlaceholder} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Built-in Skill Detail Drawer */}
      <Drawer
        title={
          selectedBuiltin ? (
            <Space>
              <span style={{ color: categoryColors[selectedBuiltin.category] || '#1677ff' }}>
                {categoryIcons[selectedBuiltin.category] || <ThunderboltOutlined />}
              </span>
              {t.skills.skillDefinition}: {selectedBuiltin.name.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
            </Space>
          ) : t.skills.skillDefinition
        }
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={640}
      >
        {selectedBuiltin && (
          <div>
            <Space style={{ marginBottom: 16 }}>
              <Tag color={categoryColors[selectedBuiltin.category] || '#1677ff'}>
                {selectedBuiltin.category}
              </Tag>
              <Tag>{selectedBuiltin.type}</Tag>
              <Tag>v{selectedBuiltin.version}</Tag>
            </Space>
            {selectedBuiltin.description && (
              <Typography.Paragraph type="secondary">
                {selectedBuiltin.description}
              </Typography.Paragraph>
            )}
            <pre
              style={{
                background: '#f6f8fa',
                padding: 16,
                borderRadius: 8,
                fontSize: 13,
                lineHeight: 1.6,
                overflow: 'auto',
                maxHeight: 'calc(100vh - 220px)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {selectedBuiltin.definition_md}
            </pre>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default SkillsPage;
