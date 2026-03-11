import React from 'react';
import {
  Card,
  Row,
  Col,
  Button,
  Typography,
  Tag,
  message,
  Tooltip,
  Spin,
  Empty,
  Space,
  Divider,
} from 'antd';
import {
  CopyOutlined,
  PlusOutlined,
  ShareAltOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { workflowApi, sharingApi } from '../../api/endpoints';
import type { WorkflowTemplate } from '../../types';
import { useI18n } from '../../i18n';

const { Title, Text, Paragraph } = Typography;

const TemplateGalleryPage: React.FC = () => {
  const { t } = useI18n();
  const navigate = useNavigate();

  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['workflow-templates'],
    queryFn: () => workflowApi.templates(),
    select: (res) => res.data,
  });

  const { data: publicWorkflows, isLoading: publicLoading } = useQuery({
    queryKey: ['public-workflows'],
    queryFn: () => workflowApi.list(0, 50),
    select: (res) => res.data.items.filter((w) => w.is_public),
  });

  const handleUseTemplate = (template: WorkflowTemplate) => {
    navigate('/workflows/new', {
      state: { template },
    });
  };

  const handleCopyShareLink = async (workflowId: string) => {
    try {
      const res = await sharingApi.share(workflowId);
      await navigator.clipboard.writeText(res.data.share_url);
      message.success(t.gallery.shareLinkCopied);
    } catch {
      message.error('Failed to generate share link');
    }
  };

  return (
    <div>
      <Title level={3}>{t.gallery.title}</Title>
      <Paragraph type="secondary">
        {t.gallery.subtitle}
      </Paragraph>

      {/* Templates Section */}
      <Title level={4}>{t.gallery.workflowTemplates}</Title>

      {templatesLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
        </div>
      ) : !templates?.length ? (
        <Empty description={t.gallery.noTemplates} />
      ) : (
        <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
          {templates.map((template: WorkflowTemplate, index: number) => (
            <Col xs={24} sm={12} md={8} lg={6} key={index}>
              <Card
                hoverable
                title={template.name}
                extra={
                  <Tooltip title={t.gallery.useTemplate}>
                    <Button
                      type="primary"
                      size="small"
                      icon={<PlusOutlined />}
                      onClick={() => handleUseTemplate(template)}
                    >
                      {t.gallery.useTemplate}
                    </Button>
                  </Tooltip>
                }
              >
                <Paragraph
                  type="secondary"
                  ellipsis={{ rows: 2 }}
                  style={{ minHeight: 44 }}
                >
                  {template.description || t.gallery.noDescription}
                </Paragraph>
                <Space size="middle">
                  <Tag icon={<NodeIndexOutlined />} color="blue">
                    {template.definition.nodes?.length ?? 0} {t.gallery.nodes}
                  </Tag>
                  <Tag color="geekblue">
                    {template.definition.edges?.length ?? 0} {t.gallery.edges}
                  </Tag>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Divider />

      {/* Shared Workflows Section */}
      <Title level={4}>
        <Space>
          <ShareAltOutlined />
          {t.gallery.myPublicWorkflows}
        </Space>
      </Title>

      {publicLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
        </div>
      ) : !publicWorkflows?.length ? (
        <Empty description={t.gallery.noPublicWorkflows} />
      ) : (
        <Row gutter={[16, 16]}>
          {publicWorkflows.map((workflow) => (
            <Col xs={24} sm={12} md={8} lg={6} key={workflow.id}>
              <Card
                hoverable
                title={workflow.name}
                extra={
                  <Tooltip title={t.gallery.copyShareLink}>
                    <Button
                      type="text"
                      icon={<CopyOutlined />}
                      onClick={() => handleCopyShareLink(workflow.id)}
                    />
                  </Tooltip>
                }
              >
                <Paragraph
                  type="secondary"
                  ellipsis={{ rows: 2 }}
                  style={{ minHeight: 44 }}
                >
                  {workflow.description || t.gallery.noDescription}
                </Paragraph>
                <Space size="middle">
                  <Tag color="blue">
                    {workflow.definition.nodes?.length ?? 0} {t.gallery.nodes}
                  </Tag>
                  <Tag color="geekblue">
                    {workflow.definition.edges?.length ?? 0} {t.gallery.edges}
                  </Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    v{workflow.version}
                  </Text>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
};

export default TemplateGalleryPage;
