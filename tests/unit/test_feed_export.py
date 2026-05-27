import json
from pathlib import Path

import yaml


def _write_profile(tools_dir: Path, *, slug: str = "tool-a") -> None:
    tools_dir.mkdir(parents=True, exist_ok=True)
    front = {
        "slug": slug,
        "name": "Tool A",
        "license": "MIT",
        "domains": ["ml"],
        "autonomy_level": "Scientist",
        "autonomy_rationale": "Runs experiment loops.",
        "interface": "Python lib",
        "resource_requirements": "single GPU",
        "last_commit": "2026-05-01T00:00:00Z",
        "stars": 123,
        "open_issues": 4,
        "pricing_note": "Free",
        "key_limitations": ["Needs GPU"],
        "github_url": "https://github.com/example/tool-a",
        "paper_url": "https://arxiv.org/abs/2601.00001",
        "project_url": None,
        "source_ids": [1],
    }
    body = "# Tool A\n\nTool A automates ML experiments.\n"
    (tools_dir / f"{slug}.md").write_text(
        "---\n" + yaml.dump(front, sort_keys=False) + "---\n\n" + body
    )


def _bootstrap_day_dir(day_dir: Path) -> None:
    (day_dir / "run_metadata.json").write_text(json.dumps({
        "day": "2026-05-28",
        "run_id": "run-1",
        "started_at": "2026-05-28T00:00:00+00:00",
        "finished_at": "2026-05-28T00:05:00+00:00",
    }))
    (day_dir / "draft.md").write_text("# Daily Briefing\n\nBody")
    (day_dir / "comparison_table.md").write_text("| Tool Name |\n|---|\n| Tool A |\n")
    (day_dir / "highlights.md").write_text("## Today's Highlights\n")
    (day_dir / "_candidates.jsonl").write_text(
        json.dumps({"name": "Tool A", "url": "https://github.com/example/tool-a"}) + "\n"
    )
    (day_dir / "_new_candidates.jsonl").write_text(
        json.dumps({"slug": "tool-a", "name": "Tool A"}) + "\n"
    )
    (day_dir / "_profile_runs.jsonl").write_text(
        json.dumps({"day": "2026-05-28", "slug": "tool-a"}) + "\n"
    )
    _write_profile(day_dir / "tools")


def test_build_feed_output_writes_manifest_items_report_and_raw(tmp_path):
    from autoresearch_researcher.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert manifest["schemaVersion"] == 1
    assert manifest["runId"] == "2026-05-28"
    assert manifest["runDate"] == "2026-05-28"
    assert manifest["cadence"] == "daily"
    assert manifest["sourceSha"] == "abc123"
    assert manifest["delta"]["newItemIds"] == ["tool-a"]
    assert manifest["items"][0]["changeStatus"] == "new"
    assert manifest["manifestHash"]

    manifest_file = json.loads((day_dir / "manifest.json").read_text())
    item_file = json.loads((day_dir / "items" / "tool-a.json").read_text())
    assert manifest_file["manifestHash"] == manifest["manifestHash"]
    assert item_file["schemaVersion"] == 1
    assert item_file["id"] == "tool-a"
    assert item_file["canonicalUrl"] == "https://github.com/example/tool-a"
    assert item_file["dedupeKey"].startswith("url:")
    assert item_file["title"] == "Tool A"
    assert item_file["summary"] == "Tool A automates ML experiments."
    assert item_file["tags"] == ["academic", "github"]
    assert item_file["metadata"]["githubStars"] == 123
    assert item_file["metadata"]["keyLimitation"] == "Needs GPU"
    assert item_file["contentHash"]

    assert (day_dir / "report.md").read_text() == "# Daily Briefing\n\nBody"
    assert (day_dir / "raw" / "candidates.jsonl").exists()
    assert (day_dir / "raw" / "new_candidates.jsonl").exists()
    assert (day_dir / "raw" / "comparison_table.md").exists()
    assert (day_dir / "raw" / "run_metadata.json").exists()


def test_build_feed_output_hashes_are_stable(tmp_path):
    from autoresearch_researcher.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    first = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")
    second = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert second["manifestHash"] == first["manifestHash"]
    first_item = json.loads((day_dir / "items" / "tool-a.json").read_text())
    second_item = json.loads((day_dir / "items" / "tool-a.json").read_text())
    assert second_item["contentHash"] == first_item["contentHash"]


def test_build_feed_output_dedupes_items_by_dedupe_key(tmp_path):
    from autoresearch_researcher.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    _write_profile(day_dir / "tools", slug="tool-a-duplicate")
    (day_dir / "_updated_tools.jsonl").write_text(
        json.dumps({"slug": "tool-a", "name": "Tool A"}) + "\n"
    )

    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    dedupe_keys = [item["dedupeKey"] for item in manifest["items"]]
    assert len(dedupe_keys) == len(set(dedupe_keys))
    assert len(manifest["items"]) == 1
    assert manifest["items"][0]["id"] == "tool-a"
    assert manifest["delta"]["newItemIds"] == []
    assert manifest["delta"]["updatedItemIds"] == ["tool-a"]
