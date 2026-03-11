#!/usr/bin/env bash
#
# StockSage — 一键启动脚本 (零外部依赖)
# core v0.2.0 | api v0.1.0
#
# 用法:
#   ./start.sh              # 启动后端+前端 (SQLite, 无需 Docker/PG/Redis)
#   ./start.sh --backend    # 仅启动后端
#   ./start.sh --frontend   # 仅启动前端
#   ./start.sh --worker     # 同时启动 arq worker (异步任务队列)
#   ./start.sh --docker     # 用 Docker 启动 PG+Redis (可选)
#   ./start.sh --stop       # 停止所有服务 (也可使用独立 stop.sh)
#   ./start.sh --test       # 运行所有测试
#   ./start.sh --check      # 预检依赖和配置
#
set -euo pipefail

# ─── 路径 ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR/stocksage-api"
WEB_DIR="$SCRIPT_DIR/stocksage-web"
PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/.logs"

# ─── 颜色 ───────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR]${NC}  $*"; }

# ─── 参数解析 ────────────────────────────────────────────
USE_DOCKER=false
START_BACKEND=true
START_FRONTEND=true
START_WORKER=false
DO_STOP=false
DO_TEST=false
DO_CHECK=false

for arg in "$@"; do
  case "$arg" in
    --docker)     USE_DOCKER=true ;;
    --backend)    START_FRONTEND=false ;;
    --frontend)   START_BACKEND=false ;;
    --worker)     START_WORKER=true ;;
    --stop)       DO_STOP=true ;;
    --test)       DO_TEST=true ;;
    --check)      DO_CHECK=true ;;
    --help|-h)
      echo "用法: ./start.sh [选项]"
      echo ""
      echo "选项:"
      echo "  (无参数)      一键启动后端+前端 (SQLite, 零依赖)"
      echo "  --backend     仅启动后端"
      echo "  --frontend    仅启动前端"
      echo "  --worker      同时启动 arq worker (screener/runs 异步任务)"
      echo "  --docker      额外用 Docker 启动 PostgreSQL + Redis"
      echo "  --test        运行所有测试 (core pytest + API pytest + 前端 tsc)"
      echo "  --check       预检: 依赖 + API key + 模块导入 + 类型检查"
      echo "  --stop        停止所有服务 (也可使用: ./stop.sh)"
      echo "  -h, --help    显示帮助"
      exit 0
      ;;
    *)
      err "未知参数: $arg  (用 --help 查看帮助)"
      exit 1
      ;;
  esac
done

# ─── 停止服务 ────────────────────────────────────────────
stop_services() {
  info "正在停止服务..."
  local stopped=false

  for svc in backend frontend worker; do
    if [[ -f "$PID_DIR/$svc.pid" ]]; then
      pid=$(cat "$PID_DIR/$svc.pid")
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null && ok "$svc 已停止 (PID $pid)"
        stopped=true
      fi
      rm -f "$PID_DIR/$svc.pid"
    fi
  done

  if docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" ps --quiet 2>/dev/null | grep -q .; then
    docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" down 2>/dev/null
    ok "Docker 容器已停止"
    stopped=true
  fi

  if $stopped; then
    ok "所有服务已停止"
  else
    info "没有正在运行的服务"
  fi
}

if $DO_STOP; then
  stop_services
  exit 0
fi

# ─── 测试模式 ────────────────────────────────────────────
if $DO_TEST; then
  info "运行所有测试..."
  echo ""
  FAIL=false

  # 核心库测试
  info "核心库测试 (pytest tests/)..."
  cd "$SCRIPT_DIR"
  if python3 -m pytest tests/ -v --tb=short; then
    ok "核心库测试全部通过"
  else
    err "核心库测试失败"
    FAIL=true
  fi
  echo ""

  # Backend API tests
  info "后端 API 测试 (pytest stocksage-api/tests/)..."
  cd "$API_DIR"
  if python3 -m pytest tests/ -v --tb=short; then
    ok "后端 API 测试全部通过"
  else
    err "后端 API 测试失败"
    FAIL=true
  fi
  cd "$SCRIPT_DIR"
  echo ""

  # Frontend type check
  info "前端类型检查 (tsc --noEmit)..."
  cd "$WEB_DIR"
  if npx tsc --noEmit; then
    ok "前端类型检查通过"
  else
    err "前端类型检查失败"
    FAIL=true
  fi
  cd "$SCRIPT_DIR"
  echo ""

  # Frontend build
  info "前端构建测试 (vite build)..."
  cd "$WEB_DIR"
  if npx vite build; then
    ok "前端构建成功"
  else
    err "前端构建失败"
    FAIL=true
  fi
  cd "$SCRIPT_DIR"

  echo ""
  if $FAIL; then
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  测试未全部通过, 请检查以上错误        ${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
  else
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  所有测试通过!                         ${NC}"
    echo -e "${GREEN}========================================${NC}"
  fi
  exit 0
fi

# ─── 预检模式 ────────────────────────────────────────────
if $DO_CHECK; then
  info "预检: 验证项目状态..."
  PASS=true
  echo ""

  # Check core library
  if python3 -c "import stocksage" 2>/dev/null; then
    ok "核心库 stocksage 已安装"
  else
    warn "核心库未安装 (运行: pip install -e .)"
    PASS=false
  fi

  # Check Python deps (API)
  if python3 -c "import fastapi, sqlalchemy, pydantic" 2>/dev/null; then
    ok "后端 Python 依赖已安装"
  else
    warn "后端 Python 依赖未完整安装 (运行: pip install -e stocksage-api[dev])"
    PASS=false
  fi

  # Check pywencai (screener v2)
  if python3 -c "import pywencai" 2>/dev/null; then
    ok "pywencai 选股引擎已安装"
  else
    warn "pywencai 未安装 (运行: pip install 'pywencai>=0.10.0')"
    PASS=false
  fi

  # Check Node.js (pywencai 依赖)
  if command -v node &>/dev/null; then
    ok "Node.js 已安装 ($(node --version)) — pywencai 必需"
  else
    warn "Node.js 未安装 — pywencai 选股引擎无法工作"
    PASS=false
  fi

  # Check Node modules
  if [[ -d "$WEB_DIR/node_modules" ]]; then
    ok "前端 Node 依赖已安装"
  else
    warn "前端 Node 依赖未安装 (运行: cd stocksage-web && npm install)"
    PASS=false
  fi

  # Check DEEPSEEK_API_KEY
  if [[ -f "$SCRIPT_DIR/.env" ]] && grep -q "DEEPSEEK_API_KEY=sk-" "$SCRIPT_DIR/.env" 2>/dev/null; then
    ok "DEEPSEEK_API_KEY 已配置 (根目录 .env)"
  elif [[ -f "$API_DIR/.env" ]] && grep -q "DEEPSEEK_API_KEY=sk-" "$API_DIR/.env" 2>/dev/null; then
    ok "DEEPSEEK_API_KEY 已配置 (stocksage-api/.env)"
  elif [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    ok "DEEPSEEK_API_KEY 已配置 (环境变量)"
  else
    warn "DEEPSEEK_API_KEY 未配置 (在 .env 中设置: DEEPSEEK_API_KEY=sk-...)"
    PASS=false
  fi

  # Backend import check
  if cd "$API_DIR" && python3 -c "from app.main import app; print(f'  {len(app.routes)} routes')" 2>/dev/null; then
    ok "后端模块导入正常"
  else
    warn "后端模块导入失败"
    PASS=false
  fi
  cd "$SCRIPT_DIR"

  # Frontend type check
  cd "$WEB_DIR"
  if npx tsc --noEmit 2>/dev/null; then
    ok "前端 TypeScript 类型检查通过"
  else
    warn "前端 TypeScript 有类型错误"
    PASS=false
  fi
  cd "$SCRIPT_DIR"

  echo ""
  if $PASS; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  预检通过! 可以启动服务                ${NC}"
    echo -e "${GREEN}========================================${NC}"
  else
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}  预检发现问题, 请修复后再启动          ${NC}"
    echo -e "${YELLOW}========================================${NC}"
    exit 1
  fi
  exit 0
fi

# ─── 准备目录 ────────────────────────────────────────────
mkdir -p "$PID_DIR" "$LOG_DIR"

# ─── 环境检查 ────────────────────────────────────────────
info "检查环境..."

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    err "未找到 $1, 请先安装"
    exit 1
  fi
}

$START_BACKEND  && check_cmd python3
# Node.js 始终需要: 前端构建 + pywencai 选股引擎依赖
($START_BACKEND || $START_FRONTEND) && check_cmd node
$START_FRONTEND && check_cmd npm
$USE_DOCKER     && check_cmd docker

ok "环境检查通过"

# ─── Docker 基础设施 (可选) ──────────────────────────────
if $USE_DOCKER; then
  COMPOSE_FILE="$SCRIPT_DIR/docker-compose.dev.yml"
  if [[ ! -f "$COMPOSE_FILE" ]]; then
    info "生成 docker-compose.dev.yml..."
    cat > "$COMPOSE_FILE" << 'YAML'
services:
  postgres:
    image: postgres:16-alpine
    container_name: stocksage-postgres
    environment:
      POSTGRES_USER: stocksage
      POSTGRES_PASSWORD: stocksage
      POSTGRES_DB: stocksage
    ports:
      - "5432:5432"
    volumes:
      - stocksage-pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U stocksage"]
      interval: 5s
      timeout: 3s
      retries: 5
  redis:
    image: redis:7-alpine
    container_name: stocksage-redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
volumes:
  stocksage-pgdata:
YAML
  fi

  info "启动 PostgreSQL + Redis 容器..."
  docker compose -f "$COMPOSE_FILE" up -d

  info "等待数据库就绪..."
  for _ in $(seq 1 30); do
    docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U stocksage &>/dev/null && break
    sleep 1
  done
  ok "PostgreSQL 就绪"

  for _ in $(seq 1 15); do
    docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping &>/dev/null && break
    sleep 1
  done
  ok "Redis 就绪"

  DB_URL="postgresql+asyncpg://stocksage:stocksage@localhost:5432/stocksage"
else
  DB_URL="sqlite+aiosqlite:///./stocksage.db"
fi

# ─── .env 文件 ───────────────────────────────────────────
ENV_FILE="$API_DIR/.env"
if [[ ! -f "$ENV_FILE" ]] || ! grep -q "DATABASE_URL" "$ENV_FILE" 2>/dev/null; then
  info "生成 stocksage-api/.env..."
  cat > "$ENV_FILE" << EOF
DATABASE_URL=$DB_URL
JWT_SECRET=stocksage-dev-secret-key-change-in-prod
JWT_EXPIRE_MINUTES=1440
DEBUG=true
DEFAULT_LLM_PROVIDER=deepseek
RATE_LIMIT_PER_MINUTE=120
DAILY_TOKEN_QUOTA=1000000
EOF
  ok "stocksage-api/.env 已生成 (数据库: $(echo $DB_URL | cut -d: -f1))"

  # 提示配置 API Key
  if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
    warn "请在 stocksage-api/.env 中添加: DEEPSEEK_API_KEY=sk-..."
  fi
else
  ok "stocksage-api/.env 已存在, 跳过"
fi

# ─── 后端启动 ────────────────────────────────────────────
if $START_BACKEND; then
  # 停止已有进程
  if [[ -f "$PID_DIR/backend.pid" ]]; then
    old_pid=$(cat "$PID_DIR/backend.pid")
    kill "$old_pid" 2>/dev/null || true
    rm -f "$PID_DIR/backend.pid"
    sleep 1
  fi

  # 安装核心库 (如果缺少)
  if ! python3 -c "import stocksage" 2>/dev/null; then
    info "安装核心库 stocksage..."
    pip install -e "$SCRIPT_DIR" --quiet
  fi

  # 安装 API 依赖 (如果缺少)
  if ! python3 -c "import fastapi" 2>/dev/null; then
    info "安装后端依赖..."
    pip install -e "$API_DIR[dev]" --quiet
  fi
  ok "后端依赖就绪"

  info "启动后端 (uvicorn port 8000)..."
  cd "$API_DIR"
  uvicorn app.main:app \
    --reload \
    --host 0.0.0.0 \
    --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$PID_DIR/backend.pid"
  cd "$SCRIPT_DIR"

  # 等待健康检查
  for i in $(seq 1 20); do
    if curl -sf http://localhost:8000/api/health &>/dev/null; then
      break
    fi
    sleep 1
  done

  if curl -sf http://localhost:8000/api/health &>/dev/null; then
    ok "后端已启动: http://localhost:8000"
  else
    warn "后端启动中, 查看日志: $LOG_DIR/backend.log"
  fi
fi

# ─── arq Worker 启动 ─────────────────────────────────────
if $START_WORKER; then
  if [[ -f "$PID_DIR/worker.pid" ]]; then
    old_pid=$(cat "$PID_DIR/worker.pid")
    kill "$old_pid" 2>/dev/null || true
    rm -f "$PID_DIR/worker.pid"
    sleep 1
  fi

  info "启动 arq worker..."
  cd "$API_DIR"
  python3 -m arq app.runs.worker.WorkerSettings \
    > "$LOG_DIR/worker.log" 2>&1 &
  echo $! > "$PID_DIR/worker.pid"
  cd "$SCRIPT_DIR"
  sleep 1
  ok "arq worker 已启动 (异步任务队列)"
fi

# ─── 前端启动 ────────────────────────────────────────────
if $START_FRONTEND; then
  # 停止已有进程
  if [[ -f "$PID_DIR/frontend.pid" ]]; then
    old_pid=$(cat "$PID_DIR/frontend.pid")
    kill "$old_pid" 2>/dev/null || true
    rm -f "$PID_DIR/frontend.pid"
    sleep 1
  fi

  # 安装依赖 (如果缺少)
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    info "安装前端依赖..."
    cd "$WEB_DIR" && npm install --silent && cd "$SCRIPT_DIR"
  fi
  ok "前端依赖就绪"

  info "启动前端 (vite port 5173)..."
  cd "$WEB_DIR"
  npx vite --host 0.0.0.0 --port 5173 \
    > "$LOG_DIR/frontend.log" 2>&1 &
  echo $! > "$PID_DIR/frontend.pid"
  cd "$SCRIPT_DIR"

  for i in $(seq 1 10); do
    sleep 1
    if curl -sf http://localhost:5173 &>/dev/null; then
      break
    fi
  done
  ok "前端已启动: http://localhost:5173"
fi

# ─── 完成 ────────────────────────────────────────────────
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  StockSage 启动完成                    ${NC}"
echo -e "${GREEN}  core v0.2.0 | api v0.1.0             ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
$START_FRONTEND && echo -e "  前端地址:  ${CYAN}http://localhost:5173${NC}"
$START_BACKEND  && echo -e "  后端地址:  ${CYAN}http://localhost:8000${NC}"
$START_BACKEND  && echo -e "  API 文档:  ${CYAN}http://localhost:8000/docs${NC}"
echo ""
$START_BACKEND  && echo -e "  后端日志:  $LOG_DIR/backend.log"
$START_FRONTEND && echo -e "  前端日志:  $LOG_DIR/frontend.log"
$START_WORKER   && echo -e "  Worker日志: $LOG_DIR/worker.log"
echo ""
echo -e "  停止服务:  ${YELLOW}./stop.sh${NC}  或  ${YELLOW}./start.sh --stop${NC}"
echo ""
