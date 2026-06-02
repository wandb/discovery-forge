"""US6: Citation integrity tests."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


# ── Source schema ─────────────────────────────────────────────────────────────

def test_source_schema_fields():
    from autoresearch_researcher.schemas.sources import Source
    s = Source(
        id=1,
        url="https://example.com",
        title="Example Paper",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        used_in=["tool-a"],
    )
    assert s.id == 1
    assert s.used_in == ["tool-a"]


def test_source_schema_used_in_is_list():
    from autoresearch_researcher.schemas.sources import Source
    s = Source(
        id=2,
        url="https://github.com/example/tool",
        title="GitHub",
        fetched_at=datetime.now(timezone.utc),
        used_in=[],
    )
    assert isinstance(s.used_in, list)


# ── save_source / load_sources persistence ────────────────────────────────────

def test_save_source_writes_jsonl(tmp_path):
    from autoresearch_researcher.schemas.sources import Source
    from autoresearch_researcher.tools.persistence import save_source, load_sources

    sources_file = tmp_path / "sources.jsonl"
    s = Source(
        id=1,
        url="https://arxiv.org/abs/2025.00001",
        title="Test Paper",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        used_in=["test-tool"],
    )
    save_source(s, sources_file)

    assert sources_file.exists()
    lines = sources_file.read_text().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["id"] == 1
    assert data["url"] == "https://arxiv.org/abs/2025.00001"


def test_load_sources_round_trips(tmp_path):
    from autoresearch_researcher.schemas.sources import Source
    from autoresearch_researcher.tools.persistence import save_source, load_sources

    sources_file = tmp_path / "sources.jsonl"
    for i in range(3):
        s = Source(
            id=i + 1,
            url=f"https://example.com/{i}",
            title=f"Source {i}",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            used_in=["tool-x"],
        )
        save_source(s, sources_file)

    sources = load_sources(sources_file)
    assert len(sources) == 3
    assert sources[0].id == 1
    assert sources[2].url == "https://example.com/2"


def test_load_sources_empty_file_returns_empty(tmp_path):
    from autoresearch_researcher.tools.persistence import load_sources
    sources_file = tmp_path / "sources.jsonl"
    assert load_sources(sources_file) == []


# ── verify_citations logic ────────────────────────────────────────────────────

def test_verify_citations_clean_report_no_errors():
    from autoresearch_researcher.schemas.sources import Source
    from autoresearch_researcher.tools.citations import verify_citations

    sources = [
        Source(id=1, url="https://a.com", title="A", fetched_at=datetime.now(timezone.utc), used_in=["t"]),
        Source(id=2, url="https://b.com", title="B", fetched_at=datetime.now(timezone.utc), used_in=["t"]),
    ]
    report = "Some text [^1] and more text [^2] end."
    errors = verify_citations(report, sources)
    assert errors == []


def test_verify_citations_missing_source_id():
    from autoresearch_researcher.schemas.sources import Source
    from autoresearch_researcher.tools.citations import verify_citations

    sources = [
        Source(id=1, url="https://a.com", title="A", fetched_at=datetime.now(timezone.utc), used_in=["t"]),
    ]
    report = "Text cites [^1] and also [^99]."  # 99 not in sources
    errors = verify_citations(report, sources)
    assert any("99" in e or "Missing" in e for e in errors)


def test_verify_citations_orphan_source_warning():
    from autoresearch_researcher.schemas.sources import Source
    from autoresearch_researcher.tools.citations import verify_citations

    sources = [
        Source(id=1, url="https://a.com", title="A", fetched_at=datetime.now(timezone.utc), used_in=["t"]),
        Source(id=2, url="https://b.com", title="B", fetched_at=datetime.now(timezone.utc), used_in=["t"]),
    ]
    report = "Only cites [^1]."  # source 2 is orphaned
    errors = verify_citations(report, sources)
    assert any("orphan" in e.lower() or "2" in e for e in errors)


def test_verify_citations_empty_report_with_sources():
    from autoresearch_researcher.schemas.sources import Source
    from autoresearch_researcher.tools.citations import verify_citations

    sources = [
        Source(id=1, url="https://a.com", title="A", fetched_at=datetime.now(timezone.utc), used_in=["t"]),
    ]
    errors = verify_citations("No citations here.", sources)
    assert len(errors) > 0  # source 1 is orphaned


def test_verify_citations_no_sources_no_citations_is_clean():
    from autoresearch_researcher.tools.citations import verify_citations
    errors = verify_citations("No citations.", [])
    assert errors == []


def test_verify_citations_returns_list_of_strings():
    from autoresearch_researcher.tools.citations import verify_citations
    errors = verify_citations("Text [^999].", [])
    assert isinstance(errors, list)
    assert all(isinstance(e, str) for e in errors)


# ── Integration: sources tracking (retained citation subsystem) ──────────────

def test_source_registry_allocates_sequential_ids(tmp_path):
    from autoresearch_researcher.tools.citations import SourceRegistry

    registry = SourceRegistry(tmp_path / "sources.jsonl")
    id1 = registry.register(url="https://a.com", title="A", used_in="tool-a")
    id2 = registry.register(url="https://b.com", title="B", used_in="tool-a")
    id3 = registry.register(url="https://a.com", title="A", used_in="tool-b")  # dedup

    assert id1 == 1
    assert id2 == 2
    assert id3 == id1  # same URL → same ID


def test_source_registry_persists_to_jsonl(tmp_path):
    from autoresearch_researcher.tools.citations import SourceRegistry
    from autoresearch_researcher.tools.persistence import load_sources

    sources_file = tmp_path / "sources.jsonl"
    registry = SourceRegistry(sources_file)
    registry.register(url="https://a.com", title="A", used_in="tool-a")
    registry.register(url="https://b.com", title="B", used_in="tool-b")

    sources = load_sources(sources_file)
    assert len(sources) == 2
