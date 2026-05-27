"""ToolRegistry: global tool accumulation across daily runs."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ── RegistryEntry schema ──────────────────────────────────────────────────────

def test_registry_entry_schema_fields():
    from autoresearch_researcher.schemas.registry import RegistryEntry

    e = RegistryEntry(
        slug="example-tool",
        name="Example Tool",
        url="https://github.com/example/tool",
        first_seen_day="2026-05-19",
        last_updated_day="2026-05-19",
        last_profiled_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        stars=500,
        last_commit="2026-04-01T00:00:00Z",
    )
    assert e.slug == "example-tool"
    assert e.first_seen_day == "2026-05-19"


# ── ToolRegistry class ────────────────────────────────────────────────────────

def test_registry_load_creates_dirs(tmp_path):
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg = ToolRegistry.load(tmp_path / "_registry")
    assert (tmp_path / "_registry").exists()
    assert (tmp_path / "_registry" / "profiles").exists()


def test_registry_contains_url_normalization(tmp_path):
    from autoresearch_researcher.schemas.tool_profile import ToolProfile
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg = ToolRegistry.load(tmp_path / "_registry")
    assert reg.contains("https://github.com/example/tool") is False

    profile = _make_profile("example-tool", "Example", "https://github.com/example/tool")
    reg.add(profile, day="2026-05-19")

    # Same URL with trailing slash, different case → still matches
    assert reg.contains("https://github.com/example/tool") is True
    assert reg.contains("https://github.com/example/tool/") is True
    assert reg.contains("https://GITHUB.com/Example/Tool") is True
    # Different URL → no match
    assert reg.contains("https://github.com/example/other") is False


def test_registry_add_persists_profile_and_entry(tmp_path):
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg = ToolRegistry.load(tmp_path / "_registry")
    profile = _make_profile("example-tool", "Example", "https://github.com/example/tool")
    reg.add(profile, day="2026-05-19")

    # tools.jsonl entry written
    tools_jsonl = tmp_path / "_registry" / "tools.jsonl"
    assert tools_jsonl.exists()
    lines = tools_jsonl.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["slug"] == "example-tool"
    assert entry["first_seen_day"] == "2026-05-19"

    # profile markdown written
    profile_path = tmp_path / "_registry" / "profiles" / "example-tool.md"
    assert profile_path.exists()
    assert "Example" in profile_path.read_text()


def test_registry_add_duplicate_does_not_create_second_entry(tmp_path):
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg = ToolRegistry.load(tmp_path / "_registry")
    profile = _make_profile("example-tool", "Example", "https://github.com/example/tool")

    reg.add(profile, day="2026-05-19")
    reg.add(profile, day="2026-05-20")  # add again

    tools_jsonl = tmp_path / "_registry" / "tools.jsonl"
    lines = tools_jsonl.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["first_seen_day"] == "2026-05-19"  # preserved
    assert entry["last_updated_day"] == "2026-05-20"  # updated


def test_registry_load_existing_entries(tmp_path):
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg1 = ToolRegistry.load(tmp_path / "_registry")
    reg1.add(_make_profile("a", "A", "https://a.com"), day="2026-05-19")
    reg1.add(_make_profile("b", "B", "https://b.com"), day="2026-05-19")

    # Reload and verify state preserved
    reg2 = ToolRegistry.load(tmp_path / "_registry")
    assert reg2.contains("https://a.com")
    assert reg2.contains("https://b.com")
    assert len(reg2.get_all_entries()) == 2


def test_registry_update_metadata_records_change(tmp_path):
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg = ToolRegistry.load(tmp_path / "_registry")
    profile = _make_profile("example-tool", "Example", "https://github.com/example/tool", stars=100)
    reg.add(profile, day="2026-05-19")

    # Stars changed
    changed = reg.update_metadata(
        slug="example-tool", stars=150, last_commit="2026-05-01", day="2026-05-20"
    )
    assert changed is True

    # tools.jsonl reflects new stars
    reg2 = ToolRegistry.load(tmp_path / "_registry")
    entries = reg2.get_all_entries()
    assert entries[0].stars == 150
    assert entries[0].last_updated_day == "2026-05-20"


def test_registry_update_metadata_no_change_returns_false(tmp_path):
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg = ToolRegistry.load(tmp_path / "_registry")
    profile = _make_profile("example", "Example", "https://x.com", stars=100)
    reg.add(profile, day="2026-05-19")

    # Same stars and commit → no change
    changed = reg.update_metadata(slug="example", stars=100, last_commit=None, day="2026-05-20")
    assert changed is False


def test_registry_get_all_profiles(tmp_path):
    from autoresearch_researcher.tools.registry import ToolRegistry

    reg = ToolRegistry.load(tmp_path / "_registry")
    reg.add(_make_profile("a", "A", "https://a.com"), day="2026-05-19")
    reg.add(_make_profile("b", "B", "https://b.com"), day="2026-05-19")

    profiles = reg.get_all_profiles()
    assert len(profiles) == 2
    slugs = {p["slug"] for p in profiles}
    assert slugs == {"a", "b"}


# ── helper ────────────────────────────────────────────────────────────────────

def _make_profile(slug: str, name: str, url: str, stars: int = 100):
    from autoresearch_researcher.schemas.tool_profile import ToolProfile
    return ToolProfile(
        slug=slug,
        name=name,
        license="MIT",
        domains=["ml"],
        autonomy_level="Scientist",
        autonomy_rationale="test",
        interface="CLI",
        resource_requirements="single GPU",
        last_commit="2026-01-01",
        stars=stars,
        open_issues=0,
        pricing_note="free",
        key_limitations=[],
        github_url=url,
        paper_url=None,
        project_url=None,
        source_ids=[],
    )
