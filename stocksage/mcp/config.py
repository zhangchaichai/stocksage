"""MCP Server 配置加载器。

从 YAML 文件读取 MCP Server 定义，支持 ${ENV_VAR} 环境变量解析。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MCPServerConfig:
    """单个 MCP Server 配置。"""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""
    market: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    enabled: bool = True


def _resolve_env_vars(env: dict) -> dict[str, str]:
    """解析 ${ENV_VAR} 格式的环境变量引用。"""
    resolved = {}
    for key, value in env.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            resolved[key] = os.environ.get(value[2:-1], "")
        else:
            resolved[key] = str(value)
    return resolved


def load_mcp_config(config_path: Path | None = None) -> list[MCPServerConfig]:
    """加载 MCP Server 配置列表，仅返回 enabled=true 的服务器。"""
    path = config_path or Path(__file__).parent.parent / "config" / "mcp_servers.yaml"
    if not path.exists():
        logger.info("未找到 MCP 配置文件 %s，MCP 功能关闭", path)
        return []

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    servers: list[MCPServerConfig] = []

    for name, cfg in (raw.get("servers") or {}).items():
        if not cfg.get("enabled", True):
            continue
        servers.append(MCPServerConfig(
            name=name,
            command=cfg["command"],
            args=cfg.get("args", []),
            env=_resolve_env_vars(cfg.get("env") or {}),
            description=cfg.get("description", ""),
            market=cfg.get("market", []),
            capabilities=cfg.get("capabilities", []),
        ))

    logger.info("已加载 %d 个 MCP Server 配置", len(servers))
    return servers
