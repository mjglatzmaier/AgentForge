from __future__ import annotations

from pathlib import Path


def test_arxiv_readme_covers_required_sections() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    readme = repo_root / "agents" / "arxiv_research" / "README.md"
    text = readme.read_text(encoding="utf-8")

    assert "Determinism boundary" in text
    assert "Replay mode" in text
    assert "How to extend this agent" in text
