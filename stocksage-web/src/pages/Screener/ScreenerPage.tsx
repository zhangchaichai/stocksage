import React, { useEffect, useState } from 'react';
import {
  Button,
  Card,
  Checkbox,
  Col,
  DatePicker,
  Input,
  Modal,
  Radio,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import dayjs from 'dayjs';import {
  DeleteOutlined,
  DownloadOutlined,
  FilterOutlined,
  InfoCircleOutlined,
  LineChartOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../../i18n';
import { runApi, screenerApi, workflowApi } from '../../api/endpoints';
import StrategyCard from '../../components/Screener/StrategyCard';
import AnalystReportPanel from '../../components/Screener/AnalystReportPanel';
import type { AnalystReports, StrategyDetail, StrategyListItem, Workflow } from '../../types';

const { RangePicker } = DatePicker;
const { Title, Text, Paragraph } = Typography;

// ── Constants ──────────────────────────────────────────────────────────────

interface FilterRow {
  key: string;
  field: string;
  operator: string;
  value: string;
}

const OPERATOR_OPTIONS = [
  { value: 'gt', label: '>' },
  { value: 'gte', label: '>=' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '<=' },
  { value: 'eq', label: '==' },
  { value: 'ne', label: '!=' },
];

const FIELD_OPTIONS = [
  { value: 'pe', label: 'PE' },
  { value: 'pb', label: 'PB' },
  { value: 'market_cap', label: '总市值' },
  { value: 'close', label: '最新价' },
  { value: 'rsi', label: 'RSI' },
  { value: 'macd_dif', label: 'MACD DIF' },
  { value: 'macd_hist', label: 'MACD Histogram' },
  { value: 'ma5', label: 'MA5' },
  { value: 'ma10', label: 'MA10' },
  { value: 'ma20', label: 'MA20' },
  { value: 'ma60', label: 'MA60' },
  { value: 'adx', label: 'ADX' },
  { value: 'turnover_rate', label: '换手率' },
  { value: 'vol_ratio', label: '量比' },
  { value: 'change_pct', label: '涨跌幅' },
  { value: 'turnover_premium', label: '换手溢价' },
  { value: 'main_net_flow_total', label: '主力净流入' },
];

const POOL_OPTIONS = [
  { value: 'hs300', label: '沪深300' },
  { value: 'zz500', label: '中证500' },
  { value: 'zz1000', label: '中证1000' },
  { value: 'kc50', label: '科创50' },
  { value: 'cyb', label: '创业板' },
  { value: 'main_sh', label: '沪市主板' },
  { value: 'main_sz', label: '深市主板' },
  { value: 'all_a', label: 'A股全市场' },
  { value: 'custom', label: '自定义' },
];

const CATEGORIES = ['全部', '成长类', '技术面', '资金面', '价值类', '特色策略'];

const MARKET_FILTER_OPTIONS = [
  { value: 'sh_main', label: '沪市主板' },
  { value: 'sz_main', label: '深市主板' },
  { value: 'cyb',     label: '创业板' },
  { value: 'kcb',     label: '科创板' },
  { value: 'bj',      label: '北交所' },
];

let filterCounter = 0;

// ── Main Component ──────────────────────────────────────────────────────────

const ScreenerPage: React.FC = () => {
  const { t } = useI18n();
  const navigate = useNavigate();

  // ── Strategy template state ────────────────────────────────────────────
  const [strategies, setStrategies] = useState<StrategyListItem[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('全部');
  const [runningStrategy, setRunningStrategy] = useState<string | null>(null);
  const [previewStrategy, setPreviewStrategy] = useState<StrategyDetail | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);

  // ── NL search state ────────────────────────────────────────────────────
  const [nlInput, setNlInput] = useState('');
  const [nlLoading, setNlLoading] = useState(false);

  // ── Screener config state (v2.1) ──────────────────────────────────────
  const [topN, setTopN] = useState(20);
  const [enableAiScore, setEnableAiScore] = useState(false);
  // ── Date range & market filter (shared) ────────────────────────────────
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [marketFilters, setMarketFilters] = useState<string[]>([]);

  // ── Custom filter state (legacy) ────────────────────────────────────────
  const [filters, setFilters] = useState<FilterRow[]>([
    { key: `f-${++filterCounter}`, field: 'pe', operator: 'lt', value: '30' },
  ]);
  const [pool, setPool] = useState('hs300');
  const [customSymbols, setCustomSymbols] = useState('');
  const [loadingCustom, setLoadingCustom] = useState(false);

  // ── Shared job state ───────────────────────────────────────────────────
  const [jobs, setJobs] = useState<any[]>([]);
  const [polling, setPolling] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('templates');

  // ── Batch analysis state ───────────────────────────────────────────────
  const [batchModalVisible, setBatchModalVisible] = useState(false);
  const [batchJobId, setBatchJobId] = useState<string | null>(null);
  const [batchSelectedRows, setBatchSelectedRows] = useState<any[]>([]);
  const [batchWorkflows, setBatchWorkflows] = useState<Workflow[]>([]);
  const [batchWorkflowId, setBatchWorkflowId] = useState<string>('');
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  // per-job row selection: jobId → selected symbol keys
  const [jobRowSelection, setJobRowSelection] = useState<Record<string, React.Key[]>>({});

  // ── Backtest state ─────────────────────────────────────────────────────
  const [backtestVisible, setBacktestVisible] = useState(false);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestResult, setBacktestResult] = useState<any>(null);
  const [backtestJob, setBacktestJob] = useState<any>(null);

  // ── Load strategies on mount ───────────────────────────────────────────
  useEffect(() => {
    setLoadingStrategies(true);
    screenerApi.listStrategies()
      .then((res) => setStrategies(res.data))
      .catch(() => message.error('加载策略列表失败'))
      .finally(() => setLoadingStrategies(false));

    loadJobs();
  }, []);

  // ── Poll job completion ────────────────────────────────────────────────
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(async () => {
      try {
        const res = await screenerApi.getJob(polling);
        const job = res.data;
        // Update job in list for live candidate display
        setJobs((prev) =>
          prev.map((j) => (j.id === job.id ? job : j))
        );
        if (job.status === 'completed' || job.status === 'failed') {
          setPolling(null);
          setRunningStrategy(null);
          setLoadingCustom(false);
          loadJobs();
          setActiveTab('history');
          if (job.status === 'completed') {
            const matchCount = job.matches?.length ?? 0;
            const candidateCount = job.candidate_count ?? 0;
            message.success(
              `选股完成！候选 ${candidateCount} 只，精选 ${matchCount} 只`
            );
          } else {
            message.error(`选股失败: ${job.error || '未知错误'}`);
          }
        }
      } catch {
        setPolling(null);
        setRunningStrategy(null);
        setLoadingCustom(false);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [polling]);

  const loadJobs = async () => {
    try {
      const res = await screenerApi.listJobs();
      setJobs(res.data);
    } catch {
      // ignore
    }
  };

  // ── Batch analysis handlers ─────────────────────────────────────────────
  const openBatchModal = async (job: any, selectedRows: any[]) => {
    setBatchJobId(job.id);
    setBatchSelectedRows(selectedRows);
    try {
      const res = await workflowApi.list(0, 100);
      setBatchWorkflows(res.data.items);
      if (res.data.items.length > 0) setBatchWorkflowId(res.data.items[0].id);
    } catch {
      message.error('加载工作流列表失败');
    }
    setBatchModalVisible(true);
  };

  const handleBatchSubmit = async () => {
    if (!batchWorkflowId) {
      message.warning('请先选择工作流');
      return;
    }
    setBatchSubmitting(true);
    try {
      const symbols = batchSelectedRows.map((r) => r.symbol);
      const stockNames: Record<string, string> = {};
      batchSelectedRows.forEach((r) => { stockNames[r.symbol] = r.name || ''; });
      await runApi.batchSubmit({
        workflow_id: batchWorkflowId,
        symbols,
        stock_names: stockNames,
        source: batchJobId ? `screener_job:${batchJobId}` : undefined,
      });
      message.success(`已提交 ${symbols.length} 只股票的分析任务`);
      setBatchModalVisible(false);
      setBatchSelectedRows([]);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '批量提交失败');
    } finally {
      setBatchSubmitting(false);
    }
  };

  // ── Backtest handler ───────────────────────────────────────────────────
  const handleBacktest = async (job: any) => {
    if (!job.strategy_id) {
      message.warning('仅策略模板运行结果支持回测');
      return;
    }
    setBacktestJob(job);
    setBacktestResult(null);
    setBacktestVisible(true);
    setBacktestLoading(true);
    try {
      const res = await screenerApi.backtest({
        strategy_id: job.strategy_id,
        job_id: job.id,
        period_days: 30,
      });
      setBacktestResult(res.data);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '回测失败');
      setBacktestVisible(false);
    } finally {
      setBacktestLoading(false);
    }
  };

  // ── Strategy template handlers ─────────────────────────────────────────
  const handleUseStrategy = async (strategyId: string) => {
    setRunningStrategy(strategyId);
    try {
      const res = await screenerApi.run({
        strategy_id: strategyId,
        top_n: topN,
        enable_ai_score: enableAiScore,
        date_from: dateRange?.[0] || undefined,
        date_to: dateRange?.[1] || undefined,
        market_filters: marketFilters.length > 0 ? marketFilters : undefined,
      });
      // Insert the new job at the top of the jobs list
      setJobs((prev) => [res.data, ...prev]);
      setPolling(res.data.id);
      message.success('选股任务已提交，请稍候...');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交选股任务失败');
      setRunningStrategy(null);
    }
  };

  // ── NL query handler ───────────────────────────────────────────────────
  const handleNLSearch = async (value: string) => {
    const q = value.trim();
    if (!q) return;
    setNlLoading(true);
    try {
      const res = await screenerApi.nlQuery(q);
      const { pywencai_query, strategy_hint, error } = res.data;
      if (error || !pywencai_query) {
        message.warning(error || '无法解析查询，请尝试更具体的描述');
        return;
      }
      if (strategy_hint) {
        message.info(`已识别为「${strategies.find(s => s.id === strategy_hint)?.name || strategy_hint}」策略`);
        await handleUseStrategy(strategy_hint);
        return;
      }
      Modal.info({
        title: '自然语言查询已翻译',
        content: (
          <div>
            <p style={{ marginBottom: 8 }}>问财查询条件：</p>
            <div style={{ background: '#f5f5f5', padding: '8px 12px', borderRadius: 4, fontSize: 13 }}>
              {pywencai_query}
            </div>
            <p style={{ marginTop: 8, color: '#888', fontSize: 12 }}>
              您可将此条件复制到同花顺问财，或选择下方最接近的策略模板使用。
            </p>
          </div>
        ),
        okText: '知道了',
      });
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '查询转换失败');
    } finally {
      setNlLoading(false);
    }
  };

  const handlePreviewStrategy = async (strategyId: string) => {
    try {
      const res = await screenerApi.getStrategy(strategyId);
      setPreviewStrategy(res.data);
      setPreviewVisible(true);
    } catch {
      message.error('获取策略详情失败');
    }
  };

  const filteredStrategies = categoryFilter === '全部'
    ? strategies
    : strategies.filter((s) => s.category === categoryFilter);

  // ── Custom filter handlers ─────────────────────────────────────────────
  const addFilter = () => {
    setFilters([...filters, { key: `f-${++filterCounter}`, field: 'pe', operator: 'lt', value: '' }]);
  };

  const removeFilter = (key: string) => {
    setFilters(filters.filter((f) => f.key !== key));
  };

  const updateFilter = (key: string, field: string, value: any) => {
    setFilters(filters.map((f) => (f.key === key ? { ...f, [field]: value } : f)));
  };

  const handleCustomRun = async () => {
    const validFilters = filters
      .filter((f) => f.field && f.operator && f.value !== '')
      .map((f) => ({
        field: f.field,
        operator: f.operator,
        value: isNaN(Number(f.value)) ? f.value : Number(f.value),
      }));

    if (validFilters.length === 0) {
      message.warning(t.screener.addFilterFirst);
      return;
    }

    setLoadingCustom(true);
    try {
      const payload: any = {
        filters: validFilters,
        pool,
        top_n: topN,
        enable_ai_score: enableAiScore,
        date_from: dateRange?.[0] || undefined,
        date_to: dateRange?.[1] || undefined,
        market_filters: marketFilters.length > 0 ? marketFilters : undefined,
      };
      if (pool === 'custom' && customSymbols.trim()) {
        payload.custom_symbols = customSymbols.split(/[,，\s]+/).filter(Boolean);
      }
      const res = await screenerApi.run(payload);
      setJobs((prev) => [res.data, ...prev]);
      setPolling(res.data.id);
      message.success(t.screener.jobSubmitted);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || t.screener.submitFailed);
      setLoadingCustom(false);
    }
  };

  // ── CSV export ─────────────────────────────────────────────────────────
  const exportCSV = (rows: any[], filename: string) => {
    if (!rows?.length) return;
    const headers = ['代码', '名称', ...Object.keys(rows[0]?.indicators || {})];
    const csvRows = rows.map((m: any) => [
      m.symbol, m.name, ...Object.values(m.indicators || {}),
    ]);
    const csv = [headers, ...csvRows].map((r) => r.join(',')).join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Result table columns ───────────────────────────────────────────────
  const candidateColumns = [
    { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 90 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100 },
    {
      title: '指标摘要',
      key: 'indicators',
      render: (_: any, r: any) => {
        const entries = Object.entries(r.indicators || {}).slice(0, 5);
        return (
          <Space size={4} wrap>
            {entries.map(([k, v]: [string, any]) => (
              <Tag key={k} style={{ fontSize: 11 }}>
                {k}: {typeof v === 'number' ? v.toFixed(2) : String(v)}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: any, r: any) => (
        <Button size="small" type="link" onClick={() => navigate(`/indicators?symbol=${r.symbol}`)}>
          {t.screener.viewIndicators}
        </Button>
      ),
    },
  ];

  const matchColumns = [
    { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 90 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100 },
    {
      title: 'AI评分',
      key: 'ai_score',
      width: 80,
      sorter: (a: any, b: any) => (a.ai_score || 0) - (b.ai_score || 0),
      defaultSortOrder: 'descend' as const,
      render: (_: any, r: any) => r.ai_score != null && r.ai_score > 0 ? (
        <Tag color={r.ai_score >= 8 ? 'green' : r.ai_score >= 6 ? 'orange' : 'default'}>
          {r.ai_score.toFixed(1)}
        </Tag>
      ) : <Tag>-</Tag>,
    },
    {
      title: '推荐理由',
      key: 'ai_reason',
      render: (_: any, r: any) => r.ai_reason ? (
        <Text type="secondary" style={{ fontSize: 12 }}>{r.ai_reason}</Text>
      ) : null,
    },
    {
      title: '指标摘要',
      key: 'indicators',
      render: (_: any, r: any) => {
        const entries = Object.entries(r.indicators || {}).slice(0, 4);
        return (
          <Space size={4} wrap>
            {entries.map(([k, v]: [string, any]) => (
              <Tag key={k} style={{ fontSize: 11 }}>
                {k}: {typeof v === 'number' ? v.toFixed(2) : String(v)}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: any, r: any) => (
        <Button size="small" type="link" onClick={() => navigate(`/indicators?symbol=${r.symbol}`)}>
          {t.screener.viewIndicators}
        </Button>
      ),
    },
  ];

  // ── Screener config panel (shared between strategy and custom tabs) ────
  const configPanel = (
    <Card size="small" style={{ marginBottom: 16, background: '#fafafa' }}>
      <Row gutter={[16, 12]} align="middle">
        <Col>
          <Text strong>精选数量 (top_n)：</Text>
          <Slider
            min={5}
            max={50}
            step={5}
            value={topN}
            onChange={setTopN}
            style={{ width: 160, display: 'inline-block', marginLeft: 8, marginRight: 8, verticalAlign: 'middle' }}
            marks={{ 5: '5', 20: '20', 50: '50' }}
          />
          <Tag color="blue">{topN}</Tag>
        </Col>
        <Col>
          <Checkbox
            checked={enableAiScore}
            onChange={(e) => setEnableAiScore(e.target.checked)}
          >
            启用 AI 分析团队
          </Checkbox>
          <Tooltip title="AI 分析团队将从资金面、行业面、基本面三个维度撰写研报并综合推荐，额外耗时约 20-40 秒">
            <InfoCircleOutlined style={{ color: '#8c8c8c', marginLeft: 4 }} />
          </Tooltip>
        </Col>
      </Row>
      <Row gutter={[16, 8]} align="middle" style={{ marginTop: 10 }}>
        <Col>
          <Text strong style={{ marginRight: 8 }}>数据时间段：</Text>
          <RangePicker
            size="small"
            value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
            onChange={(_, strs) => {
              if (strs[0] && strs[1]) setDateRange([strs[0], strs[1]]);
              else setDateRange(null);
            }}
            disabledDate={(d) => d && d.isAfter(dayjs())}
            placeholder={['开始日期', '结束日期']}
            style={{ width: 240 }}
          />
          <Tooltip title="指定后，AI报告和价格数据将基于该时间段进行分析；留空则使用最新数据">
            <InfoCircleOutlined style={{ color: '#8c8c8c', marginLeft: 6 }} />
          </Tooltip>
        </Col>
        <Col flex="auto">
          <Text strong style={{ marginRight: 8 }}>板块筛选：</Text>
          <Select
            mode="multiple"
            size="small"
            placeholder="不限（全部板块）"
            value={marketFilters}
            onChange={setMarketFilters}
            options={MARKET_FILTER_OPTIONS}
            style={{ minWidth: 260 }}
            maxTagCount={3}
            allowClear
          />
          <Tooltip title="可多选：仅在选定板块内筛选候选股票">
            <InfoCircleOutlined style={{ color: '#8c8c8c', marginLeft: 6 }} />
          </Tooltip>
        </Col>
      </Row>
    </Card>
  );

  // ── Job result renderer (with dual tabs: candidates + matches) ────────
  const renderJobResult = (job: any) => {
    const candidates = job.candidates || [];
    const matches = job.matches || [];
    const candidateCount = job.candidate_count || candidates.length;
    const selectedRowKeys = jobRowSelection[job.id] || [];
    const selectedRows = matches.filter((m: any) => selectedRowKeys.includes(m.symbol));
    const onSelectionChange = (keys: React.Key[]) =>
      setJobRowSelection((prev) => ({ ...prev, [job.id]: keys }));

    const hasAiScore = matches.some((m: any) => m.ai_score != null && m.ai_score > 0);
    const analystReports: AnalystReports | null = job.analyst_reports || null;

    // Dual-tab: Candidates + AI Picks + AI 研报
    const resultTabs = [
      ...(analystReports
        ? [
            {
              key: 'ai_report',
              label: (
                <span>
                  📝 AI 研报
                </span>
              ),
              children: <AnalystReportPanel reports={analystReports} />,
            },
          ]
        : []),
      {
        key: 'candidates',
        label: (
          <span>
            <LineChartOutlined />
            候选列表
            {candidateCount > 0 && (
              <Tag style={{ marginLeft: 4 }} color="blue">{candidateCount}</Tag>
            )}
          </span>
        ),
        children: (
          <div>
            <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
              <Text type="secondary">Layer 1 数据获取结果 — 完整候选列表</Text>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={() => exportCSV(candidates, `candidates_${job.id.slice(0, 8)}.csv`)}
                disabled={candidates.length === 0}
              >
                导出候选
              </Button>
            </div>
            <Table
              dataSource={candidates}
              columns={candidateColumns}
              rowKey="symbol"
              size="small"
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 只` }}
            />
          </div>
        ),
      },
      {
        key: 'matches',
        label: (
          <span>
            <ThunderboltOutlined />
            {hasAiScore ? 'AI 精选' : '精选结果'}
            {matches.length > 0 && (
              <Tag style={{ marginLeft: 4 }} color={hasAiScore ? 'green' : 'blue'}>{matches.length}</Tag>
            )}
          </span>
        ),
        children: (
          <div>
            <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
              <Text type="secondary">
                {hasAiScore
                  ? `Layer 2 AI 评分结果 — 前 ${matches.length} 只按评分排序`
                  : `精选前 ${matches.length} 只`}
              </Text>
              <Space>
                {selectedRowKeys.length > 0 && (
                  <Button
                    size="small"
                    type="primary"
                    icon={<PlayCircleOutlined />}
                    onClick={() => openBatchModal(job, selectedRows)}
                  >
                    深度分析({selectedRowKeys.length})
                  </Button>
                )}
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => exportCSV(matches, `screener_${job.id.slice(0, 8)}.csv`)}
                  disabled={matches.length === 0}
                >
                  导出精选
                </Button>
              </Space>
            </div>
            <Table
              dataSource={matches}
              columns={matchColumns}
              rowKey="symbol"
              size="small"
              pagination={{ pageSize: 20 }}
              rowSelection={{
                selectedRowKeys,
                onChange: onSelectionChange,
              }}
            />
          </div>
        ),
      },
    ];

    return <Tabs items={resultTabs} size="small" defaultActiveKey={analystReports ? 'ai_report' : 'matches'} />;
  };

  // ── Tab content ────────────────────────────────────────────────────────

  const templateTab = (
    <div>
      {/* NL search bar */}
      <div style={{ marginBottom: 16 }}>
        <Input.Search
          value={nlInput}
          onChange={(e) => setNlInput(e.target.value)}
          placeholder='用自然语言描述选股需求，如"帮我找低价高成长的股票"'
          enterButton="AI选股"
          loading={nlLoading}
          onSearch={handleNLSearch}
          style={{ maxWidth: 600 }}
        />
      </div>

      {/* Screener config */}
      {configPanel}

      {/* Category filter */}
      <div style={{ marginBottom: 16 }}>
        <Radio.Group
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          buttonStyle="solid"
          size="small"
        >
          {CATEGORIES.map((c) => (
            <Radio.Button key={c} value={c}>{c}</Radio.Button>
          ))}
        </Radio.Group>
      </div>

      {loadingStrategies ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="加载策略中..." />
        </div>
      ) : (
        <Row gutter={[12, 12]}>
          {filteredStrategies.map((s) => (
            <Col key={s.id} xs={24} sm={12} md={8} lg={6}>
              <StrategyCard
                strategy={s}
                onUse={handleUseStrategy}
                onPreview={handlePreviewStrategy}
                loading={runningStrategy === s.id && !!polling}
              />
            </Col>
          ))}
        </Row>
      )}

      {/* Running indicator */}
      {polling && runningStrategy && (
        <Card style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin tip="选股中，请稍候..." />
          <br />
          <Text type="secondary" style={{ marginTop: 8, display: 'block' }}>
            使用策略: {strategies.find((s) => s.id === runningStrategy)?.name}
            {enableAiScore ? ' · AI 分析团队正在撰写研报...' : ''}
            &nbsp;· 完成后自动跳转到历史记录
          </Text>
        </Card>
      )}
    </div>
  );

  const customTab = (
    <Card>
      {/* Screener config */}
      {configPanel}

      <Space direction="vertical" style={{ width: '100%' }}>
        {filters.map((f) => (
          <Row gutter={8} key={f.key} align="middle">
            <Col span={7}>
              <Select
                value={f.field}
                onChange={(v) => updateFilter(f.key, 'field', v)}
                options={FIELD_OPTIONS}
                style={{ width: '100%' }}
                placeholder={t.screener.selectField}
              />
            </Col>
            <Col span={4}>
              <Select
                value={f.operator}
                onChange={(v) => updateFilter(f.key, 'operator', v)}
                options={OPERATOR_OPTIONS}
                style={{ width: '100%' }}
              />
            </Col>
            <Col span={7}>
              <Input
                value={f.value}
                onChange={(e) => updateFilter(f.key, 'value', e.target.value)}
                placeholder={t.screener.enterValue}
              />
            </Col>
            <Col span={2}>
              <Button
                icon={<DeleteOutlined />}
                danger
                type="text"
                onClick={() => removeFilter(f.key)}
                disabled={filters.length <= 1}
              />
            </Col>
          </Row>
        ))}

        <Row gutter={8} align="middle">
          <Col>
            <Button icon={<PlusOutlined />} onClick={addFilter}>
              {t.screener.addFilter}
            </Button>
          </Col>
          <Col span={6}>
            <Select
              value={pool}
              onChange={setPool}
              options={POOL_OPTIONS}
              style={{ width: '100%' }}
            />
          </Col>
          {pool === 'custom' && (
            <Col span={8}>
              <Input
                value={customSymbols}
                onChange={(e) => setCustomSymbols(e.target.value)}
                placeholder={t.screener.customSymbolsPlaceholder}
              />
            </Col>
          )}
          <Col>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={handleCustomRun}
              loading={loadingCustom || (!!polling && !runningStrategy)}
            >
              {polling && !runningStrategy ? t.screener.running : t.screener.runScreener}
            </Button>
          </Col>
        </Row>
      </Space>
    </Card>
  );

  const historyTab = (
    <div>
      {jobs.length === 0 && !polling && (
        <Card>
          <Paragraph type="secondary" style={{ textAlign: 'center', padding: 20 }}>
            {t.screener.noResults}
          </Paragraph>
        </Card>
      )}

      {polling && !runningStrategy && (
        <Card style={{ marginBottom: 8, textAlign: 'center', padding: 20 }}>
          <Spin tip={t.screener.scanning} />
        </Card>
      )}

      {jobs.map((job) => (
        <Card
          key={job.id}
          size="small"
          style={{ marginBottom: 8 }}
          title={
            <Space>
              <Tag color={
                job.status === 'completed' ? 'green' :
                job.status === 'failed' ? 'red' : 'blue'
              }>
                {job.status}
              </Tag>
              {job.strategy_id && (
                <Tag color="purple">{strategies.find((s) => s.id === job.strategy_id)?.name || job.strategy_id}</Tag>
              )}
              <span>候选: {job.candidate_count ?? (job.candidates?.length ?? 0)}</span>
              <span>精选: {job.matches?.length ?? 0}</span>
              {job.enable_ai_score && <Tag color="orange">AI评分</Tag>}
              {(job.date_from || job.date_to) && (
                <Tag color="geekblue">
                  {job.date_from || ''}～{job.date_to || '今'}
                </Tag>
              )}
              {(job.market_filters?.length > 0) && (
                <Tag color="cyan">
                  {(job.market_filters as string[]).map((mf: string) =>
                    MARKET_FILTER_OPTIONS.find(o => o.value === mf)?.label || mf
                  ).join('/')}
                </Tag>
              )}
              <Text type="secondary">{job.created_at?.slice(0, 16)}</Text>
            </Space>
          }
          extra={
            job.status === 'completed' && (
              <Space>
                {job.strategy_id && (
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    onClick={() => handleBacktest(job)}
                  >
                    回测
                  </Button>
                )}
              </Space>
            )
          }
        >
          {job.status === 'completed' && (job.matches?.length > 0 || job.candidates?.length > 0) && (
            renderJobResult(job)
          )}
          {job.status === 'running' && job.candidates?.length > 0 && (
            <div>
              <div style={{ marginBottom: 8 }}>
                <Spin size="small" />
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  Layer 1 已完成，AI 分析团队正在撰写研报...（已获取 {job.candidates.length} 只候选）
                </Text>
              </div>
              <Table
                dataSource={job.candidates}
                columns={candidateColumns}
                rowKey="symbol"
                size="small"
                pagination={{ pageSize: 10 }}
              />
            </div>
          )}
          {job.status === 'failed' && (
            <Text type="danger">{job.error}</Text>
          )}
        </Card>
      ))}
    </div>
  );

  const tabItems = [
    {
      key: 'templates',
      label: (
        <span>
          <ThunderboltOutlined />
          策略模板
          {strategies.length > 0 && (
            <Tag style={{ marginLeft: 4 }} color="blue">{strategies.length}</Tag>
          )}
        </span>
      ),
      children: templateTab,
    },
    {
      key: 'custom',
      label: (
        <span>
          <FilterOutlined />
          {t.screener.filterBuilder}
        </span>
      ),
      children: customTab,
    },
    {
      key: 'history',
      label: (
        <span>
          历史记录
          {jobs.length > 0 && (
            <Tag style={{ marginLeft: 4 }}>{jobs.length}</Tag>
          )}
        </span>
      ),
      children: historyTab,
    },
  ];

  return (
    <div>
      <Title level={3}>
        <FilterOutlined style={{ marginRight: 8 }} />
        {t.screener.title}
      </Title>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />

      {/* Strategy preview modal */}
      <Modal
        title={previewStrategy ? `${previewStrategy.icon} ${previewStrategy.name}` : '策略详情'}
        open={previewVisible}
        onCancel={() => setPreviewVisible(false)}
        footer={[
          <Button key="close" onClick={() => setPreviewVisible(false)}>关闭</Button>,
          <Button
            key="use"
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => {
              setPreviewVisible(false);
              if (previewStrategy) handleUseStrategy(previewStrategy.id);
            }}
          >
            立即使用
          </Button>,
        ]}
        width={620}
      >
        {previewStrategy && (
          <div>
            <Paragraph>{previewStrategy.description}</Paragraph>

            <div style={{ marginBottom: 12 }}>
              <Tag color="blue">{previewStrategy.category}</Tag>
              <Tag color={previewStrategy.risk_level === '高' ? 'red' : previewStrategy.risk_level === '中' ? 'orange' : 'green'}>
                {previewStrategy.risk_level}风险
              </Tag>
              <Tag>{previewStrategy.suitable_for}</Tag>
            </div>

            <div style={{ marginBottom: 12 }}>
              <Text strong>问财查询条件（按优先级）：</Text>
              {previewStrategy.pywencai_queries.length > 0 ? (
                previewStrategy.pywencai_queries.map((q, i) => (
                  <div key={i} style={{ fontSize: 12, color: '#666', marginTop: 4, padding: '4px 8px', background: '#f5f5f5', borderRadius: 4 }}>
                    {i + 1}. {q}
                  </div>
                ))
              ) : (
                <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>使用 AkShare 深度指标引擎</div>
              )}
            </div>

            <div>
              <Text strong>卖出信号：</Text>
              <Space wrap style={{ marginTop: 4 }}>
                {previewStrategy.sell_conditions.map((c: any, i: number) => (
                  <Tag key={i} color="red">{c.label}</Tag>
                ))}
              </Space>
            </div>
          </div>
        )}
      </Modal>

      {/* Batch analysis modal — with workflow selector */}
      <Modal
        title={`深度分析 — ${batchSelectedRows.length} 只股票`}
        open={batchModalVisible}
        onCancel={() => setBatchModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setBatchModalVisible(false)}>取消</Button>,
          <Button
            key="submit"
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={batchSubmitting}
            disabled={!batchWorkflowId}
            onClick={handleBatchSubmit}
          >
            提交分析
          </Button>,
        ]}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              将为以下股票提交工作流深度分析（Layer 3），结果可在「运行记录」页查看。
            </Text>
          </div>
          <div>
            <Space wrap>
              {batchSelectedRows.map((r) => (
                <Tag key={r.symbol}>{r.symbol} {r.name}</Tag>
              ))}
            </Space>
          </div>
          <div>
            <Text strong>选择工作流：</Text>
            <Select
              value={batchWorkflowId}
              onChange={setBatchWorkflowId}
              style={{ width: '100%', marginTop: 6 }}
              placeholder="请选择工作流"
            >
              {batchWorkflows.map((w) => (
                <Select.Option key={w.id} value={w.id}>
                  <Space>
                    <span>{w.name}</span>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {w.description?.slice(0, 40)}
                    </Text>
                  </Space>
                </Select.Option>
              ))}
            </Select>
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                推荐：快速分析类工作流适合批量（约30秒/只），深度辩论类适合精选1-3只（约5分/只）
              </Text>
            </div>
          </div>
        </Space>
      </Modal>

      {/* Backtest modal */}
      <Modal
        title={backtestJob ? `策略回测 — ${strategies.find(s => s.id === backtestJob.strategy_id)?.name || backtestJob.strategy_id}` : '策略回测'}
        open={backtestVisible}
        onCancel={() => setBacktestVisible(false)}
        footer={<Button onClick={() => setBacktestVisible(false)}>关闭</Button>}
        width={680}
      >
        {backtestLoading && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin tip="计算中，正在获取当前价格..." />
          </div>
        )}
        {!backtestLoading && backtestResult && (
          <div>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              {[
                { label: '股票数', value: backtestResult.total_stocks },
                { label: '平均收益', value: backtestResult.avg_return_pct != null ? `${backtestResult.avg_return_pct}%` : '-' },
                { label: '胜率', value: backtestResult.win_rate != null ? `${(backtestResult.win_rate * 100).toFixed(0)}%` : '-' },
                { label: '最大涨幅', value: backtestResult.max_gain_pct != null ? `${backtestResult.max_gain_pct}%` : '-' },
                { label: '最大跌幅', value: backtestResult.max_loss_pct != null ? `${backtestResult.max_loss_pct}%` : '-' },
              ].map(({ label, value }) => (
                <Col key={label} span={5}>
                  <Card size="small" style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 12, color: '#666' }}>{label}</div>
                    <div style={{ fontSize: 16, fontWeight: 600 }}>{value}</div>
                  </Card>
                </Col>
              ))}
            </Row>
            <Table
              dataSource={backtestResult.items || []}
              rowKey="symbol"
              size="small"
              pagination={{ pageSize: 10 }}
              columns={[
                { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 80 },
                { title: '名称', dataIndex: 'name', key: 'name', width: 90 },
                { title: '买入价', dataIndex: 'entry_price', key: 'entry', width: 80, render: (v: any) => v?.toFixed(2) ?? '-' },
                { title: '现价', dataIndex: 'current_price', key: 'cur', width: 80, render: (v: any) => v?.toFixed(2) ?? '-' },
                {
                  title: '涨跌幅',
                  dataIndex: 'price_change_pct',
                  key: 'pct',
                  width: 90,
                  render: (v: any) => v != null ? (
                    <Tag color={v >= 0 ? 'green' : 'red'}>{v >= 0 ? '+' : ''}{v}%</Tag>
                  ) : '-',
                },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 8 }}>
              * 买入价使用选股时的收盘价（close指标），现价为当前最新价，仅供参考。
            </Text>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ScreenerPage;
