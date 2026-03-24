export interface User {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Workflow {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  definition: WorkflowDefinition;
  version: string;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowDefinition {
  name?: string;
  version?: string;
  state?: Record<string, unknown>;
  nodes: NodeDef[];
  edges: EdgeDef[];
}

export interface NodeDef {
  id: string;
  skill: string;
  config?: Record<string, unknown>;
}

export interface EdgeDef {
  from: string;
  to: string;
  type?: 'serial' | 'fan_out' | 'fan_in' | 'conditional';
  condition?: Record<string, unknown>;
}

export interface WorkflowTemplate {
  name: string;
  description: string;
  definition: WorkflowDefinition;
}

export interface CustomSkill {
  id: string;
  owner_id: string;
  name: string;
  version: string;
  type: string;
  tags: string[];
  definition_md: string;
  created_at: string;
  updated_at: string;
}

export interface BuiltinSkill {
  name: string;
  type: string;
  category: string;
  version: string;
  description: string;
  definition_md: string;
}

export interface WorkflowRun {
  id: string;
  owner_id: string;
  workflow_id: string | null;
  symbol: string;
  stock_name: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  config_overrides: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface RunProgressEvent {
  event: string;
  node?: string | null;
  phase?: string | null;
  payload?: Record<string, unknown>;
  timestamp?: string | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface MarketplaceSkill extends CustomSkill {
  owner_username: string;
  is_published: boolean;
  stars_count: number;
  starred_by_me: boolean;
  forked_from: string | null;
}

export interface ShareLinkResponse {
  share_url: string;
  workflow_id: string;
}

export interface WorkflowExport {
  name: string;
  description: string;
  definition: WorkflowDefinition;
  version: string;
  skills: Record<string, unknown>[];
}

export interface UsageSummary {
  total_tokens_input: number;
  total_tokens_output: number;
  total_tokens: number;
  total_runs: number;
  period: string;
}

export interface DailyUsage {
  date: string;
  tokens_input: number;
  tokens_output: number;
  runs_count: number;
}

export interface UsageDashboard {
  summary: UsageSummary;
  daily: DailyUsage[];
}

export interface QuotaResponse {
  daily_limit: number;
  used_today: number;
  remaining: number;
}

// ---- Portfolio & Memory ----

export interface InvestmentAction {
  id: string;
  user_id: string;
  run_id: string | null;
  symbol: string;
  stock_name: string;
  action_type: 'buy' | 'sell' | 'hold' | 'watch';
  price: number;
  quantity: number | null;
  amount: number | null;
  reason: string | null;
  analysis_snapshot: Record<string, unknown> | null;
  action_date: string;
  created_at: string;
}

export interface PortfolioHolding {
  symbol: string;
  stock_name: string;
  quantity: number;
  avg_cost: number;
  last_analysis_date: string | null;
}

export interface PortfolioSummary {
  total_cost: number;
  holding_count: number;
  holdings: PortfolioHolding[];
}

export interface MemoryItem {
  id: string;
  memory_type: string;
  content: string;
  structured_data: Record<string, unknown> | null;
  importance_weight: number;
  access_count: number;
  happened_at: string | null;
  is_archived: boolean;
  categories: string[];
  created_at: string;
}

export interface MemoryCategory {
  id: string;
  name: string;
  description: string;
  summary: string | null;
  item_count: number;
}

export interface StockMemory {
  symbol: string;
  profile: MemoryItem | null;
  analysis_events: MemoryItem[];
  price_anchors: MemoryItem[];
  strategy_reviews: MemoryItem[];
  actions: MemoryItem[];
}

export interface TimelineEntry {
  date: string;
  type: string;
  content: string;
  structured_data: Record<string, unknown> | null;
}

export interface DealerSignal {
  type: string;
  confidence: number;
  description: string;
}

export interface BacktestResult {
  id: string;
  action_id: string;
  symbol: string;
  period_days: number;
  action_price: number;
  current_price: number;
  price_change_pct: number;
  max_drawdown_pct: number | null;
  max_gain_pct: number | null;
  predicted_direction: string;
  actual_direction: string;
  direction_correct: boolean;
  diagnosis: BacktestDiagnosis | null;
  // Phase 4: enhanced fields
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  var_95: number | null;
  wyckoff_phase_at_action: string | null;
  dealer_signals_at_action: DealerSignal[] | null;
  backtest_date: string;
  created_at: string;
}

export interface BacktestDiagnosis {
  accuracy_verdict: 'correct' | 'partially_correct' | 'incorrect';
  score: number;
  direction_correct: boolean;
  magnitude_error: string;
  correct_insights: string[];
  missed_factors: string[];
  root_cause: string;
  improvement_suggestions: EvolutionSuggestionPayload[];
}

export interface EvolutionSuggestionPayload {
  type: string;
  target: string;
  suggestion: string;
  priority: string;
}

export interface EvolutionSuggestion {
  id: string;
  backtest_id: string | null;
  evolution_type: 'skill_weight' | 'skill_prompt' | 'workflow_structure' | 'new_skill';
  target_type: 'skill' | 'workflow';
  target_name: string;
  suggestion_text: string;
  suggestion_diff: Record<string, unknown> | null;
  priority: 'high' | 'medium' | 'low';
  confidence: number;
  status: 'pending' | 'accepted' | 'rejected' | 'applied';
  applied_at: string | null;
  created_at: string;
}

export interface BacktestStats {
  total_actions: number;
  direction_accuracy: number;
  avg_return: number;
  win_rate: number;
  max_drawdown: number;
  dimension_accuracy: Record<string, number>;
  // Phase 4: enhanced stats
  avg_sharpe: number;
  avg_sortino: number;
  avg_var_95: number;
  wyckoff_accuracy: Record<string, number>;
  dealer_signal_accuracy: number;
}

// ── Screener Strategy types ────────────────────────────────────────────────

export interface AnalystReport {
  id: string;
  title: string;
  icon: string;
  report: string;
}

export interface SynthesisTopPick {
  symbol: string;
  name: string;
  score: number;
  reason: string;
}

export interface SynthesisReport {
  report: string;
  top_picks: SynthesisTopPick[];
}

export interface AnalystReportsMeta {
  candidate_count: number;
  strategy: string;
  data_date?: string;
  report_date?: string;
  duration_sec: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface AnalystReports {
  analysts: AnalystReport[];
  synthesis: SynthesisReport;
  meta: AnalystReportsMeta;
}

export interface StrategyListItem {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  risk_level: string;
  suitable_for: string;
  pool: string;
  sell_condition_count: number;
}

export interface StrategyDetail extends StrategyListItem {
  pywencai_queries: string[];
  display_fields: Array<{ field: string; label: string }>;
  sell_conditions: Array<Record<string, unknown>>;
  risk_params: Record<string, unknown>;
}

// ── Scheduler types ──────────────────────────────────────────────────────────

export interface ScheduledTask {
  id: string;
  user_id: string;
  name: string;
  task_type: 'screener' | 'workflow_run' | 'workflow_backtest' | 'screener_backtest' | 'memory_forgetting';
  cron_expr: string;
  timezone: string;
  enabled: boolean;
  config: Record<string, unknown>;
  last_run_at: string | null;
  last_run_status: 'completed' | 'failed' | null;
  last_run_error: string | null;
  run_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface ScheduledTaskCreate {
  name: string;
  task_type: ScheduledTask['task_type'];
  cron_expr: string;
  timezone?: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

export interface ScheduledTaskUpdate {
  name?: string;
  cron_expr?: string;
  timezone?: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

// ── Screener Backtest types ─────────────────────────────────────────────────

export interface ScreenerBacktestResult {
  id: string;
  user_id: string;
  job_id: string;
  strategy_id: string | null;
  period_days: number;
  backtest_date: string | null;
  total_stocks: number;
  avg_return_pct: number | null;
  win_rate: number | null;
  max_gain_pct: number | null;
  max_loss_pct: number | null;
  sharpe_ratio: number | null;
  stock_details: ScreenerBacktestStockDetail[] | null;
  diagnosis: ScreenerBacktestDiagnosis | null;
  created_at: string;
}

export interface ScreenerBacktestStockDetail {
  symbol: string;
  name: string;
  entry_price: number | null;
  current_price: number | null;
  price_change_pct: number | null;
  max_gain_pct: number | null;
  max_drawdown_pct: number | null;
  error: string | null;
}

export interface ScreenerBacktestDiagnosis {
  overall_verdict: 'effective' | 'marginal' | 'ineffective';
  score: number;
  strengths: string[];
  weaknesses: string[];
  best_picks: string[];
  worst_picks: string[];
  root_cause: string;
  improvement_suggestions: Array<{
    type: string;
    target: string;
    priority: string;
    confidence: number;
    suggestion: string;
  }>;
}

export interface ScreenerBacktestStats {
  total_backtests: number;
  avg_return: number;
  avg_win_rate: number;
  avg_sharpe: number;
  best_strategy: string | null;
}
