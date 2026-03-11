import React, { useState } from 'react';
import {
  Input,
  Select,
  Card,
  Row,
  Col,
  Tag,
  Button,
  Space,
  Statistic,
  message,
  Typography,
  Spin,
  Empty,
} from 'antd';
import { StarOutlined, StarFilled, ForkOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { marketplaceApi } from '../../api/endpoints';
import type { MarketplaceSkill } from '../../types';
import { useI18n } from '../../i18n';

const { Title } = Typography;

const typeColorMap: Record<string, string> = {
  agent: 'blue',
  data: 'green',
  decision: 'orange',
  expert: 'purple',
  debate: 'red',
};

const MarketplacePage: React.FC = () => {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  const skillTypes = [
    { value: '', label: t.marketplace.allTypes },
    { value: 'agent', label: 'Agent' },
    { value: 'data', label: 'Data' },
    { value: 'decision', label: 'Decision' },
    { value: 'expert', label: 'Expert' },
    { value: 'debate', label: 'Debate' },
  ];

  const { data, isLoading } = useQuery({
    queryKey: ['marketplace', search, typeFilter],
    queryFn: () =>
      marketplaceApi.list(0, 50, search || undefined, typeFilter || undefined),
    select: (res) => res.data,
  });

  const starMutation = useMutation({
    mutationFn: (skillId: string) => marketplaceApi.star(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace'] });
    },
    onError: () => {
      message.error('Failed to toggle star');
    },
  });

  const forkMutation = useMutation({
    mutationFn: (skillId: string) => marketplaceApi.fork(skillId),
    onSuccess: () => {
      message.success(t.marketplace.forkSuccess);
      queryClient.invalidateQueries({ queryKey: ['marketplace'] });
    },
    onError: () => {
      message.error('Failed to fork skill');
    },
  });

  const handleSearch = (value: string) => {
    setSearch(value);
  };

  const handleStar = (skill: MarketplaceSkill) => {
    starMutation.mutate(skill.id);
  };

  const handleFork = (skill: MarketplaceSkill) => {
    forkMutation.mutate(skill.id);
  };

  return (
    <div>
      <Title level={3}>{t.marketplace.title}</Title>

      <Space style={{ marginBottom: 24, width: '100%' }} size="middle">
        <Input.Search
          placeholder={t.marketplace.searchPlaceholder}
          onSearch={handleSearch}
          allowClear
          style={{ width: 320 }}
        />
        <Select
          value={typeFilter}
          onChange={setTypeFilter}
          options={skillTypes}
          style={{ width: 160 }}
        />
      </Space>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
        </div>
      ) : !data?.items?.length ? (
        <Empty description={t.common.noData} />
      ) : (
        <Row gutter={[16, 16]}>
          {data.items.map((skill: MarketplaceSkill) => (
            <Col xs={24} sm={12} md={8} lg={6} key={skill.id}>
              <Card
                hoverable
                title={
                  <Space>
                    <span>{skill.name}</span>
                    <Tag color={typeColorMap[skill.type] || 'default'}>
                      {skill.type}
                    </Tag>
                  </Space>
                }
                extra={
                  <Statistic
                    value={skill.stars_count}
                    prefix={
                      skill.starred_by_me ? (
                        <StarFilled style={{ color: '#faad14' }} />
                      ) : (
                        <StarOutlined />
                      )
                    }
                    valueStyle={{ fontSize: 14 }}
                  />
                }
                actions={[
                  <Button
                    key="star"
                    type="text"
                    icon={
                      skill.starred_by_me ? (
                        <StarFilled style={{ color: '#faad14' }} />
                      ) : (
                        <StarOutlined />
                      )
                    }
                    onClick={() => handleStar(skill)}
                    loading={starMutation.isPending}
                  >
                    {skill.starred_by_me ? t.marketplace.unstar : t.marketplace.star}
                  </Button>,
                  <Button
                    key="fork"
                    type="text"
                    icon={<ForkOutlined />}
                    onClick={() => handleFork(skill)}
                    loading={forkMutation.isPending}
                  >
                    {t.marketplace.fork}
                  </Button>,
                ]}
              >
                <Card.Meta
                  description={
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      <Typography.Text type="secondary">
                        {t.marketplace.by} {skill.owner_username}
                      </Typography.Text>
                      {skill.tags?.length > 0 && (
                        <Space size={[0, 4]} wrap>
                          {skill.tags.map((tag) => (
                            <Tag key={tag}>{tag}</Tag>
                          ))}
                        </Space>
                      )}
                      {skill.forked_from && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {t.marketplace.forkedFrom} {skill.forked_from}
                        </Typography.Text>
                      )}
                    </Space>
                  }
                />
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
};

export default MarketplacePage;
