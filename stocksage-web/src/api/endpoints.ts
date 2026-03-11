import api from './client';
import type {
  BacktestResult,
  BacktestStats,
  BuiltinSkill,
  CustomSkill,
  EvolutionSuggestion,
  InvestmentAction,
  MarketplaceSkill,
  MemoryCategory,
  MemoryItem,
  PaginatedResponse,
  PortfolioSummary,
  QuotaResponse,
  ShareLinkResponse,
  StockMemory,
  StrategyDetail,
  StrategyListItem,
  TimelineEntry,
  TokenResponse,
  UsageDashboard,
  UsageSummary,
  User,
  Workflow,
  WorkflowDefinition,
  WorkflowExport,
  WorkflowRun,
  WorkflowTemplate,
} from '../types';

// ---- Auth ----
export const authApi = {
  register: (data: { username: string; email: string; password: string }) =>
    api.post<TokenResponse>('/auth/register', data),
  login: (data: { email: string; password: string }) =>
    api.post<TokenResponse>('/auth/login', data),
  me: () => api.get<User>('/auth/me'),
};

// ---- Workflows ----
export const workflowApi = {
  list: (skip = 0, limit = 50) =>
    api.get<PaginatedResponse<Workflow>>('/workflows', { params: { skip, limit } }),
  get: (id: string) => api.get<Workflow>(`/workflows/${id}`),
  create: (data: { name: string; description?: string; definition: WorkflowDefinition }) =>
    api.post<Workflow>('/workflows', data),
  update: (id: string, data: Partial<{ name: string; description: string; definition: WorkflowDefinition }>) =>
    api.put<Workflow>(`/workflows/${id}`, data),
  delete: (id: string) => api.delete(`/workflows/${id}`),
  validate: (data: { name: string; definition: WorkflowDefinition }) =>
    api.post('/workflows/validate', data),
  templates: () => api.get<WorkflowTemplate[]>('/workflows/templates'),
};

// ---- Skills ----
export const skillApi = {
  list: (skip = 0, limit = 50) =>
    api.get<PaginatedResponse<CustomSkill>>('/skills', { params: { skip, limit } }),
  builtins: () => api.get<BuiltinSkill[]>('/skills/builtins'),
  get: (id: string) => api.get<CustomSkill>(`/skills/${id}`),
  create: (data: { name: string; type: string; tags?: string[]; definition_md: string }) =>
    api.post<CustomSkill>('/skills', data),
  update: (id: string, data: Partial<{ name: string; type: string; tags: string[]; definition_md: string }>) =>
    api.put<CustomSkill>(`/skills/${id}`, data),
  delete: (id: string) => api.delete(`/skills/${id}`),
};

// ---- Runs ----
export const runApi = {
  list: (skip = 0, limit = 50) =>
    api.get<PaginatedResponse<WorkflowRun>>('/runs', { params: { skip, limit } }),
  get: (id: string) => api.get<WorkflowRun>(`/runs/${id}`),
  submit: (data: { workflow_id: string; symbol: string; stock_name?: string; config_overrides?: Record<string, unknown> }) =>
    api.post<WorkflowRun>('/runs', data),
  batchSubmit: (data: {
    workflow_id: string;
    symbols: string[];
    stock_names?: Record<string, string>;
    source?: string;
    config_overrides?: Record<string, unknown>;
  }) => api.post<WorkflowRun[]>('/runs/batch', data),
  cancel: (id: string) => api.delete(`/runs/${id}`),
};

// ---- Reports ----
export const reportApi = {
  markdown: (runId: string) => api.get<string>(`/reports/${runId}/markdown`),
  pdf: (runId: string) =>
    api.get(`/reports/${runId}/pdf`, { responseType: 'blob' }),
};

// ---- Marketplace ----
export const marketplaceApi = {
  list: (skip = 0, limit = 50, search?: string, type?: string) =>
    api.get<PaginatedResponse<MarketplaceSkill>>('/marketplace/skills', { params: { skip, limit, search, type } }),
  star: (skillId: string) =>
    api.post(`/marketplace/skills/${skillId}/star`),
  fork: (skillId: string) =>
    api.post<CustomSkill>(`/marketplace/skills/${skillId}/fork`),
  publish: (skillId: string) =>
    api.post<CustomSkill>(`/marketplace/skills/${skillId}/publish`),
};

// ---- Sharing ----
export const sharingApi = {
  share: (workflowId: string) =>
    api.post<ShareLinkResponse>(`/sharing/workflows/${workflowId}/share`),
  exportWorkflow: (workflowId: string) =>
    api.get<WorkflowExport>(`/sharing/workflows/${workflowId}/export`),
  importWorkflow: (data: WorkflowExport) =>
    api.post<{ workflow_id: string; name: string; skills_imported: number }>('/sharing/workflows/import', data),
  getPublic: (workflowId: string) =>
    api.get<Workflow>(`/sharing/public/${workflowId}`),
};

// ---- Usage ----
export const usageApi = {
  summary: (period: string = 'all') =>
    api.get<UsageSummary>('/usage/summary', { params: { period } }),
  daily: (days: number = 30) =>
    api.get<UsageDashboard>('/usage/daily', { params: { days } }),
  quota: () =>
    api.get<QuotaResponse>('/usage/quota'),
};

// ---- Portfolio ----
export const portfolioApi = {
  recordAction: (data: {
    symbol: string; stock_name?: string; action_type: string;
    price: number; quantity?: number; amount?: number;
    reason?: string; run_id?: string; action_date: string;
  }) => api.post<InvestmentAction>('/portfolio/actions', data),

  listActions: (params?: { symbol?: string; skip?: number; limit?: number }) =>
    api.get<PaginatedResponse<InvestmentAction>>('/portfolio/actions', { params }),

  getAction: (id: string) =>
    api.get<InvestmentAction>(`/portfolio/actions/${id}`),

  updateAction: (id: string, data: Partial<{ price: number; quantity: number; amount: number; reason: string; action_type: string }>) =>
    api.put<InvestmentAction>(`/portfolio/actions/${id}`, data),

  deleteAction: (id: string) =>
    api.delete(`/portfolio/actions/${id}`),

  getSummary: () =>
    api.get<PortfolioSummary>('/portfolio/summary'),

  getHoldings: () =>
    api.get<PortfolioSummary['holdings']>('/portfolio/holdings'),

  getStockHistory: (symbol: string) =>
    api.get<InvestmentAction[]>(`/portfolio/${symbol}/history`),
};

// ---- Memory ----
export const memoryApi = {
  listCategories: () =>
    api.get<MemoryCategory[]>('/memory/categories'),

  getCategoryItems: (name: string, skip = 0, limit = 20) =>
    api.get<PaginatedResponse<MemoryItem>>(`/memory/categories/${name}/items`, {
      params: { skip, limit },
    }),

  getItem: (id: string) =>
    api.get<MemoryItem>(`/memory/items/${id}`),

  deleteItem: (id: string) =>
    api.delete(`/memory/items/${id}`),

  setPreference: (data: { key: string; value: string; category?: string }) =>
    api.post<MemoryItem>('/memory/preferences', data),

  getPreferences: () =>
    api.get<MemoryItem[]>('/memory/preferences'),

  getStockMemory: (symbol: string) =>
    api.get<StockMemory>(`/memory/stock/${symbol}`),

  getStockTimeline: (symbol: string) =>
    api.get<TimelineEntry[]>(`/memory/stock/${symbol}/timeline`),

  search: (data: { query: string; k?: number; category?: string }) =>
    api.post<MemoryItem[]>('/memory/search', data),

  forget: () =>
    api.post<{ compressed: number; archived: number }>('/memory/forget'),
};

// ---- Backtest ----
export const backtestApi = {
  run: (data: { action_id: string; period_days?: number }) =>
    api.post<BacktestResult>('/backtest/run', data),

  runAll: (data: { period_days?: number }) =>
    api.post<BacktestResult[]>('/backtest/run-all', data),

  listResults: (params?: { symbol?: string; period?: number; skip?: number; limit?: number }) =>
    api.get<BacktestResult[]>('/backtest/results', { params }),

  getResult: (id: string) =>
    api.get<BacktestResult>(`/backtest/results/${id}`),

  getStats: () =>
    api.get<BacktestStats>('/backtest/stats'),

  getSymbolStats: (symbol: string) =>
    api.get<BacktestStats>(`/backtest/stats/${symbol}`),
};

// ---- Evolution ----
export const evolutionApi = {
  listSuggestions: (params?: { status?: string; skip?: number; limit?: number }) =>
    api.get<EvolutionSuggestion[]>('/evolution/suggestions', { params }),

  getSuggestion: (id: string) =>
    api.get<EvolutionSuggestion>(`/evolution/suggestions/${id}`),

  accept: (id: string) =>
    api.post<EvolutionSuggestion>(`/evolution/suggestions/${id}/accept`),

  reject: (id: string) =>
    api.post<EvolutionSuggestion>(`/evolution/suggestions/${id}/reject`),

  modify: (id: string, data: { suggestion_text?: string; suggestion_diff?: Record<string, unknown> }) =>
    api.put<EvolutionSuggestion>(`/evolution/suggestions/${id}/modify`, data),

  getHistory: (params?: { skip?: number; limit?: number }) =>
    api.get<EvolutionSuggestion[]>('/evolution/history', { params }),
};

// ---- Indicators ----
export const indicatorsApi = {
  get: (symbol: string, period?: number) =>
    api.get<any>(`/indicators/${symbol}`, { params: period ? { period } : {} }),
};

// ---- Screener ----
export const screenerApi = {
  // Strategy templates
  listStrategies: () =>
    api.get<StrategyListItem[]>('/screener/strategies'),

  getStrategy: (id: string) =>
    api.get<StrategyDetail>(`/screener/strategies/${id}`),

  // Natural language query translation
  nlQuery: (query: string) =>
    api.post<{ pywencai_query: string; strategy_hint?: string; error?: string }>(
      '/screener/nl_query',
      { query },
    ),

  // Jobs
  run: (data: {
    filters?: any[];
    pool?: string;
    custom_symbols?: string[];
    strategy_id?: string;
    top_n?: number;
    enable_ai_score?: boolean;
    date_from?: string;
    date_to?: string;
    market_filters?: string[];
  }) => api.post<any>('/screener/run', data),

  listJobs: (skip = 0, limit = 20) =>
    api.get<any[]>('/screener/jobs', { params: { skip, limit } }),

  getJob: (id: string) =>
    api.get<any>(`/screener/jobs/${id}`),

  backtest: (data: { strategy_id: string; job_id: string; period_days?: number }) =>
    api.post<any>('/screener/backtest', data),
};

// ---- Chat ----
export const chatApi = {
  sendMessage: (data: { message: string }) =>
    api.post<any>('/chat/message', data),

  history: (skip = 0, limit = 50) =>
    api.get<any[]>('/chat/history', { params: { skip, limit } }),
};
