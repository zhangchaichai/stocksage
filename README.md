# StockSage

**多 Agent 智能股票分析系统** — LangGraph + DeepSeek + AkShare

> core v0.2.0 | api v0.1.0

---

## 简介

StockSage 是一个基于多 AI 智能体协作的股票分析平台，模拟证券公司分析师团队对个股进行全方位分析并输出投资决策。

- **六维分析**: 技术面、基本面、资金流向、市场情绪、新闻舆情、风险管理
- **法庭辩论工作流**: 多空双方立场辩论 + 专家评审 + 法官综合裁决
- **可配置工作流**: YAML 定义节点与边，fan-out 并行、fan-in 汇聚
- **全栈架构**: CLI 工具 + FastAPI 后端 + React 前端 + SQLite/PostgreSQL
- **多数据源**: AkShare / YFinance / MCP Server，自动降级

---

## 系统架构

```
┌─────────────────────────────────┐
│   stocksage-web  (React + Vite) │  :5173
└───────────────┬─────────────────┘
                │ REST / SSE
┌───────────────▼─────────────────┐
│  stocksage-api  (FastAPI)       │  :8000
│  auth / runs / workflows /      │
│  screener / portfolio / ...     │
└───────────────┬─────────────────┘
                │
┌───────────────▼─────────────────┐
│   stocksage  (核心库)            │
│                                 │
│  WorkflowCompiler               │
│    └─ YAML → LangGraph 图       │
│                                 │
│  Phase 1: DataFetcher (并行)    │
│    ├─ stock_info / price_data   │
│    ├─ financial / quarterly     │
│    ├─ news / fund_flow          │
│    ├─ sentiment / margin        │
│    └─ northbound / balance_sheet│
│                                 │
│  Phase 2: SkillExecutor (并行)  │
│    ├─ 技术分析师                 │
│    ├─ 基本面分析师               │
│    ├─ 资金流向分析师             │
│    ├─ 市场情绪分析师             │
│    ├─ 新闻分析师                 │
│    └─ 风险管理师                 │
│                                 │
│  Phase 3–5: 辩论 / 专家 / 决策  │
└─────────────────────────────────┘
```

---

## 目录结构

```
StockSage/
├── stocksage/              # 核心分析库 (Python 包)
│   ├── workflows/          # 内置 YAML 工作流定义 (9 个)
│   ├── skills/             # Markdown 技能定义
│   │   ├── agents/         # 分析师技能
│   │   ├── data/           # 数据获取技能
│   │   ├── debate/         # 辩论技能 (多空双方)
│   │   ├── experts/        # 专家评审技能
│   │   ├── decision/       # 决策技能
│   │   └── researcher/     # 研究员技能
│   ├── data/               # DataFetcher + 数据模型
│   ├── llm/                # LLM 工厂 (DeepSeek)
│   ├── skill_engine/       # SkillRegistry + SkillExecutor
│   ├── workflow/           # WorkflowCompiler + LangGraph 引擎
│   ├── mcp/                # MCP Client Manager + ToolBridge
│   └── main.py             # CLI 入口
│
├── stocksage-api/          # FastAPI 后端
│   └── app/
│       ├── auth/           # JWT 认证
│       ├── runs/           # 分析任务执行 + arq 异步队列
│       ├── workflows/      # 工作流 CRUD
│       ├── skills/         # 技能管理
│       ├── screener/       # 选股引擎 (pywencai)
│       ├── portfolio/      # 持仓管理
│       ├── backtest/       # 回测框架
│       ├── indicators/     # 技术指标
│       └── ...
│
├── stocksage-web/          # React 前端 (Vite + TypeScript)
│   └── src/
│       ├── pages/          # 页面
│       ├── components/     # 组件
│       ├── stores/         # 状态管理
│       └── api/            # API 客户端
│
├── tests/                  # 核心库单元测试
├── start.sh                # 一键启动脚本
├── stop.sh                 # 停止脚本
└── pyproject.toml          # 核心库构建配置
```

---

## 内置工作流

| 工作流 | 描述 |
|--------|------|
| `courtroom_debate_v3` | 法庭辩论（默认）— 多空辩论 + 专家评审 + 法官裁决 |
| `quick_analysis` | 快速分析 — 3 个分析师直接决策 |
| `full_spectrum` | 全维度分析 — 6 个分析师完整覆盖 |
| `deep_fundamental` | 深度基本面分析 |
| `deep_research` | 深度研究模式 |
| `macro_cycle_analysis` | 宏观周期分析 |
| `macro_sentiment` | 宏观情绪分析 |
| `dealer_tracking` | 游资追踪分析 |
| `dragon_tiger_analysis` | 龙虎榜分析 |

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+ (前端 + pywencai 选股引擎)
- DeepSeek API Key

### 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd StockSage

# 2. 配置 API Key
echo "DEEPSEEK_API_KEY=sk-..." > .env

# 3. 安装核心库
pip install -e .

# 4. 一键启动（后端 + 前端）
./start.sh
```

启动后访问：
- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

### CLI 使用

```bash
# 安装后直接使用
stocksage 600519                                    # 分析贵州茅台（默认法庭辩论工作流）
stocksage 000001 --name 平安银行                    # 指定股票名称
stocksage 600519 --workflow quick_analysis          # 快速分析模式
stocksage 600519 --workflow path/to/custom.yaml     # 自定义工作流
stocksage 600519 --pdf                              # 同时生成 PDF 报告
stocksage 600519 --no-md                            # 不生成 Markdown 报告
stocksage 600519 --legacy                           # 使用旧版 WorkflowEngine
stocksage 600519 -v                                 # 详细日志
```

### 启动选项

```bash
./start.sh              # 启动后端 + 前端（SQLite，零依赖）
./start.sh --backend    # 仅启动后端
./start.sh --frontend   # 仅启动前端
./start.sh --worker     # 同时启动 arq worker（异步任务队列）
./start.sh --docker     # 用 Docker 启动 PostgreSQL + Redis
./start.sh --test       # 运行所有测试
./start.sh --check      # 预检依赖和配置
./start.sh --stop       # 停止所有服务
```

---

## 环境变量

在项目根目录或 `stocksage-api/` 目录下创建 `.env`：

```env
# 必需
DEEPSEEK_API_KEY=sk-...

# 后端配置（start.sh 自动生成）
DATABASE_URL=sqlite+aiosqlite:///./stocksage.db   # 或 PostgreSQL URL
JWT_SECRET=your-secret-key
DEBUG=true

# 可选数据源
TUSHARE_TOKEN=...        # Tushare 数据（备用）
```

---

## 自定义工作流

工作流使用 YAML 定义，支持串行、并行（fan-out/fan-in）编排：

```yaml
name: my_workflow
version: "3.0.0"
description: "自定义分析工作流"

nodes:
  - name: collect_data
    skill: collect_data
    type: custom
  - name: technical_analyst
    skill: technical_analyst
  - name: judge
    skill: judge

edges:
  - source: START
    target: collect_data
    type: serial
  - source: collect_data
    target: [technical_analyst, fundamental_analyst]
    type: fan_out        # 并行
  - source: technical_analyst
    target: judge
    type: fan_in         # 汇聚
  - source: judge
    target: END
    type: serial

custom_nodes:
  collect_data: "engine._collect_data"
```

运行：
```bash
stocksage 600519 --workflow path/to/my_workflow.yaml
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 核心库 | Python 3.10+, LangGraph 0.2+, DeepSeek API |
| 数据源 | AkShare, YFinance, MCP Server (可选) |
| 后端 | FastAPI, SQLAlchemy 2.0, Alembic, arq, JWT |
| 前端 | React, TypeScript, Vite |
| 数据库 | SQLite（默认）/ PostgreSQL（生产） |
| 异步队列 | arq + Redis（可选） |

---

## 开发

```bash
# 运行测试
./start.sh --test

# 仅运行核心库测试
pytest tests/ -v

# 预检环境
./start.sh --check
```

---

## 数据说明

本项目通过 AkShare 获取公开市场数据，仅供学习与研究使用，不构成投资建议。
