from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from agents.arxiv_research.models import ResearchPaper, ResearchRequest

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_and_snapshot(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    request = _request_from_context(ctx)
    if request.mode == "replay":
        raw_feed_text = _read_text_input(ctx, "raw_feed_xml")
        papers = _read_papers_input(ctx, "papers_raw")
    else:
        raw_feed_text = _fetch_atom_feed(request)
        papers = _parse_research_papers(raw_feed_text)

    (outputs_dir / "raw_feed.xml").write_text(raw_feed_text, encoding="utf-8")
    (outputs_dir / "papers_raw.json").write_text(
        json.dumps([paper.model_dump(mode="json") for paper in papers], indent=2),
        encoding="utf-8",
    )
    return {
        "outputs": [
            {"name": "raw_feed_xml", "type": "xml", "path": "outputs/raw_feed.xml"},
            {"name": "papers_raw", "type": "json", "path": "outputs/papers_raw.json"},
        ],
        "metrics": {"count": len(papers)},
    }


def _request_from_context(ctx: dict[str, Any]) -> ResearchRequest:
    config = dict(ctx.get("config", {}))
    return ResearchRequest(
        query=str(config.get("query", "cat:cs.AI")),
        max_results=int(config.get("max_results", 10)),
        categories=config.get("categories"),
        sort_by=str(config.get("sort_by", "relevance")),
        mode=str(config.get("mode", "live")),
    )


def _fetch_atom_feed(request: ResearchRequest) -> str:
    response = httpx.get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": _build_search_query(request),
            "start": 0,
            "max_results": request.max_results,
            "sortBy": request.sort_by,
            "sortOrder": "descending",
        },
        timeout=20.0,
    )
    response.raise_for_status()
    return response.text


def _build_search_query(request: ResearchRequest) -> str:
    if not request.categories:
        return request.query
    category_terms = [
        category if category.startswith("cat:") else f"cat:{category}"
        for category in request.categories
    ]
    return f"({request.query}) AND ({' OR '.join(category_terms)})"


def _parse_research_papers(feed_xml: str) -> list[ResearchPaper]:
    root = ET.fromstring(feed_xml)
    papers: list[ResearchPaper] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        entry_id = entry.findtext("atom:id", "", _ATOM_NS)
        title = " ".join(entry.findtext("atom:title", "", _ATOM_NS).split())
        abstract = " ".join(entry.findtext("atom:summary", "", _ATOM_NS).split())
        published = entry.findtext("atom:published", "", _ATOM_NS)
        authors = [
            " ".join((author.text or "").split())
            for author in entry.findall("atom:author/atom:name", _ATOM_NS)
            if (author.text or "").strip()
        ]
        categories = [
            str(category.attrib.get("term", "")).strip()
            for category in entry.findall("atom:category", _ATOM_NS)
            if str(category.attrib.get("term", "")).strip()
        ]
        papers.append(
            ResearchPaper(
                paper_id=_extract_paper_id(entry_id),
                title=title,
                authors=authors,
                abstract=abstract,
                categories=categories,
                published=published,
            )
        )
    return sorted(papers, key=lambda paper: (paper.published, paper.paper_id))


def _extract_paper_id(entry_id: str) -> str:
    normalized = entry_id.strip().rstrip("/")
    if "/abs/" in normalized:
        normalized = normalized.split("/abs/", maxsplit=1)[1]
    elif "/" in normalized:
        normalized = normalized.rsplit("/", maxsplit=1)[1]
    return normalized


def _read_text_input(ctx: dict[str, Any], artifact_name: str) -> str:
    artifact = _require_input_artifact(ctx, artifact_name)
    return Path(artifact["abs_path"]).read_text(encoding="utf-8")


def _read_papers_input(ctx: dict[str, Any], artifact_name: str) -> list[ResearchPaper]:
    artifact = _require_input_artifact(ctx, artifact_name)
    payload = json.loads(Path(artifact["abs_path"]).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"Replay artifact '{artifact_name}' must contain a JSON list.")
    return [ResearchPaper.model_validate(item) for item in payload]


def _require_input_artifact(ctx: dict[str, Any], artifact_name: str) -> dict[str, Any]:
    inputs = ctx.get("inputs", {})
    artifact = inputs.get(artifact_name)
    if artifact is None:
        raise KeyError(
            f"Replay mode requires snapshot input artifact '{artifact_name}'."
        )
    if not isinstance(artifact, dict):
        raise TypeError(f"Input artifact '{artifact_name}' must be a metadata dict.")
    abs_path = artifact.get("abs_path")
    if not isinstance(abs_path, str) or not abs_path:
        raise TypeError(f"Input artifact '{artifact_name}' must include non-empty 'abs_path'.")
    return dict(artifact)
