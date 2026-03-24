import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Button,
  Card,
  Col,
  Collapse,
  DatePicker,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Row,
  Select,
  Spin,
  Statistic,
  Table,
  Tag,
  Timeline,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  PlusOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { runApi, reportApi, portfolioApi } from '../../api/endpoints';
import type { RunProgressEvent, WorkflowRun } from '../../types';
import { useI18n } from '../../i18n';
import StreamPanel from './StreamPanel';

const { Text, Title, Paragraph } = Typography;

// ── Status helpers ────────────────────────────────────────────────────────────

const statusColors: Record<string, string> = {
  queued: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
};

const statusIcons: Record<string, React.ReactNode> = {
  queued: <ClockCircleOutlined />,
  running: <SyncOutlined spin />,
  completed: <CheckCircleOutlined />,
  failed: <CloseCircleOutlined />,
  cancelled: <CloseCircleOutlined />,
};

const timelineItemColor = (event: string): string => {
  if (event === 'error' || event === 'failed') return 'red';
  if (event === 'completed' || event === 'done') return 'green';
  if (event === 'started' || event === 'running') return 'blue';
  return 'gray';
};

// ── Decision result panel ─────────────────────────────────────────────────────

const RECOMMENDATION_COLORS: Record<string, string> = {
  BUY: '#52c41a',
  SELL: '#ff4d4f',
  HOLD: '#faad14',
  WATCH: '#1677ff',
};

const DIMENSION_LABELS: Record<string, string> = {
  technical:    '技术面',
  fundamental:  '基本面',
  risk:         '风险',
  sentiment:    '情绪面',
  news:         '新闻',
  fund_flow:    '资金流',
};

interface FinalDecision {
  recommendation?: string;
  confidence?: number;
  weighted_score?: number;
  core_logic?: string;
  risk_warning?: string;
  action_strategy?: string;
  bull_factors?: string[];
  bear_factors?: string[];
  key_watch_points?: string[];
  dimension_scores?: Record<string, number>;
  blind_spot_assessment?: any[];
}

const DecisionPanel: React.FC<{ result: Record<string, any> }> = ({ result }) => {
  const decision: FinalDecision = result.final_decision || result.decision || {};
  const dimScores: Record<string, number> =
    result.dimension_scores || decision.dimension_scores || {};
  const llmTraces: Record<string, string> = result.llm_traces || {};

  if (!decision.recommendation && !decision.core_logic) {
    return (
      <Text type="secondary">分析结果格式不符，请下载 Markdown 报告查看完整内容。</Text>
    );
  }

  const rec = (decision.recommendation || '').toUpperCase();
  const recColor = RECOMMENDATION_COLORS[rec] || '#666';
  // confidence: 0.0-1.0 from backend → display as 0-100%
  const confidence = typeof decision.confidence === 'number'
    ? Math.round(decision.confidence * 100)
    : null;
  const weightedScore = typeof decision.weighted_score === 'number'
    ? decision.weighted_score
    : null;

  return (
    <div>
      {/* ── 核心决策 ─────────────────────────────────────────────── */}
      <Row gutter={24} align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <div style={{
            display: 'inline-block',
            padding: '8px 28px',
            borderRadius: 8,
            background: recColor,
            color: '#fff',
            fontSize: 28,
            fontWeight: 700,
            letterSpacing: 4,
          }}>
            {rec || '—'}
          </div>
        </Col>
        {confidence !== null && (
          <Col>
            <Statistic
              title="置信度"
              value={confidence}
              suffix="%"
              valueStyle={{ color: confidence >= 70 ? '#52c41a' : confidence >= 50 ? '#faad14' : '#ff4d4f' }}
            />
          </Col>
        )}
        {weightedScore !== null && (
          <Col>
            <Statistic
              title="综合评分"
              value={weightedScore.toFixed(1)}
              suffix="/ ±10"
              valueStyle={{ color: weightedScore >= 3 ? '#52c41a' : weightedScore >= 0 ? '#faad14' : '#ff4d4f' }}
            />
          </Col>
        )}
      </Row>

      {/* ── 六维评分 ─────────────────────────────────────────────── */}
      {Object.keys(dimScores).length > 0 && (
        <Card size="small" title="多维评分（-10 至 +10）" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 8]}>
            {Object.entries(dimScores).map(([k, v]) => {
              const score = Number(v);
              // Convert -10~+10 to 0~100% for Progress display
              const pct = Math.round((score + 10) / 20 * 100);
              const color = score >= 3 ? '#52c41a' : score >= 0 ? '#faad14' : '#ff4d4f';
              return (
                <Col key={k} xs={12} sm={8} md={6} lg={4}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>
                      {DIMENSION_LABELS[k] || k}
                    </div>
                    <Progress
                      type="circle"
                      size={64}
                      percent={pct}
                      format={() => score > 0 ? `+${score.toFixed(1)}` : score.toFixed(1)}
                      strokeColor={color}
                    />
                  </div>
                </Col>
              );
            })}
          </Row>
        </Card>
      )}

      {/* ── 核心逻辑 / 操作策略 / 风险提示 ──────────────────────── */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {decision.core_logic && (
          <Col xs={24} md={12}>
            <Card size="small" title="核心逻辑" style={{ height: '100%' }}>
              <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{decision.core_logic}</Paragraph>
            </Card>
          </Col>
        )}
        {decision.action_strategy && (
          <Col xs={24} md={12}>
            <Card size="small" title="操作策略" style={{ height: '100%' }}>
              <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{decision.action_strategy}</Paragraph>
            </Card>
          </Col>
        )}
      </Row>

      {decision.risk_warning && (
        <Card size="small" title="风险提示" style={{ marginBottom: 16, borderColor: '#ff4d4f' }}>
          <Paragraph style={{ margin: 0, color: '#ff4d4f', whiteSpace: 'pre-wrap' }}>{decision.risk_warning}</Paragraph>
        </Card>
      )}

      {decision.key_watch_points && decision.key_watch_points.length > 0 && (
        <Card size="small" title="关键观察指标" style={{ marginBottom: 16 }}>
          <Row gutter={[8, 4]}>
            {decision.key_watch_points.map((p: string, i: number) => (
              <Col key={i}><Tag color="blue">{p}</Tag></Col>
            ))}
          </Row>
        </Card>
      )}

      {/* ── 多空因素 ─────────────────────────────────────────────── */}
      {((decision.bull_factors?.length || 0) + (decision.bear_factors?.length || 0)) > 0 && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {decision.bull_factors && decision.bull_factors.length > 0 && (
            <Col xs={24} md={12}>
              <Card size="small" title={<span style={{ color: '#52c41a' }}>多方因素</span>}>
                <ul style={{ paddingLeft: 16, margin: 0 }}>
                  {decision.bull_factors.map((f: string, i: number) => (
                    <li key={i}><Text style={{ fontSize: 13 }}>{f}</Text></li>
                  ))}
                </ul>
              </Card>
            </Col>
          )}
          {decision.bear_factors && decision.bear_factors.length > 0 && (
            <Col xs={24} md={12}>
              <Card size="small" title={<span style={{ color: '#ff4d4f' }}>空方因素</span>}>
                <ul style={{ paddingLeft: 16, margin: 0 }}>
                  {decision.bear_factors.map((f: string, i: number) => (
                    <li key={i}><Text style={{ fontSize: 13 }}>{f}</Text></li>
                  ))}
                </ul>
              </Card>
            </Col>
          )}
        </Row>
      )}

      {/* ── 数据获取状态 ─────────────────────────────────────────── */}
      {result.data_status && typeof result.data_status === 'object' && (
        <Card size="small" title="数据获取状态" style={{ marginBottom: 16 }}>
          <Table
            size="small"
            pagination={false}
            dataSource={Object.entries(result.data_status).map(([k, v]: [string, any]) => ({
              key: k,
              source: k,
              status: v?.success ?? v,
              rows: v?.rows ?? '-',
            }))}
            columns={[
              { title: '数据源', dataIndex: 'source', key: 'source', width: 160 },
              {
                title: '状态',
                dataIndex: 'status',
                key: 'status',
                width: 80,
                render: (v: any) => (
                  <Tag color={v === true || v === 'ok' ? 'green' : 'red'}>
                    {v === true || v === 'ok' ? '成功' : '失败'}
                  </Tag>
                ),
              },
              { title: '数据行数', dataIndex: 'rows', key: 'rows' },
            ]}
          />
        </Card>
      )}

      {/* ── LLM 分析详情（可折叠） ───────────────────────────────── */}
      {Object.keys(llmTraces).length > 0 && (
        <Collapse
          size="small"
          items={Object.entries(llmTraces).map(([skill, trace]) => ({
            key: skill,
            label: <Text style={{ fontSize: 13 }}>{skill}</Text>,
            children: (
              <pre style={{
                maxHeight: 300,
                overflow: 'auto',
                fontSize: 12,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                background: '#fafafa',
                padding: 8,
                margin: 0,
              }}>
                {typeof trace === 'string' ? trace : JSON.stringify(trace, null, 2)}
              </pre>
            ),
          }))}
        />
      )}
    </div>
  );
};

// ── Main component ────────────────────────────────────────────────────────────

const RunDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const [events, setEvents] = useState<RunProgressEvent[]>([]);
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [form] = Form.useForm();
  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  const { data: run, isLoading } = useQuery({
    queryKey: ['runs', id],
    queryFn: () => runApi.get(id!).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'queued' || status === 'running') return 3000;
      return false;
    },
  });

  // WebSocket — connect through Vite proxy (/api path, same origin)
  useEffect(() => {
    if (!id) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use same host:port as the page — Vite proxy forwards /api/ws to backend
    const wsUrl = `${protocol}//${window.location.host}/api/runs/${id}/progress`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const parsed: RunProgressEvent = JSON.parse(event.data);
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onerror = () => {
      // Silently ignore — run may already be completed
    };

    ws.onclose = () => {
      wsRef.current = null;
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [id]);

  const handleDownloadReport = async () => {
    if (!id) return;
    try {
      const { data: markdown } = await reportApi.markdown(id);
      const blob = new Blob([markdown], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report-${run?.symbol || id}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '下载报告失败');
    }
  };

  const createActionMutation = useMutation({
    mutationFn: (values: any) =>
      portfolioApi.recordAction({
        ...values,
        action_date: values.action_date.format('YYYY-MM-DD'),
        run_id: id,
      }),
    onSuccess: () => {
      message.success(t.portfolio.actionCreated);
      setActionModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['portfolio-actions'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio-summary'] });
    },
  });

  const handleOpenActionModal = () => {
    form.setFieldsValue({
      symbol: run?.symbol,
      stock_name: run?.stock_name,
    });
    setActionModalOpen(true);
  };

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 64 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (!run) {
    return <Typography.Text type="danger">{t.runs.notFound}</Typography.Text>;
  }

  const isTerminal = run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled';
  const actionTypeColors: Record<string, string> = { buy: 'green', sell: 'red', hold: 'blue', watch: 'orange' };

  return (
    <div>
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          {t.runs.runDetail}: {run.symbol}
          {run.stock_name && <Text type="secondary" style={{ fontSize: 16, marginLeft: 8 }}>{run.stock_name}</Text>}
        </Title>
        {isTerminal && run.status === 'completed' && (
          <div style={{ display: 'flex', gap: 8 }}>
            <Button icon={<PlusOutlined />} onClick={handleOpenActionModal}>
              {t.portfolio.recordAction}
            </Button>
            <Button type="primary" icon={<DownloadOutlined />} onClick={handleDownloadReport}>
              {t.runs.downloadReport}
            </Button>
          </div>
        )}
      </div>

      {/* ── Meta info ───────────────────────────────────────────────── */}
      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label={t.common.status}>
            <Tag color={statusColors[run.status]} icon={statusIcons[run.status]}>
              {run.status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t.common.created}>
            {new Date(run.created_at).toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label={t.runs.completedAt}>
            {run.completed_at ? new Date(run.completed_at).toLocaleString() : '—'}
          </Descriptions.Item>
          {run.error_message && (
            <Descriptions.Item label={t.runs.error} span={3}>
              <Text type="danger">{run.error_message}</Text>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      {/* ── Running indicator / SSE Stream ────────────────────────────── */}
      {run.status === 'running' && (
        <StreamPanel
          runId={id!}
          onCompleted={() => queryClient.invalidateQueries({ queryKey: ['runs', id] })}
        />
      )}
      {run.status === 'queued' && (
        <Card style={{ marginBottom: 16, textAlign: 'center' }}>
          <Spin size="large" />
          <div style={{ marginTop: 12 }}>
            <Text type="secondary">工作流排队中，等待开始执行...</Text>
          </div>
        </Card>
      )}

      {/* ── Analysis result ─────────────────────────────────────────── */}
      {run.status === 'completed' && run.result && (
        <Card title="分析结果" style={{ marginBottom: 16 }}>
          <DecisionPanel result={run.result as Record<string, any>} />
        </Card>
      )}

      {/* ── Progress events (live / historical) ─────────────────────── */}
      {events.length > 0 && (
        <Card title={t.runs.progressEvents} style={{ marginBottom: 16 }}>
          <Timeline
            items={events.map((evt, idx) => ({
              key: idx,
              color: timelineItemColor(evt.event),
              children: (
                <div>
                  <Text strong>{evt.event}</Text>
                  {evt.node && <Text type="secondary"> — {evt.node}</Text>}
                  {evt.phase && <Tag style={{ marginLeft: 8 }}>{evt.phase}</Tag>}
                  {evt.timestamp && (
                    <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                      {new Date(evt.timestamp).toLocaleTimeString()}
                    </Text>
                  )}
                  {evt.error && <div><Text type="danger">{evt.error}</Text></div>}
                </div>
              ),
            }))}
          />
        </Card>
      )}

      {/* ── Record Action Modal ──────────────────────────────────────── */}
      <Modal
        title={t.portfolio.recordAction}
        open={actionModalOpen}
        onCancel={() => setActionModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createActionMutation.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => createActionMutation.mutate(v)}>
          <Form.Item name="symbol" label={t.portfolio.symbol} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="stock_name" label={t.portfolio.stockName}>
            <Input />
          </Form.Item>
          <Form.Item name="action_type" label={t.portfolio.actionType} rules={[{ required: true }]}>
            <Select>
              {(['buy', 'sell', 'hold', 'watch'] as const).map((at) => (
                <Select.Option key={at} value={at}>
                  <Tag color={actionTypeColors[at]}>{t.portfolio[at]}</Tag>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="price" label={t.portfolio.price} rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={0} precision={2} />
          </Form.Item>
          <Form.Item name="quantity" label={t.portfolio.quantity}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="amount" label={t.portfolio.amount}>
            <InputNumber style={{ width: '100%' }} min={0} precision={2} />
          </Form.Item>
          <Form.Item name="reason" label={t.portfolio.reason}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="action_date" label={t.portfolio.actionDate} rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RunDetailPage;
