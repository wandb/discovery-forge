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
from autoresearch_researcher.tools.citations import verify_citations
from autoresearch_researcher.tools.persistence import load_sources


@pytest.mark.expensive
@pytest.mark.asyncio
async def test_e2e_smoke_dry_run(tmp_path):
    """
    Dry-run pipeline: no real LLM calls, validates all required outputs are generated.
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

    # ── 1. Output structure ───────────────────────────────────────────────────
    assert (tmp_path / "draft.md").exists(), "draft.md must exist"
    assert (tmp_path / "comparison_table.md").exists(), "comparison_table.md must exist"
    assert (tmp_path / "_candidates.jsonl").exists(), "_candidates.jsonl must exist"
    assert (tmp_path / "_profile_runs.jsonl").exists(), "_profile_runs.jsonl must exist"
    metadata = json.loads((tmp_path / "run_metadata.json").read_text())
    assert metadata["search_backend"] == "serpapi"

    # ── 2. tools/ has ≥3 in-scope profiles ────────────────────────────────────
    tools_dir = tmp_path / "tools"
    assert tools_dir.exists(), "tools/ directory must exist"
    tool_files = list(tools_dir.glob("*.md"))
    assert len(tool_files) >= 3, f"Expected ≥3 tool profiles, found {len(tool_files)}"

    # ── 3. comparison_table.md has all required columns ───────────────────────
    table = (tmp_path / "comparison_table.md").read_text()
    required_cols = ["Tool", "License", "Domain", "Autonomy", "Interface", "Resource", "Stars", "Price"]
    for col in required_cols:
        assert col.lower() in table.lower(), f"Missing column in comparison_table: {col}"

    # ── 4. Citation integrity passes ──────────────────────────────────────────
    draft = (tmp_path / "draft.md").read_text()
    sources_file = tmp_path / "sources.jsonl"
    sources = load_sources(sources_file)
    citation_errors = verify_citations(draft, sources)
    assert citation_errors == [], f"Citation integrity errors: {citation_errors}"

    # ── 5. No obvious OUT tools in results ────────────────────────────────────
    # Deep-research / general-search tools must not appear
    # (These are example OUT-category tool names per PRD, checked as exclusion)
    draft_lower = draft.lower()
    table_lower = table.lower()
    out_category_markers = ["gpt-researcher", "perplexity", "you.com", "tavily"]
    for marker in out_category_markers:
        assert marker not in draft_lower, f"OUT-scope tool marker found in draft: {marker}"
        assert marker not in table_lower, f"OUT-scope tool marker found in comparison_table: {marker}"

    # ── 6. Candidates file is valid JSONL ─────────────────────────────────────
    candidates_text = (tmp_path / "_candidates.jsonl").read_text().strip()
    assert candidates_text, "_candidates.jsonl must not be empty"
    candidate_count = 0
    for line in candidates_text.splitlines():
        data = json.loads(line)
        assert "name" in data and "url" in data and "category" in data
        candidate_count += 1
    assert candidate_count >= 3, f"Expected ≥3 candidates, found {candidate_count}"

    # ── 7. Per-tool trace contract is recorded ────────────────────────────────
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
        assert "profiler_prompt_hash" in run
        assert run["search_backend"] == "serpapi"


@pytest.mark.expensive
@pytest.mark.asyncio
async def test_e2e_smoke_tool_profiles_are_in_scope(tmp_path):
    """All generated tool profiles in dry-run must be experiment-automation (not deep research)."""
    from autoresearch_researcher.agents.profiler import is_experiment_automation
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
