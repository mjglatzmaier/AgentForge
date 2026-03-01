# ArXiv Research Agent

This example agent demonstrates a deterministic batch workflow for ingesting ArXiv papers, synthesizing structured outputs, and rendering a markdown report.

## Determinism boundary

The determinism boundary is external ingest: live mode may fetch fresh data from `export.arxiv.org`, while replay mode consumes snapshot artifacts (`raw_feed.xml`, `papers_raw.json`) only.

## Replay mode

Replay mode is the verification contract for repeatability in this agent:
- ingest skips network and requires snapshot inputs
- synthesis uses stable prompt ordering and deterministic replay defaults
- test fixtures compare produced `digest.json` to an expected deterministic output

## How to extend this agent

1. Add new schema fields in `models.py` and update tests first.
2. Extend ingest/synthesis/render modules while preserving manifest-indexed artifact handoff.
3. Add replay fixtures and tests for any new behavior that affects output determinism.
