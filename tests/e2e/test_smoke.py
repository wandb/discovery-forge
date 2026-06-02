"""
E2E smoke test — dry-run pipeline validation.

Marked @pytest.mark.expensive:
  - Run only via: uv run pytest -m expensive
  - CI must skip these tests
  - max_cost_usd=2 enforced per AGENTS.md rule
"""

import json
from pathlib import Path

import pytest

from autoresearch_researcher.orchestrator import run_briefing


@pytest.mark.expensive
@pytest.mark.asyncio
async def test_e2e_smoke_dry_run(tmp_path):
    """
    Dry-run pipeline: no real LLM calls, validates the feed outputs are generated.
    Cost must remain $0 (dry-run mode).
    """
    day = "2026-05-29-test"

    await run_briefing(
        day=day,
        output_dir=tmp_path,
        max_tools=3,
        max_cost_usd=2.0,
        dry_run=True,
    )

    # ── 1. Feed output structure ──────────────────────────────────────────────
    assert (tmp_path / "manifest.json").exists(), "manifest.json must exist"
    assert (tmp_path / "items").exists(), "items/ directory must exist"
    assert (tmp_path / "raw").exists(), "raw/ directory must exist"
    assert (tmp_path / "_profile_runs.jsonl").exists(), "_profile_runs.jsonl must exist"
    metadata = json.loads((tmp_path / "run_metadata.json").read_text())
    assert metadata["search_backend"] == "serper"

    # Writer artifacts are gone in the single-agent design.
    assert not (tmp_path / "draft.md").exists()
    assert not (tmp_path / "report.md").exists()
    assert not (tmp_path / "comparison_table.md").exists()

    # ── 2. items/ has ≥3 feed items ───────────────────────────────────────────
    item_files = list((tmp_path / "items").glob("*.json"))
    assert len(item_files) >= 3, f"Expected ≥3 feed items, found {len(item_files)}"
    for item_file in item_files:
        item = json.loads(item_file.read_text())
        assert item["schemaVersion"] == 1
        assert item["id"]
        assert item["dedupeKey"]
        assert item["contentHash"]

    # ── 3. manifest references the items ──────────────────────────────────────
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["schemaVersion"] == 1
    assert manifest["runId"] == day
    assert len(manifest["items"]) == len(item_files)
    assert manifest["manifestHash"]

    # ── 4. No obvious OUT-scope tools appear ──────────────────────────────────
    manifest_text = (tmp_path / "manifest.json").read_text().lower()
    for marker in ["gpt-researcher", "perplexity", "you.com", "tavily"]:
        assert marker not in manifest_text, f"OUT-scope tool marker found: {marker}"

    # ── 5. Per-tool trace contract is recorded ────────────────────────────────
    profile_runs = [
        json.loads(line)
        for line in (tmp_path / "_profile_runs.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(profile_runs) >= 3
    for run in profile_runs:
        assert run["run_id"]
        assert run["status"] == "accepted"
        assert "weave_call_id" in run
        assert "researcher_prompt_hash" in run
        assert run["search_backend"] == "serper"


@pytest.mark.expensive
@pytest.mark.asyncio
async def test_e2e_smoke_tool_profiles_are_in_scope(tmp_path):
    """All generated tool profiles in dry-run must be experiment-automation (not deep research)."""
    from autoresearch_researcher.agents.researcher import is_experiment_automation
    import yaml

    await run_briefing(
        day="2026-05-29-test",
        output_dir=tmp_path,
        max_tools=3,
        max_cost_usd=2.0,
        dry_run=True,
    )

    tools_dir = tmp_path / "tools"
    for md_file in tools_dir.glob("*.md"):
        content = md_file.read_text()
        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        front = yaml.safe_load(parts[1])
        autonomy = front.get("autonomy_level", "")
        description = front.get("autonomy_rationale", "") + " " + front.get("slug", "")
        domains = front.get("domains", [])

        assert is_experiment_automation(
            autonomy_level=autonomy,
            description=description,
            domains=domains,
        ), f"Tool profile {md_file.name} failed scope filter"
