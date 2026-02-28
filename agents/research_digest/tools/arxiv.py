from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from agents.research_digest.tools.models import ArxivPaper

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    config = ctx.get("config", {})
    query = str(config.get("query", "cat:cs.AI"))
    max_results = int(config.get("max_results", 10))
    feed_url = str(config.get("feed_url", "https://export.arxiv.org/api/query"))
    response = httpx.get(
        feed_url,
        params={
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        timeout=20.0,
    )
    response.raise_for_status()

    root = ET.fromstring(response.text)
    papers: list[ArxivPaper] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        title = " ".join((entry.findtext("atom:title", "", _ATOM_NS)).split())
        abstract = " ".join((entry.findtext("atom:summary", "", _ATOM_NS)).split())
        url = entry.findtext("atom:id", "", _ATOM_NS)
        published = entry.findtext("atom:published", "", _ATOM_NS)
        authors = [
            " ".join((author.text or "").split())
            for author in entry.findall("atom:author/atom:name", _ATOM_NS)
            if (author.text or "").strip()
        ]
        papers.append(
            ArxivPaper(
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                published=published,
            )
        )

    output_path = outputs_dir / "arxiv_docs.json"
    output_path.write_text(
        json.dumps([paper.model_dump(mode="json") for paper in papers], indent=2),
        encoding="utf-8",
    )
    return {
        "outputs": [{"name": "arxiv_docs", "type": "json", "path": "outputs/arxiv_docs.json"}],
        "metrics": {"count": len(papers)},
    }
