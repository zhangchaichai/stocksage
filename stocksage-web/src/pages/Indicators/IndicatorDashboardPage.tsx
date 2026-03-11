import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Col,
  Input,
  Row,
  Spin,
  Statistic,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  LineChartOutlined,
  QuestionCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import { useI18n } from '../../i18n';
import { indicatorsApi } from '../../api/endpoints';

const { Title } = Typography;

interface IndicatorGroup {
  name: string;
  label: string;
  indicators: Record<string, unknown>;
}

interface IndicatorData {
  symbol: string;
  period: number;
  groups: IndicatorGroup[];
}

const CATEGORY_COLORS: Record<string, string> = {
  technical: 'blue',
  kbar: 'purple',
  rolling: 'cyan',
  ashare: 'red',
  risk: 'orange',
  fundamental: 'green',
  fund_flow: 'gold',
  margin: 'magenta',
  dealer: 'volcano',
};

/** 常用指标中文说明（hover tooltip） */
const INDICATOR_DESC: Record<string, string> = {
  // 均线
  ma5: '5日简单移动平均线 — 短期趋势参考',
  ma10: '10日简单移动平均线 — 短期趋势参考',
  ma20: '20日简单移动平均线 — 中期趋势参考',
  ma60: '60日简单移动平均线 — 长期趋势参考',
  ema12: '12日指数移动平均线 — MACD 快线基础',
  ema26: '26日指数移动平均线 — MACD 慢线基础',
  // MACD
  macd: 'MACD 差离值 (DIF - DEA)，正值看多，负值看空',
  macd_dif: 'MACD DIF — 快线 EMA12 与慢线 EMA26 之差',
  macd_dea: 'MACD DEA — DIF 的 9 日 EMA 信号线',
  macd_hist: 'MACD 柱状图 (Histogram)，可视化动能变化',
  // RSI
  rsi: 'RSI 相对强弱指数 (14日)，>70 超买，<30 超卖',
  rsi6: 'RSI 6日，反应更灵敏，>80 超买，<20 超卖',
  rsi14: 'RSI 14日，标准设置，用于判断超买超卖',
  // 布林带
  boll_upper: '布林带上轨 — 价格偏高警戒线',
  boll_mid: '布林带中轨 (20日均线)',
  boll_lower: '布林带下轨 — 价格偏低支撑线',
  boll_width: '布林带带宽 — 值越大波动越剧烈',
  // KDJ
  kdj_k: 'KDJ K值，>80 超买，<20 超卖',
  kdj_d: 'KDJ D值，K 的 3 日移动平均，更平滑',
  kdj_j: 'KDJ J值，方向最灵敏，>100 极度超买，<0 极度超卖',
  // 成交量
  volume: '当日成交量 (股)',
  volume_ma5: '5日平均成交量',
  volume_ma20: '20日平均成交量',
  vol_ratio: '量比 — 当日量与过去5日均量之比，>1.5 放量',
  // 振幅 / 涨跌
  amplitude: '振幅 — (最高-最低)/昨收，衡量当日波动幅度',
  change_pct: '涨跌幅 (%)，正为上涨，负为下跌',
  turnover_rate: '换手率 (%) — 成交量占流通股比例，越高活跃度越高',
  // ATR / 波动
  atr: 'ATR 真实波幅 (14日) — 衡量价格波动范围，越高风险越大',
  atr14: 'ATR 14日真实波幅',
  // 价格
  close: '最新收盘价',
  open: '开盘价',
  high: '最高价',
  low: '最低价',
  // 趋势
  adx: 'ADX 趋势强度指标 (14日)，>25 趋势强，<20 震荡',
  cci: 'CCI 顺势指标，>100 超买，<-100 超卖',
  wr: 'WR 威廉指标，-20 以上超买，-80 以下超卖',
  // 基本面
  pe: 'PE 市盈率 — 股价/每股收益，越低估值越低',
  pb: 'PB 市净率 — 股价/每股净资产，<1 通常被低估',
  ps: 'PS 市销率 — 股价/每股收入',
  roe: 'ROE 净资产收益率 (%) — 衡量公司盈利效率',
  // 资金流
  net_inflow: '主力资金净流入额，正为净流入，负为净流出',
  main_inflow: '主力资金流入量',
  main_outflow: '主力资金流出量',
  // 融资融券
  margin_buy: '融资买入额 — 市场看多情绪参考',
  margin_repay: '融资偿还额',
  margin_balance: '融资余额 — 存量杠杆规模',
  // 北向资金
  north_net: '北向资金净流入 (亿元)，正为买入，负为卖出',
  north_buy: '北向资金买入额 (亿元)',
  north_sell: '北向资金卖出额 (亿元)',
  // 风险
  sharpe: 'Sharpe 夏普比率 — 每单位风险超额收益，>1 为优',
  sortino: 'Sortino 比率 — 仅考虑下行风险的夏普改进版',
  var95: 'VaR 95% 风险价值 — 95%置信下最大日亏损',
  max_drawdown: '最大回撤 (%) — 历史峰值到谷值最大跌幅',
};

const formatValue = (val: unknown): string => {
  if (val === null || val === undefined) return '-';
  if (typeof val === 'number') {
    if (Number.isNaN(val) || !Number.isFinite(val)) return '-';
    return Math.abs(val) >= 1000000
      ? `${(val / 1000000).toFixed(2)}M`
      : Math.abs(val) >= 1000
        ? `${(val / 1000).toFixed(2)}K`
        : val.toFixed(4).replace(/\.?0+$/, '') || '0';
  }
  if (typeof val === 'boolean') return val ? 'Yes' : 'No';
  if (typeof val === 'object') return JSON.stringify(val);
  return String(val);
};

const IndicatorDashboardPage: React.FC = () => {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const [symbol, setSymbol] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<IndicatorData | null>(null);

  const fetchIndicators = useCallback(async (sym: string) => {
    // Strip exchange suffix (.SH / .SZ) — indicators API expects pure numeric code
    const trimmed = sym.trim().replace(/\.(SH|SZ|sh|sz)$/, '');
    if (!trimmed) return;
    setLoading(true);
    try {
      const res = await indicatorsApi.get(trimmed);
      setData(res.data);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || t.indicators.fetchFailed);
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Auto-load when navigated from screener with ?symbol=XXX
  useEffect(() => {
    const urlSymbol = searchParams.get('symbol');
    if (urlSymbol) {
      const clean = urlSymbol.replace(/\.(SH|SZ|sh|sz)$/, '');
      setSymbol(clean);
      fetchIndicators(clean);
    }
  }, [searchParams, fetchIndicators]);

  const handleSearch = async () => {
    const trimmed = symbol.trim();
    if (!trimmed) {
      message.warning(t.indicators.enterSymbol);
      return;
    }
    fetchIndicators(trimmed);
  };

  const renderIndicatorCards = (indicators: Record<string, unknown>) => {
    const entries = Object.entries(indicators);
    return (
      <Row gutter={[12, 12]}>
        {entries.map(([key, val]) => {
          const desc = INDICATOR_DESC[key.toLowerCase()];
          const titleNode = desc ? (
            <Tooltip title={desc} placement="top">
              <span style={{ cursor: 'help' }}>
                {key} <QuestionCircleOutlined style={{ fontSize: 11, color: '#8c8c8c' }} />
              </span>
            </Tooltip>
          ) : (
            key
          );
          return (
            <Col xs={12} sm={8} md={6} lg={4} key={key}>
              <Card size="small" hoverable>
                <Statistic
                  title={titleNode}
                  value={formatValue(val)}
                  valueStyle={{ fontSize: 14 }}
                />
              </Card>
            </Col>
          );
        })}
      </Row>
    );
  };

  const tabItems = data
    ? data.groups.map((group) => ({
        key: group.name,
        label: (
          <span>
            <Tag color={CATEGORY_COLORS[group.name] || 'default'} style={{ marginRight: 4 }}>
              {Object.keys(group.indicators).length}
            </Tag>
            {group.label}
          </span>
        ),
        children: renderIndicatorCards(group.indicators),
      }))
    : [];

  return (
    <div>
      <Title level={3}>
        <LineChartOutlined style={{ marginRight: 8 }} />
        {t.indicators.title}
      </Title>

      <Card style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder={t.indicators.symbolPlaceholder}
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          onSearch={handleSearch}
          enterButton={<><SearchOutlined /> {t.indicators.search}</>}
          size="large"
          style={{ maxWidth: 480 }}
          loading={loading}
        />
      </Card>

      {loading && (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" tip={t.common.loading} />
        </div>
      )}

      {!loading && data && (
        <Card>
          <Typography.Text type="secondary" style={{ marginBottom: 12, display: 'block' }}>
            {t.indicators.resultsFor} <strong>{data.symbol}</strong> ({data.period} {t.indicators.days})
          </Typography.Text>
          <Tabs items={tabItems} />
        </Card>
      )}

      {!loading && !data && (
        <Card>
          <Typography.Paragraph type="secondary" style={{ textAlign: 'center', padding: 40 }}>
            {t.indicators.hint}
          </Typography.Paragraph>
        </Card>
      )}
    </div>
  );
};

export default IndicatorDashboardPage;
