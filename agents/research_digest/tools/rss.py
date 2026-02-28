from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from agents.research_digest.tools.models import RSSItem


def fetch(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    config = ctx.get("config", {})
    feed_urls = list(config.get("feed_urls", []))
    if "feed_url" in config:
        feed_urls.append(str(config["feed_url"]))

    items: list[RSSItem] = []
    for feed_url in feed_urls:
        response = httpx.get(str(feed_url), timeout=20.0)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        channel_items = root.findall("./channel/item")
        for raw_item in channel_items:
            title = _clean(raw_item.findtext("title", ""))
            url = _clean(raw_item.findtext("link", ""))
            snippet = _clean(raw_item.findtext("description", ""))[:400]
            published = _clean(raw_item.findtext("pubDate", ""))
            items.append(RSSItem(title=title, url=url, snippet=snippet, published=published))

    output_path = outputs_dir / "rss_docs.json"
    output_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in items], indent=2),
        encoding="utf-8",
    )
    return {
        "outputs": [{"name": "rss_docs", "type": "json", "path": "outputs/rss_docs.json"}],
        "metrics": {"count": len(items), "feeds": len(feed_urls)},
    }


def _clean(value: str) -> str:
    return " ".join(value.split())
