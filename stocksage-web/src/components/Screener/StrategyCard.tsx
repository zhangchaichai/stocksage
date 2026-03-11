import React from 'react';
import { Badge, Button, Card, Space, Tag, Tooltip, Typography } from 'antd';
import { ThunderboltOutlined, EyeOutlined, InfoCircleOutlined } from '@ant-design/icons';
import type { StrategyListItem } from '../../types';

const { Text, Paragraph } = Typography;

const RISK_COLORS: Record<string, string> = {
  低: 'green',
  中: 'orange',
  高: 'red',
};

const CATEGORY_COLORS: Record<string, string> = {
  成长类: 'blue',
  技术面: 'purple',
  资金面: 'gold',
  价值类: 'green',
  特色策略: 'volcano',
};

interface StrategyCardProps {
  strategy: StrategyListItem;
  onUse: (id: string) => void;
  onPreview: (id: string) => void;
  loading?: boolean;
}

const StrategyCard: React.FC<StrategyCardProps> = ({ strategy, onUse, onPreview, loading }) => {
  return (
    <Card
      hoverable
      size="small"
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column' }}
      actions={[
        <Button
          key="preview"
          type="text"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => onPreview(strategy.id)}
        >
          预览
        </Button>,
        <Button
          key="use"
          type="primary"
          size="small"
          icon={<ThunderboltOutlined />}
          onClick={() => onUse(strategy.id)}
          loading={loading}
        >
          使用
        </Button>,
      ]}
    >
      {/* Header: icon + name + risk tag */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <Space size={6}>
          <span style={{ fontSize: 20 }}>{strategy.icon}</span>
          <Text strong style={{ fontSize: 14 }}>{strategy.name}</Text>
        </Space>
        <Tag color={RISK_COLORS[strategy.risk_level] || 'default'} style={{ marginLeft: 4 }}>
          {strategy.risk_level}风险
        </Tag>
      </div>

      {/* Description */}
      <Paragraph
        type="secondary"
        style={{ fontSize: 12, marginBottom: 8, flex: 1 }}
        ellipsis={{ rows: 2, tooltip: strategy.description }}
      >
        {strategy.description}
      </Paragraph>

      {/* Meta row */}
      <Space size={4} wrap style={{ marginBottom: 6 }}>
        <Tag color={CATEGORY_COLORS[strategy.category] || 'default'} style={{ fontSize: 11 }}>
          {strategy.category}
        </Tag>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {strategy.suitable_for}
        </Text>
      </Space>

      {/* Sell signal count hint */}
      <Tooltip title={`该策略有 ${strategy.sell_condition_count} 个卖出信号（止损/止盈/技术信号）`}>
        <Text type="secondary" style={{ fontSize: 11, cursor: 'help' }}>
          <InfoCircleOutlined style={{ marginRight: 3 }} />
          {strategy.sell_condition_count} 个卖出信号
        </Text>
      </Tooltip>
    </Card>
  );
};

export default StrategyCard;
