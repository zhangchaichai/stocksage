"""Web 搜索工具：为盲点分析提供实时数据支撑。

搜索策略：DuckDuckGo Lite HTML（对中文财经搜索效果好）。
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def search_blind_spots(
    blind_spots: list[str],
    stock_name: str = "",
    max_results_per_query: int = 5,
) -> dict[str, list[dict]]:
    """针对每个盲点执行 web 搜索，返回 {盲点描述: [搜索结果]}。"""
    if not blind_spots:
        return {}

    results: dict[str, list[dict]] = {}

    for bs in blind_spots:
        try:
            query = _build_query(bs, stock_name)
            items = _ddg_lite_search(query, max_results=max_results_per_query)
            results[bs] = items
            logger.info("  盲点搜索完成: %s (%d 条结果)", bs[:30], len(items))
        except Exception as e:
            results[bs] = []
            logger.warning("  盲点搜索失败: %s: %s", bs[:30], e)
        time.sleep(0.3)

    return results


def _build_query(blind_spot: str, stock_name: str) -> str:
    """根据盲点描述构建搜索查询词。"""
    core = blind_spot.split("（")[0].split("(")[0].strip()
    if stock_name:
        return f"{stock_name} {core}"
    return f"{core} A股 最新"


def _ddg_lite_search(query: str, max_results: int = 5) -> list[dict]:
    """使用 DuckDuckGo Lite HTML 版搜索（对中文支持好，无需 JS）。"""
    try:
        url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        # DDG Lite: link row → snippet row 交替排列
        current_title = None
        current_href = None
        for row in soup.find_all("tr"):
            link = row.find("a", class_="result-link")
            if link:
                current_title = link.get_text(strip=True)
                current_href = link.get("href", "")
            snippet = row.find("td", class_="result-snippet")
            if snippet and current_title:
                body = snippet.get_text(strip=True)
                if body and len(body) > 10:
                    results.append({
                        "title": _clean_text(current_title),
                        "body": _clean_text(body),
                        "href": current_href,
                    })
                current_title = None

            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        logger.debug("DDG Lite 搜索失败 (%s): %s", query[:30], e)
        return []


def _clean_text(text: str) -> str:
    """清理搜索结果文本。"""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]
