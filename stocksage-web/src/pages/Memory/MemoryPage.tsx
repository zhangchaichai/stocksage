import React, { useState } from 'react';
import {
  Card,
  Table,
  Row,
  Col,
  Tabs,
  Tag,
  Typography,
  Spin,
  Empty,
  Input,
  List,
  Descriptions,
  Space,
  Button,
  Modal,
  Form,
  message,
  Timeline,
} from 'antd';
import {
  FolderOutlined,
  SearchOutlined,
  SettingOutlined,
  PlusOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { memoryApi } from '../../api/endpoints';
import type { MemoryCategory, MemoryItem, StockMemory, TimelineEntry } from '../../types';
import { useI18n } from '../../i18n';

const memoryTypeColors: Record<string, string> = {
  profile: 'blue',
  analysis_event: 'green',
  price_anchor: 'orange',
  strategy_review: 'purple',
  preference: 'cyan',
  action: 'magenta',
};

const MemoryPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [form] = Form.useForm();

  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [stockSymbol, setStockSymbol] = useState('');
  const [timelineSymbol, setTimelineSymbol] = useState('');
  const [prefModalOpen, setPrefModalOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<MemoryItem | null>(null);

  // ---- Categories tab ----
  const { data: categories, isLoading: loadingCategories } = useQuery({
    queryKey: ['memory-categories'],
    queryFn: () => memoryApi.listCategories().then((r) => r.data),
  });

  const { data: categoryItems, isLoading: loadingCategoryItems } = useQuery({
    queryKey: ['memory-category-items', selectedCategory],
    queryFn: () => memoryApi.getCategoryItems(selectedCategory!, 0, 50).then((r) => r.data),
    enabled: !!selectedCategory,
  });

  // ---- Stock Memory tab ----
  const { data: stockMemory, isLoading: loadingStockMemory } = useQuery({
    queryKey: ['memory-stock', stockSymbol],
    queryFn: () => memoryApi.getStockMemory(stockSymbol).then((r) => r.data),
    enabled: !!stockSymbol,
  });

  // ---- Timeline tab ----
  const { data: timelineData, isLoading: loadingTimeline } = useQuery({
    queryKey: ['memory-timeline', timelineSymbol],
    queryFn: () => memoryApi.getStockTimeline(timelineSymbol).then((r) => r.data),
    enabled: !!timelineSymbol,
  });

  // ---- Preferences tab ----
  const { data: preferences, isLoading: loadingPreferences } = useQuery({
    queryKey: ['memory-preferences'],
    queryFn: () => memoryApi.getPreferences().then((r) => r.data),
  });

  const setPrefMutation = useMutation({
    mutationFn: (values: { key: string; value: string }) =>
      memoryApi.setPreference(values),
    onSuccess: () => {
      message.success(t.memory.preferenceSaved);
      queryClient.invalidateQueries({ queryKey: ['memory-preferences'] });
      setPrefModalOpen(false);
      form.resetFields();
    },
    onError: (err: any) => {
      message.error(err.response?.data?.detail || t.memory.preferenceFailed);
    },
  });

  // ---- Category items table columns ----
  const categoryItemColumns = [
    {
      title: t.common.type,
      dataIndex: 'memory_type',
      key: 'memory_type',
      width: 140,
      render: (type: string) => (
        <Tag color={memoryTypeColors[type] || 'default'}>{type}</Tag>
      ),
    },
    {
      title: t.memory.content,
      dataIndex: 'content',
      key: 'content',
      render: (content: string) =>
        content.length > 100 ? content.slice(0, 100) + '...' : content,
    },
    {
      title: t.memory.importance,
      dataIndex: 'importance_weight',
      key: 'importance_weight',
      width: 100,
      render: (val: number) => val.toFixed(2),
    },
    {
      title: t.common.created,
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => new Date(v).toLocaleString(),
    },
  ];

  // ---- Preferences table columns ----
  const preferenceColumns = [
    {
      title: t.memory.preferenceKey,
      key: 'key',
      render: (_: unknown, record: MemoryItem) => {
        if (record.structured_data && record.structured_data.key) {
          return String(record.structured_data.key);
        }
        return record.content.split(':')[0] || record.content;
      },
    },
    {
      title: t.memory.preferenceValue,
      key: 'value',
      render: (_: unknown, record: MemoryItem) => {
        if (record.structured_data && record.structured_data.value) {
          return String(record.structured_data.value);
        }
        const parts = record.content.split(':');
        return parts.length > 1 ? parts.slice(1).join(':').trim() : record.content;
      },
    },
    {
      title: t.common.created,
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => new Date(v).toLocaleString(),
    },
  ];

  // ---- Handle preference form submit ----
  const handlePrefSubmit = async () => {
    try {
      const values = await form.validateFields();
      setPrefMutation.mutate(values);
    } catch {
      // validation errors handled by form
    }
  };

  // ---- Render stock memory section ----
  const renderStockMemory = (data: StockMemory) => (
    <div style={{ marginTop: 16 }}>
      <Row gutter={[16, 16]}>
        {data.profile && (
          <Col span={24}>
            <Card title={t.memory.profile} size="small">
              <Typography.Paragraph>{data.profile.content}</Typography.Paragraph>
            </Card>
          </Col>
        )}
        <Col xs={24} md={12}>
          <Card title={t.memory.analysisEvents} size="small">
            {data.analysis_events.length === 0 ? (
              <Empty description={t.common.noData} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={data.analysis_events}
                renderItem={(item: MemoryItem) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {item.happened_at
                            ? new Date(item.happened_at).toLocaleDateString()
                            : new Date(item.created_at).toLocaleDateString()}
                        </Typography.Text>
                      }
                      description={item.content}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title={t.memory.priceAnchors} size="small">
            {data.price_anchors.length === 0 ? (
              <Empty description={t.common.noData} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={data.price_anchors}
                renderItem={(item: MemoryItem) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {item.happened_at
                            ? new Date(item.happened_at).toLocaleDateString()
                            : new Date(item.created_at).toLocaleDateString()}
                        </Typography.Text>
                      }
                      description={item.content}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col span={24}>
          <Card title={t.memory.strategyReviews} size="small">
            {data.strategy_reviews.length === 0 ? (
              <Empty description={t.common.noData} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={data.strategy_reviews}
                renderItem={(item: MemoryItem) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {item.happened_at
                            ? new Date(item.happened_at).toLocaleDateString()
                            : new Date(item.created_at).toLocaleDateString()}
                        </Typography.Text>
                      }
                      description={item.content}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );

  // ---- Tab items ----
  const tabItems = [
    {
      key: 'categories',
      label: (
        <span>
          <FolderOutlined /> {t.memory.categories}
        </span>
      ),
      children: (
        <div>
          {loadingCategories ? (
            <div style={{ textAlign: 'center', padding: 48 }}>
              <Spin size="large" />
            </div>
          ) : !categories || categories.length === 0 ? (
            <Empty description={t.memory.noMemory} />
          ) : (
            <>
              <Row gutter={[16, 16]}>
                {categories.map((cat: MemoryCategory) => (
                  <Col xs={24} sm={12} md={8} key={cat.id}>
                    <Card
                      hoverable
                      size="small"
                      style={{
                        borderLeft: selectedCategory === cat.name
                          ? '3px solid #1677ff'
                          : '3px solid transparent',
                      }}
                      onClick={() => setSelectedCategory(cat.name)}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Typography.Text strong>{cat.name}</Typography.Text>
                          <br />
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {cat.description}
                          </Typography.Text>
                        </div>
                        <Tag color="blue">{cat.item_count}</Tag>
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>

              {selectedCategory && (
                <div style={{ marginTop: 24 }}>
                  <Typography.Title level={5}>
                    {selectedCategory} - {t.memory.items}
                  </Typography.Title>
                  <Table
                    columns={categoryItemColumns}
                    dataSource={categoryItems?.items || []}
                    rowKey="id"
                    loading={loadingCategoryItems}
                    size="small"
                    pagination={{
                      total: categoryItems?.total || 0,
                      pageSize: 50,
                      showSizeChanger: false,
                    }}
                    onRow={(record: MemoryItem) => ({
                      onClick: () => setDetailItem(record),
                      style: { cursor: 'pointer' },
                    })}
                  />
                </div>
              )}
            </>
          )}
        </div>
      ),
    },
    {
      key: 'stock-memory',
      label: (
        <span>
          <SearchOutlined /> {t.memory.stockMemory}
        </span>
      ),
      children: (
        <div>
          <Input.Search
            placeholder={t.memory.symbolPlaceholder}
            enterButton={t.common.search}
            style={{ maxWidth: 400, marginBottom: 16 }}
            onSearch={(value) => setStockSymbol(value.trim())}
            allowClear
          />
          {!stockSymbol ? (
            <Empty description={t.memory.noMemory} />
          ) : loadingStockMemory ? (
            <div style={{ textAlign: 'center', padding: 48 }}>
              <Spin size="large" />
            </div>
          ) : !stockMemory ? (
            <Empty description={t.common.noData} />
          ) : (
            renderStockMemory(stockMemory)
          )}
        </div>
      ),
    },
    {
      key: 'timeline',
      label: (
        <span>
          <ClockCircleOutlined /> {t.memory.timeline}
        </span>
      ),
      children: (
        <div>
          <Input.Search
            placeholder={t.memory.symbolPlaceholder}
            enterButton={t.common.search}
            style={{ maxWidth: 400, marginBottom: 16 }}
            onSearch={(value) => setTimelineSymbol(value.trim())}
            allowClear
          />
          {!timelineSymbol ? (
            <Empty description={t.memory.noMemory} />
          ) : loadingTimeline ? (
            <div style={{ textAlign: 'center', padding: 48 }}>
              <Spin size="large" />
            </div>
          ) : !timelineData || timelineData.length === 0 ? (
            <Empty description={t.common.noData} />
          ) : (
            <Timeline
              items={timelineData.map((entry: TimelineEntry, idx: number) => ({
                key: idx,
                children: (
                  <div>
                    <Space>
                      <Typography.Text strong>
                        {new Date(entry.date).toLocaleDateString()}
                      </Typography.Text>
                      <Tag color={memoryTypeColors[entry.type] || 'default'}>
                        {entry.type}
                      </Tag>
                    </Space>
                    <Typography.Paragraph
                      style={{ marginTop: 4, marginBottom: 0 }}
                      type="secondary"
                    >
                      {entry.content}
                    </Typography.Paragraph>
                  </div>
                ),
              }))}
            />
          )}
        </div>
      ),
    },
    {
      key: 'preferences',
      label: (
        <span>
          <SettingOutlined /> {t.memory.preferences}
        </span>
      ),
      children: (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setPrefModalOpen(true)}
            >
              {t.memory.setPreference}
            </Button>
          </div>
          {loadingPreferences ? (
            <div style={{ textAlign: 'center', padding: 48 }}>
              <Spin size="large" />
            </div>
          ) : !preferences || preferences.length === 0 ? (
            <Empty description={t.memory.noMemory} />
          ) : (
            <Table
              columns={preferenceColumns}
              dataSource={preferences}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 20 }}
            />
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>
        {t.memory.title}
      </Typography.Title>

      <Tabs defaultActiveKey="categories" items={tabItems} />

      {/* Memory Item Detail Modal */}
      <Modal
        title={detailItem?.memory_type || t.memory.detail}
        open={!!detailItem}
        onCancel={() => setDetailItem(null)}
        footer={null}
        width={640}
      >
        {detailItem && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t.common.type}>
              <Tag color={memoryTypeColors[detailItem.memory_type] || 'default'}>
                {detailItem.memory_type}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t.memory.content}>
              {detailItem.content}
            </Descriptions.Item>
            <Descriptions.Item label={t.memory.importance}>
              {detailItem.importance_weight.toFixed(2)}
            </Descriptions.Item>
            <Descriptions.Item label={t.memory.accessCount}>
              {detailItem.access_count}
            </Descriptions.Item>
            <Descriptions.Item label={t.memory.categories}>
              <Space>
                {detailItem.categories.map((c) => (
                  <Tag key={c}>{c}</Tag>
                ))}
              </Space>
            </Descriptions.Item>
            {detailItem.happened_at && (
              <Descriptions.Item label={t.memory.happenedAt}>
                {new Date(detailItem.happened_at).toLocaleString()}
              </Descriptions.Item>
            )}
            <Descriptions.Item label={t.common.created}>
              {new Date(detailItem.created_at).toLocaleString()}
            </Descriptions.Item>
            {detailItem.structured_data && (
              <Descriptions.Item label={t.memory.structuredData}>
                <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(detailItem.structured_data, null, 2)}
                </pre>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      {/* Set Preference Modal */}
      <Modal
        title={t.memory.setPreference}
        open={prefModalOpen}
        onOk={handlePrefSubmit}
        onCancel={() => {
          setPrefModalOpen(false);
          form.resetFields();
        }}
        confirmLoading={setPrefMutation.isPending}
        okText={t.common.save}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="key"
            label={t.memory.preferenceKey}
            rules={[{ required: true, message: t.memory.enterKey }]}
          >
            <Input placeholder={t.memory.preferenceKey} />
          </Form.Item>
          <Form.Item
            name="value"
            label={t.memory.preferenceValue}
            rules={[{ required: true, message: t.memory.enterValue }]}
          >
            <Input.TextArea rows={4} placeholder={t.memory.preferenceValue} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default MemoryPage;
