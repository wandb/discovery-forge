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
        "autonomy_rationale": "Designs experiments, edits code, runs training, and iterates on results.",
        "interface": "Python lib",
        "resource_requirements": "single GPU",
        "last_commit": "2026-05-01T00:00:00Z",
        "stars": 123,
        "open_issues": 4,
        "pricing_note": "Free",
        "key_limitations": ["Needs GPU"],
        "page_title": "example/tool-a",
        "page_description": "Source description from GitHub.",
        "page_image_url": "https://example.com/social-preview.png",
        "page_published_at": "2026-01-02T00:00:00Z",
        "source_updated_at": "2026-05-02T00:00:00Z",
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
    (day_dir / "_candidates.jsonl").write_text(
        json.dumps({"name": "Tool A", "url": "https://github.com/example/tool-a"}) + "\n"
    )
    (day_dir / "_new_candidates.jsonl").write_text(
        json.dumps({"slug": "tool-a", "name": "Tool A"}) + "\n"
    )
    (day_dir / "_profile_runs.jsonl").write_text(
        json.dumps({
            "day": "2026-05-28",
            "slug": "tool-a",
            "weave_call_id": "call-tool-a",
            "agent_trace_id": "trace-tool-a",
            "trace_url": "https://wandb.ai/example/project/weave/traces/trace-tool-a",
            "workflow_name": "research_Tool A",
        }) + "\n"
    )
    _write_profile(day_dir / "tools")


def test_build_feed_output_writes_manifest_items_and_raw(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert manifest["schemaVersion"] == 1
    assert manifest["runId"] == "2026-05-28"
    assert manifest["runDate"] == "2026-05-28"
    assert manifest["cadence"] == "daily"
    assert manifest["sourceSha"] == "abc123"
    assert manifest["previousSourceSha"] is None
    assert manifest["sourceRange"] == {
        "fromShaExclusive": None,
        "toShaInclusive": "abc123",
    }
    assert manifest["weaveTraceId"] is None
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
    assert item_file["pageTitle"] == "example/tool-a"
    assert item_file["pageMetadata"] == {
        "description": "Source description from GitHub.",
        "image": "https://example.com/social-preview.png",
        "siteName": "GitHub",
        "weave_agent_trace_id": "trace-tool-a",
        "weave_call_id": "call-tool-a",
        "weave_trace_url": "https://wandb.ai/example/project/weave/traces/trace-tool-a",
        "weave_workflow_name": "research_Tool A",
    }
    assert item_file["title"] == "Tool A"
    assert item_file["summary"] == (
        "A library for ML workflows that designs experiments, edits code, runs training, "
        "and iterates on results."
    )
    assert item_file["tags"] == ["academic", "github"]
    assert item_file["pagePublishedAt"] == "2026-01-02T00:00:00Z"
    assert item_file["sourceUpdatedAt"] == "2026-05-02T00:00:00Z"
    assert item_file["metadata"]["githubStars"] == 123
    assert item_file["metadata"]["keyLimitation"] == "Needs GPU"
    assert item_file["weaveTraceId"] == "call-tool-a"
    assert item_file["contentHash"]

    assert not (day_dir / "report.md").exists()
    assert (day_dir / "raw" / "candidates.jsonl").exists()
    assert (day_dir / "raw" / "new_candidates.jsonl").exists()
    assert (day_dir / "raw" / "run_metadata.json").exists()
    assert not (day_dir / "raw" / "comparison_table.md").exists()


def test_feed_metadata_for_profile_matches_manifest_item_projection():
    from discovery_forge.tools.feed import feed_metadata_for_profile

    metadata = feed_metadata_for_profile({
        "slug": "tool-a",
        "name": "Tool A",
        "github_url": "https://github.com/example/tool-a",
        "paper_url": "https://arxiv.org/abs/2601.00001",
        "domains": ["ml"],
    })

    assert metadata["feed_item_id"] == "tool-a"
    assert metadata["feed_item_path"] == "items/tool-a.json"
    assert metadata["feed_dedupe_key"].startswith("url:")
    assert metadata["feed_canonical_url"] == "https://github.com/example/tool-a"
    assert metadata["feed_tags"] == ["academic", "github"]
    assert metadata["feed_manifest_path"] == "manifest.json"


def test_build_feed_output_hashes_are_stable(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    first = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")
    second = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert second["manifestHash"] == first["manifestHash"]
    first_item = json.loads((day_dir / "items" / "tool-a.json").read_text())
    second_item = json.loads((day_dir / "items" / "tool-a.json").read_text())
    assert second_item["contentHash"] == first_item["contentHash"]


def test_build_feed_output_computes_delta_against_previous_manifest(tmp_path):
    from discovery_forge.tools.feed import build_feed_output, dedupe_key_for_url

    previous_day_dir = tmp_path / "2026-05-27"
    previous_day_dir.mkdir()
    previous_key = dedupe_key_for_url("https://github.com/example/tool-a", fallback_id="tool-a")
    previous_manifest = {
        "schemaVersion": 1,
        "runId": "2026-05-27",
        "runDate": "2026-05-27",
        "cadence": "daily",
        "sourceSha": "prevsha",
        "items": [
            {
                "id": "tool-a",
                "dedupeKey": previous_key,
                "path": "items/tool-a.json",
                "contentHash": "old-content-hash",
                "changeStatus": "new",
            },
            {
                "id": "removed-tool",
                "dedupeKey": "url:removed",
                "path": "items/removed-tool.json",
                "contentHash": "removed-content-hash",
                "changeStatus": "new",
            },
        ],
    }
    (previous_day_dir / "manifest.json").write_text(json.dumps(previous_manifest))

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert manifest["previousSourceSha"] == "prevsha"
    assert manifest["sourceRange"] == {
        "fromShaExclusive": "prevsha",
        "toShaInclusive": "abc123",
    }
    assert manifest["items"][0]["changeStatus"] == "updated"
    assert manifest["delta"] == {
        "newItemIds": [],
        "updatedItemIds": ["tool-a"],
        "removedItemIds": [],
    }


def test_build_feed_output_uses_explicit_previous_manifest_path(tmp_path):
    from discovery_forge.tools.feed import build_feed_output, dedupe_key_for_url

    backup_dir = tmp_path / "2026-05-28_backup_1"
    backup_dir.mkdir()
    previous_key = dedupe_key_for_url("https://github.com/example/tool-a", fallback_id="tool-a")
    (backup_dir / "manifest.json").write_text(json.dumps({
        "schemaVersion": 1,
        "runId": "2026-05-28",
        "runDate": "2026-05-28",
        "cadence": "daily",
        "sourceSha": "backupsha",
        "items": [{
            "id": "tool-a",
            "dedupeKey": previous_key,
            "path": "items/tool-a.json",
            "contentHash": "old-content-hash",
            "changeStatus": "new",
        }],
    }))

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    metadata_path = day_dir / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["previous_manifest_path"] = str(backup_dir / "manifest.json")
    metadata_path.write_text(json.dumps(metadata))

    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert manifest["previousSourceSha"] == "backupsha"
    assert manifest["sourceRange"]["fromShaExclusive"] == "backupsha"
    assert manifest["delta"]["updatedItemIds"] == ["tool-a"]


def test_build_feed_output_uses_generated_at_only_when_page_published_unknown(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    profile_path = day_dir / "tools" / "tool-a.md"
    profile = yaml.safe_load(profile_path.read_text().split("---", 2)[1])
    profile["page_published_at"] = None
    profile["source_updated_at"] = None
    profile["last_commit"] = None
    profile_path.write_text(
        "---\n"
        + yaml.dump(profile, sort_keys=False)
        + "---\n\n# Tool A\n\nTool A automates ML experiments.\n"
    )

    build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    item_file = json.loads((day_dir / "items" / "tool-a.json").read_text())
    assert item_file["pagePublishedAt"] == "2026-05-28T00:05:00+00:00"
    assert item_file["sourceUpdatedAt"] is None


def test_build_feed_output_summarizes_curated_repository_as_reference(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    profile_path = day_dir / "tools" / "tool-a.md"
    profile = yaml.safe_load(profile_path.read_text().split("---", 2)[1])
    profile["domains"] = ["agent memory"]
    profile["interface"] = "GitHub repository / curated paper list"
    profile["autonomy_rationale"] = (
        "This is a curated technical repository for agent memory rather than an execution engine. "
        "It organizes research on persistent memory, context management, and learning from experience."
    )
    profile_path.write_text(
        "---\n"
        + yaml.dump(profile, sort_keys=False)
        + "---\n\n# Tool A\n\nTool A automates ML experiments.\n"
    )

    build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    item_file = json.loads((day_dir / "items" / "tool-a.json").read_text())
    assert item_file["summary"] == (
        "A curated reference repository for agent memory workflows that organizes research "
        "on persistent memory, context management, and learning from experience."
    )


def test_build_feed_output_rewrites_named_description_into_action_phrase(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)

    profile_path = day_dir / "tools" / "tool-a.md"
    profile = yaml.safe_load(profile_path.read_text().split("---", 2)[1])
    profile["domains"] = ["autonomous agents"]
    profile["interface"] = "GitHub repository / research code"
    profile["autonomy_rationale"] = (
        "AgentEvolver is described as an end-to-end self-evolving training framework "
        "that unifies self-questioning and self-navigating."
    )
    profile_path.write_text(
        "---\n"
        + yaml.dump(profile, sort_keys=False)
        + "---\n\n# Tool A\n\nTool A automates ML experiments.\n"
    )

    build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    item_file = json.loads((day_dir / "items" / "tool-a.json").read_text())
    assert item_file["summary"] == (
        "An open-source project for autonomous agents workflows that provides an "
        "end-to-end self-evolving training framework that unifies self-questioning "
        "and self-navigating."
    )


def test_build_feed_output_dedupes_items_by_dedupe_key(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

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
    assert manifest["delta"]["newItemIds"] == ["tool-a"]
    assert manifest["delta"]["updatedItemIds"] == []


def test_build_feed_output_exports_only_daily_profiles_from_registry(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    class Registry:
        def __init__(self, profiles_dir: Path) -> None:
            self.profiles_dir = profiles_dir

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    registry_dir = tmp_path / "_registry" / "profiles"
    _write_profile(registry_dir, slug="tool-a")
    _write_profile(registry_dir, slug="old-tool")

    old_profile_path = registry_dir / "old-tool.md"
    old_profile = yaml.safe_load(old_profile_path.read_text().split("---", 2)[1])
    old_profile["name"] = "Old Tool"
    old_profile["github_url"] = "https://github.com/example/old-tool"
    old_profile_path.write_text(
        "---\n"
        + yaml.dump(old_profile, sort_keys=False)
        + "---\n\n# Old Tool\n\nOld Tool was found on an earlier day.\n"
    )

    manifest = build_feed_output(
        day_dir,
        registry=Registry(registry_dir),
        day="2026-05-28",
        source_sha="abc123",
    )

    assert [item["id"] for item in manifest["items"]] == ["tool-a"]
    assert (day_dir / "items" / "tool-a.json").exists()
    assert not (day_dir / "items" / "old-tool.json").exists()


def test_build_feed_output_does_not_use_source_sha_as_weave_trace_fallback(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    (day_dir / "_profile_runs.jsonl").write_text(
        json.dumps({"day": "2026-05-28", "slug": "other-tool", "weave_call_id": "call-other"})
        + "\n"
    )

    build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    item_file = json.loads((day_dir / "items" / "tool-a.json").read_text())
    assert item_file["weaveTraceId"] is None


def test_build_feed_output_removes_stale_item_files(tmp_path):
    from discovery_forge.tools.feed import build_feed_output

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    stale_item = day_dir / "items" / "stale-tool.json"
    stale_item.parent.mkdir()
    stale_item.write_text(json.dumps({"id": "stale-tool"}) + "\n")

    build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert not stale_item.exists()
