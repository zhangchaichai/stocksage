#!/usr/bin/env bash
#
# StockSage — 一键停止脚本
# 停止所有 StockSage 服务 (后端 / 前端 / Worker / Docker)
#
# 用法:
#   ./stop.sh           # 停止所有服务
#   ./stop.sh --force   # 强制终止 (kill -9)
#   ./stop.sh --status  # 仅查看服务状态, 不停止
#
set -euo pipefail

# ─── 路径 ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
FORCE=false
STATUS_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --force|-f)   FORCE=true ;;
    --status|-s)  STATUS_ONLY=true ;;
    --help|-h)
      echo "用法: ./stop.sh [选项]"
      echo ""
      echo "选项:"
      echo "  (无参数)        停止所有 StockSage 服务"
      echo "  --force, -f     强制终止 (kill -9)"
      echo "  --status, -s    仅查看服务状态, 不停止"
      echo "  -h, --help      显示帮助"
      exit 0
      ;;
    *)
      err "未知参数: $arg  (用 --help 查看帮助)"
      exit 1
      ;;
  esac
done

# ─── 服务状态检查 ────────────────────────────────────────
check_service() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"

  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      echo -e "  ${GREEN}●${NC} $name  (PID $pid)"
      return 0
    else
      echo -e "  ${YELLOW}○${NC} $name  (PID $pid, 进程已退出)"
      return 1
    fi
  else
    echo -e "  ${RED}○${NC} $name  (未启动)"
    return 1
  fi
}

check_docker() {
  local compose_file="$SCRIPT_DIR/docker-compose.dev.yml"
  if [[ -f "$compose_file" ]] && docker compose -f "$compose_file" ps --quiet 2>/dev/null | grep -q .; then
    echo -e "  ${GREEN}●${NC} Docker 容器 (PostgreSQL + Redis)"
    return 0
  else
    echo -e "  ${RED}○${NC} Docker 容器 (未运行)"
    return 1
  fi
}

# ─── 状态模式 ────────────────────────────────────────────
if $STATUS_ONLY; then
  echo ""
  echo -e "${CYAN}StockSage 服务状态${NC}"
  echo "────────────────────────────────"
  has_running=false
  check_service backend  && has_running=true
  check_service frontend && has_running=true
  check_service worker   && has_running=true
  check_docker           && has_running=true
  echo "────────────────────────────────"
  if $has_running; then
    echo -e "  停止服务: ${YELLOW}./stop.sh${NC}"
  else
    echo -e "  ${GREEN}所有服务已停止${NC}"
  fi
  echo ""
  exit 0
fi

# ─── 停止服务 ────────────────────────────────────────────
echo ""
info "正在停止 StockSage 服务..."
echo ""

stopped=false
SIGNAL="TERM"
$FORCE && SIGNAL="KILL"

for svc in backend frontend worker; do
  pid_file="$PID_DIR/$svc.pid"
  if [[ -f "$pid_file" ]]; then
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      if $FORCE; then
        kill -9 "$pid" 2>/dev/null
        ok "$svc 已强制终止 (PID $pid)"
      else
        kill "$pid" 2>/dev/null
        # 等待进程退出 (最多 5 秒)
        for _ in $(seq 1 10); do
          kill -0 "$pid" 2>/dev/null || break
          sleep 0.5
        done
        if kill -0 "$pid" 2>/dev/null; then
          warn "$svc 未响应 SIGTERM, 强制终止 (PID $pid)"
          kill -9 "$pid" 2>/dev/null || true
        else
          ok "$svc 已停止 (PID $pid)"
        fi
      fi
      stopped=true
    else
      info "$svc 进程已不存在 (PID $pid), 清理 pid 文件"
    fi
    rm -f "$pid_file"
  fi
done

# ─── 停止 Docker 容器 ────────────────────────────────────
compose_file="$SCRIPT_DIR/docker-compose.dev.yml"
if [[ -f "$compose_file" ]] && docker compose -f "$compose_file" ps --quiet 2>/dev/null | grep -q .; then
  info "停止 Docker 容器..."
  docker compose -f "$compose_file" down 2>/dev/null
  ok "Docker 容器已停止 (PostgreSQL + Redis)"
  stopped=true
fi

# ─── 清理端口占用 (兜底) ─────────────────────────────────
cleanup_port() {
  local port="$1"
  local name="$2"
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    for pid in $pids; do
      local cmd
      cmd=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
      if $FORCE; then
        kill -9 "$pid" 2>/dev/null || true
        warn "端口 $port ($name) 残留进程已强制终止: $cmd (PID $pid)"
      else
        kill "$pid" 2>/dev/null || true
        warn "端口 $port ($name) 残留进程已终止: $cmd (PID $pid)"
      fi
      stopped=true
    done
  fi
}

cleanup_port 8000 "后端 API"
cleanup_port 5173 "前端 Vite"

# ─── 结果 ────────────────────────────────────────────────
echo ""
if $stopped; then
  echo -e "${GREEN}========================================${NC}"
  echo -e "${GREEN}  StockSage 所有服务已停止              ${NC}"
  echo -e "${GREEN}========================================${NC}"
else
  echo -e "${CYAN}========================================${NC}"
  echo -e "${CYAN}  没有正在运行的服务                    ${NC}"
  echo -e "${CYAN}========================================${NC}"
fi
echo ""
echo -e "  启动服务:  ${CYAN}./start.sh${NC}"
echo ""
