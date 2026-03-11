"""StrategyRegistry: load and resolve YAML-defined screener strategies."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_STRATEGIES_DIR = Path(__file__).parent


@dataclass
class SellCondition:
    type: str    # ma_cross_down | holding_days | stop_loss | take_profit | rsi_overbought
    label: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyDef:
    id: str
    name: str
    description: str
    icon: str
    category: str
    risk_level: str
    suitable_for: str
    pool: str
    # pywencai engine
    pywencai_enabled: bool
    pywencai_queries: list[str]
    pywencai_top_n: int
    pywencai_sort_field: str | None
    pywencai_sort_ascending: bool
    # AkShare deep enrichment
    akshare_enrich_enabled: bool
    akshare_required_fields: list[str]
    # quant signals
    sell_conditions: list[SellCondition]
    # display
    display_fields: list[dict[str, str]]
    risk_params: dict[str, Any]
    exclude: list[dict[str, Any]]


class StrategyRegistry:
    """Singleton-style registry that loads strategies from YAML files."""

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyDef] = {}

    def load_from_dir(self, path: Path | None = None) -> None:
        """Load all *.yaml files in *path* (defaults to this package dir)."""
        target = path or _STRATEGIES_DIR
        loaded = 0
        for yaml_file in sorted(target.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                strat = self._parse(raw)
                self._strategies[strat.id] = strat
                loaded += 1
                logger.debug("Loaded strategy: %s (%s)", strat.id, strat.name)
            except Exception as exc:
                logger.error("Failed to load strategy from %s: %s", yaml_file.name, exc)
        logger.info("StrategyRegistry: %d strategies loaded from %s", loaded, target)

    def get(self, strategy_id: str) -> StrategyDef | None:
        return self._strategies.get(strategy_id)

    def list_all(self) -> list[StrategyDef]:
        return list(self._strategies.values())

    def _parse(self, raw: dict) -> StrategyDef:
        pw = raw.get("pywencai") or {}
        ak = raw.get("akshare_enrich") or {}
        qs = raw.get("quant_signals") or {}

        sell_conds = [
            SellCondition(
                type=c["type"],
                label=c["label"],
                params={k: v for k, v in c.items() if k not in ("type", "label")},
            )
            for c in qs.get("sell_conditions", [])
        ]

        return StrategyDef(
            id=raw["id"],
            name=raw["name"],
            description=raw.get("description", ""),
            icon=raw.get("icon", "📊"),
            category=raw.get("category", "综合"),
            risk_level=raw.get("risk_level", "中"),
            suitable_for=raw.get("suitable_for", ""),
            pool=raw.get("pool", "hs300"),
            pywencai_enabled=pw.get("enabled", True),
            pywencai_queries=pw.get("queries", []),
            pywencai_top_n=pw.get("top_n", 20),
            pywencai_sort_field=pw.get("sort_field"),
            pywencai_sort_ascending=pw.get("sort_ascending", True),
            akshare_enrich_enabled=ak.get("enabled", False),
            akshare_required_fields=ak.get("required_fields", []),
            sell_conditions=sell_conds,
            display_fields=raw.get("display_fields", []),
            risk_params=raw.get("risk_params", {}),
            exclude=raw.get("exclude", []),
        )


# Module-level singleton — imported by worker and router
registry = StrategyRegistry()
registry.load_from_dir()
