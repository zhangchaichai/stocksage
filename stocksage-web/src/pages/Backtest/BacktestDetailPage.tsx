import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Col,
  Descriptions,
  List,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from 'antd';
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { backtestApi } from '../../api/endpoints';
import type { BacktestResult, BacktestDiagnosis, DealerSignal } from '../../types';
import { useI18n } from '../../i18n';

const directionColors: Record<string, string> = {
  up: 'green',
  down: 'red',
  neutral: 'blue',
};

const verdictColors: Record<string, string> = {
  correct: 'green',
  partially_correct: 'orange',
  incorrect: 'red',
};

const priorityColors: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
};

const wyckoffColors: Record<string, string> = {
  accumulation: 'green',
  markup: 'cyan',
  distribution: 'orange',
  markdown: 'red',
};

const BacktestDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useI18n();

  const { data: result, isLoading } = useQuery({
    queryKey: ['backtest-result', id],
    queryFn: () => backtestApi.getResult(id!).then((r) => r.data),
    enabled: !!id,
  });

  const directionLabel = (dir: string): string => {
    if (dir === 'up') return t.backtest.up;
    if (dir === 'down') return t.backtest.down;
    return t.backtest.neutral;
  };

  const verdictLabel = (verdict: string): string => {
    if (verdict === 'correct') return t.backtest.correct;
    if (verdict === 'partially_correct') return t.backtest.partiallyCorrect;
    return t.backtest.incorrect;
  };

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!result) {
    return <Typography.Text type="danger">{t.backtest.notFound}</Typography.Text>;
  }

  const diagnosis: BacktestDiagnosis | null = result.diagnosis;
  const priceChangeColor = result.price_change_pct >= 0 ? 'green' : 'red';

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
          >
            {t.common.back}
          </Button>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {t.backtest.detail}: {result.symbol}
          </Typography.Title>
        </Space>
      </div>

      {/* Basic Info Card */}
      <Card style={{ marginBottom: 24 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label={t.runs.symbol}>{result.symbol}</Descriptions.Item>
          <Descriptions.Item label={t.backtest.periodDays}>{result.period_days}</Descriptions.Item>
          <Descriptions.Item label={`${t.backtest.actionPrice} (\u00a5)`}>
            {result.action_price.toFixed(2)}
          </Descriptions.Item>
          <Descriptions.Item label={`${t.backtest.currentPrice} (\u00a5)`}>
            {result.current_price.toFixed(2)}
          </Descriptions.Item>
          <Descriptions.Item label={t.backtest.priceChange}>
            <Typography.Text style={{ color: priceChangeColor }}>
              {result.price_change_pct >= 0 ? '+' : ''}
              {result.price_change_pct.toFixed(2)}%
            </Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label={t.backtest.maxGain}>
            {result.max_gain_pct != null ? `${result.max_gain_pct.toFixed(2)}%` : 'N/A'}
          </Descriptions.Item>
          <Descriptions.Item label={t.backtest.maxDrawdown}>
            {result.max_drawdown_pct != null ? `${result.max_drawdown_pct.toFixed(2)}%` : 'N/A'}
          </Descriptions.Item>
          <Descriptions.Item label={t.backtest.predictedDirection}>
            <Tag color={directionColors[result.predicted_direction] || 'blue'}>
              {directionLabel(result.predicted_direction)}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t.backtest.actualDirection}>
            <Tag color={directionColors[result.actual_direction] || 'blue'}>
              {directionLabel(result.actual_direction)}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t.backtest.directionCorrect}>
            {result.direction_correct ? (
              <Tag color="green" icon={<CheckCircleOutlined />}>{t.backtest.correct}</Tag>
            ) : (
              <Tag color="red" icon={<CloseCircleOutlined />}>{t.backtest.incorrect}</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t.backtest.backtestDate}>
            {new Date(result.backtest_date).toLocaleDateString()}
          </Descriptions.Item>
          <Descriptions.Item label={t.common.created}>
            {new Date(result.created_at).toLocaleString()}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Price Comparison Cards */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title={t.backtest.actionPrice}
              value={result.action_price}
              precision={2}
              prefix="\u00a5"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t.backtest.currentPrice}
              value={result.current_price}
              precision={2}
              prefix="\u00a5"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t.backtest.priceChange}
              value={result.price_change_pct}
              precision={2}
              suffix="%"
              valueStyle={{ color: priceChangeColor }}
              prefix={result.price_change_pct >= 0 ? '+' : ''}
            />
          </Card>
        </Col>
      </Row>

      {/* Risk Indicators (Phase 4) */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title={t.backtest.sharpeRatio}
              value={result.sharpe_ratio ?? 'N/A'}
              precision={result.sharpe_ratio != null ? 4 : undefined}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t.backtest.sortinoRatio}
              value={result.sortino_ratio ?? 'N/A'}
              precision={result.sortino_ratio != null ? 4 : undefined}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t.backtest.var95}
              value={result.var_95 ?? 'N/A'}
              precision={result.var_95 != null ? 4 : undefined}
              suffix={result.var_95 != null ? '%' : undefined}
              valueStyle={result.var_95 != null ? { color: '#ff4d4f' } : undefined}
            />
          </Card>
        </Col>
      </Row>

      {/* Wyckoff Phase & Dealer Signals (Phase 4) */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card title={t.backtest.wyckoffPhase} size="small">
            {result.wyckoff_phase_at_action ? (
              <Tag color={wyckoffColors[result.wyckoff_phase_at_action] || 'blue'} style={{ fontSize: 14, padding: '4px 12px' }}>
                {(t.backtest as Record<string, string>)[result.wyckoff_phase_at_action] || result.wyckoff_phase_at_action}
              </Tag>
            ) : (
              <Typography.Text type="secondary">N/A</Typography.Text>
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card title={t.backtest.dealerSignals} size="small">
            {result.dealer_signals_at_action && result.dealer_signals_at_action.length > 0 ? (
              <List
                size="small"
                dataSource={result.dealer_signals_at_action}
                renderItem={(signal: DealerSignal) => (
                  <List.Item>
                    <Space>
                      <Tag color={signal.confidence > 0.7 ? 'red' : signal.confidence > 0.4 ? 'orange' : 'blue'}>
                        {signal.type}
                      </Tag>
                      <Typography.Text type="secondary">
                        ({(signal.confidence * 100).toFixed(0)}%)
                      </Typography.Text>
                      <Typography.Text>{signal.description}</Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Typography.Text type="secondary">{t.backtest.noSignals}</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>

      {/* Diagnosis Report Card */}
      {diagnosis ? (
        <Card title={t.backtest.diagnosis} style={{ marginBottom: 24 }}>
          <Descriptions column={1} bordered size="small" style={{ marginBottom: 24 }}>
            <Descriptions.Item label={t.backtest.accuracyVerdict}>
              <Tag color={verdictColors[diagnosis.accuracy_verdict] || 'blue'}>
                {verdictLabel(diagnosis.accuracy_verdict)}
              </Tag>
            </Descriptions.Item>
          </Descriptions>

          <div style={{ marginBottom: 24 }}>
            <Typography.Text strong>{t.backtest.score}</Typography.Text>
            <Progress
              percent={diagnosis.score}
              status={diagnosis.score >= 70 ? 'success' : diagnosis.score >= 40 ? 'normal' : 'exception'}
              style={{ marginTop: 8 }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <Typography.Text strong>{t.backtest.rootCause}</Typography.Text>
            <Typography.Paragraph style={{ marginTop: 8 }}>
              {diagnosis.root_cause}
            </Typography.Paragraph>
          </div>

          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={12}>
              <Card
                size="small"
                title={t.backtest.correctInsights}
                type="inner"
              >
                <List
                  size="small"
                  dataSource={diagnosis.correct_insights}
                  renderItem={(item) => (
                    <List.Item>
                      <Typography.Text>
                        <CheckCircleOutlined style={{ color: 'green', marginRight: 8 }} />
                        {item}
                      </Typography.Text>
                    </List.Item>
                  )}
                  locale={{ emptyText: t.common.noData }}
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card
                size="small"
                title={t.backtest.missedFactors}
                type="inner"
              >
                <List
                  size="small"
                  dataSource={diagnosis.missed_factors}
                  renderItem={(item) => (
                    <List.Item>
                      <Typography.Text>
                        <CloseCircleOutlined style={{ color: 'red', marginRight: 8 }} />
                        {item}
                      </Typography.Text>
                    </List.Item>
                  )}
                  locale={{ emptyText: t.common.noData }}
                />
              </Card>
            </Col>
          </Row>

          {diagnosis.improvement_suggestions.length > 0 && (
            <Card
              size="small"
              title={t.backtest.improvementSuggestions}
              type="inner"
            >
              <List
                size="small"
                dataSource={diagnosis.improvement_suggestions}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space>
                          <Tag>{item.type}</Tag>
                          <Typography.Text strong>{item.target}</Typography.Text>
                          <Tag color={priorityColors[item.priority] || 'blue'}>
                            {item.priority}
                          </Tag>
                        </Space>
                      }
                      description={item.suggestion}
                    />
                  </List.Item>
                )}
              />
            </Card>
          )}
        </Card>
      ) : (
        <Card style={{ marginBottom: 24 }}>
          <Typography.Text type="secondary">
            {t.backtest.noDiagnosis}
          </Typography.Text>
        </Card>
      )}
    </div>
  );
};

export default BacktestDetailPage;
