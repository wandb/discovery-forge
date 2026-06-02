"""Tests for per-tool research trace records, review output, and dry-run feed."""

import json
from types import SimpleNamespace

import pytest


def test_append_profile_run_writes_trace_contract(tmp_path):
    from autoresearch_researcher.orchestrator import append_profile_run

    record = {
        "day": "2026-05-28",
        "run_id": "2026-05-29-test",
        "slug": "tool-a",
        "name": "Tool A",
        "url": "https://example.com/tool-a",
        "status": "accepted",
        "weave_call_id": "call-123",
        "trace_url": "https://wandb.ai/call-123",
        "researcher_prompt_hash": "abc123",
    }
    append_profile_run(tmp_path, record)

    rows = [json.loads(line) for line in (tmp_path / "_profile_runs.jsonl").read_text().splitlines()]
    assert rows == [record]


def test_stage_run_config_names_research_workflow():
    from autoresearch_researcher.orchestrator import stage_run_config

    config = stage_run_config(
        workflow_name="stage_research_1",
        day="2026-05-28",
        run_id="run-123",
        stage="research",
        trace_id="trace_123",
        metadata={"iteration": 1},
    )

    assert config.workflow_name == "stage_research_1"
    assert config.trace_id == "trace_123"
    assert config.group_id == "run-123"
    assert config.trace_metadata == {
        "day": "2026-05-28",
        "run_id": "run-123",
        "stage": "research",
        "iteration": 1,
    }


def test_render_research_prompt_includes_query_pool_hint_and_recency():
    from autoresearch_researcher.orchestrator import render_research_prompt

    prompt = render_research_prompt(
        day="2026-05-28",
        exclusion_block="- Known Tool (https://example.com/known)",
        iteration=1,
        recency="month",
    )

    assert "Iteration: 1" in prompt
    assert "Query Example Pool" in prompt
    assert "write your own search queries" in prompt
    assert "Known Tool" in prompt
    assert "last month" in prompt
    assert "Search budget" in prompt


def test_render_research_prompt_keeps_iteration_number_for_repeated_runs():
    from autoresearch_researcher.orchestrator import render_research_prompt

    prompt = render_research_prompt(
        day="2026-05-28",
        exclusion_block="(none yet)",
        iteration=11,
    )

    assert "Iteration: 11" in prompt
    assert "Choose a different search angle than earlier runs when possible" in prompt


def test_patch_weave_agent_span_names_names_task_and_turn_spans():
    from agents.tracing import TaskSpanData, TurnSpanData
    from weave.integrations.openai_agents import openai_agents as weave_openai_agents

    from autoresearch_researcher.orchestrator import patch_weave_agent_span_names

    patch_weave_agent_span_names()

    task_span = SimpleNamespace(span_data=TaskSpanData(name="stage_research_1"))
    turn_span = SimpleNamespace(span_data=TurnSpanData(turn=2, agent_name="ResearcherAgent"))

    assert weave_openai_agents._call_name(task_span) == "stage_research_1"
    assert weave_openai_agents._call_name(turn_span) == "ResearcherAgent turn 2"


def test_autoresearch_processor_skips_task_and_turn_spans():
    from agents.tracing import TaskSpanData, TurnSpanData

    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    processor = AutoresearchWeaveTracingProcessor()
    root_call = SimpleNamespace(id="root-call")
    processor._trace_calls["trace-1"] = root_call

    task_span = SimpleNamespace(
        trace_id="trace-1",
        span_id="task-1",
        parent_id=None,
        span_data=TaskSpanData(name="stage_research_1"),
    )
    turn_span = SimpleNamespace(
        trace_id="trace-1",
        span_id="turn-1",
        parent_id="task-1",
        span_data=TurnSpanData(turn=0, agent_name="ResearcherAgent"),
    )

    processor.on_span_start(task_span)
    processor.on_span_end(task_span)
    processor.on_span_start(turn_span)
    processor.on_span_end(turn_span)

    assert processor._span_calls == {}
    assert processor._hidden_span_parent_calls["task-1"] is root_call
    assert processor._hidden_span_parent_calls["turn-1"] is root_call


def test_hidden_turn_children_are_reparented_to_agent_call():
    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    processor = AutoresearchWeaveTracingProcessor()
    root_call = SimpleNamespace(id="root-call")
    agent_call = SimpleNamespace(id="agent-call")
    processor._trace_calls["trace-1"] = root_call
    processor._hidden_span_parent_calls["turn-1"] = agent_call

    tool_span = SimpleNamespace(trace_id="trace-1", span_id="tool-1", parent_id="turn-1")

    assert processor._get_parent_call(tool_span) is agent_call


def test_profile_review_output_for_accepted_profile():
    from autoresearch_researcher.orchestrator import profile_review_output

    output = profile_review_output({
        "slug": "tool-a",
        "name": "Tool A",
        "autonomy_level": "Scientist",
        "autonomy_rationale": "Runs experiment loops.",
        "domains": ["ml"],
        "license": "MIT",
        "github_url": "https://github.com/example/tool-a",
        "key_limitations": ["Needs GPU"],
        "source_ids": [1],
    }, status="accepted")

    assert output["verdict"] == "accepted"
    assert output["tool_name"] == "Tool A"
    assert output["primary_url"] == "https://github.com/example/tool-a"
    assert output["github_url"] == "https://github.com/example/tool-a"
    assert output["paper_url"] is None
    assert output["project_url"] is None
    assert output["key_limitations"] == ["Needs GPU"]
    assert output["tags"] == ["github"]
    for removed_field in [
        "source_ids",
        "profile_path",
        "prompt_ref",
        "feed_item_id",
        "feed_item_path",
        "feed_dedupe_key",
        "feed_canonical_url",
        "feed_tags",
        "feed_manifest_path",
    ]:
        assert removed_field not in output
    assert "Tool Profile Review: Tool A" in output["profile_review_markdown"]
    assert "Needs GPU" in output["profile_review_markdown"]


def test_profile_review_output_for_rejected_profile():
    from autoresearch_researcher.orchestrator import profile_review_output

    output = profile_review_output({
        "slug": "tool-a",
        "name": "Tool A",
        "url": "https://example.com/tool-a",
        "rejection_reason": "Curated list only.",
    }, status="rejected")

    assert output["verdict"] == "rejected"
    assert output["primary_url"] == "https://example.com/tool-a"
    assert output["rejection_reason"] == "Curated list only."
    assert output["tags"] == []
    assert "feed_item_id" not in output
    assert "feed_item_path" not in output
    assert "Primary URL: https://example.com/tool-a" in output["profile_review_markdown"]
    assert "Curated list only." in output["profile_review_markdown"]


def test_research_agent_output_contains_review_markdown():
    from agents.tracing import AgentSpanData

    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    processor = AutoresearchWeaveTracingProcessor()
    processor._accepted_profiles["trace-1"] = {
        "slug": "tool-a",
        "name": "Tool A",
        "github_url": "https://github.com/example/tool-a",
        "key_limitations": ["Needs GPU"],
    }
    span = SimpleNamespace(
        trace_id="trace-1",
        span_data=AgentSpanData(
            name="ResearcherAgent",
            tools=["search_web", "save_tool_profile_tool"],
            handoffs=[],
            output_type="str",
        ),
    )

    data = processor._agent_log_data(span)

    assert data["outputs"]["verdict"] == "accepted"
    assert "Tool A" in data["outputs"]["profile_review_markdown"]


def test_processor_trace_end_merges_registered_review_output(monkeypatch):
    from autoresearch_researcher import orchestrator
    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    finished = {}

    class FakeClient:
        def finish_call(self, call, output):
            finished["call"] = call
            finished["output"] = output

    processor = AutoresearchWeaveTracingProcessor()
    processor._trace_data["trace-1"] = {"metrics": {}, "metadata": {"stage": "research"}}
    processor._trace_calls["trace-1"] = object()
    processor._accepted_profiles["trace-1"] = {
        "slug": "tool-a",
        "name": "Tool A",
        "github_url": "https://github.com/example/tool-a",
    }
    monkeypatch.setattr(orchestrator, "get_weave_client", lambda: FakeClient())
    trace = SimpleNamespace(trace_id="trace-1", name="stage_research_1")

    processor.on_trace_end(trace)

    assert finished["output"]["status"] == "completed"
    assert finished["output"]["verdict"] == "accepted"
    assert "profile_review_markdown" in finished["output"]


def test_trace_end_relabels_research_call_with_tool_name(monkeypatch):
    from autoresearch_researcher import orchestrator
    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    renamed = {}

    class FakeCall:
        def set_display_name(self, name):
            renamed["name"] = name

    class FakeClient:
        def finish_call(self, call, output):
            pass

    processor = AutoresearchWeaveTracingProcessor()
    processor._trace_data["trace-1"] = {"metrics": {}, "metadata": {}}
    processor._trace_calls["trace-1"] = FakeCall()
    processor._accepted_profiles["trace-1"] = {"slug": "deepscientist", "name": "DeepScientist"}
    monkeypatch.setattr(orchestrator, "get_weave_client", lambda: FakeClient())

    processor.on_trace_end(SimpleNamespace(trace_id="trace-1", name="stage_research_3"))

    assert renamed["name"] == "research_DeepScientist"


def test_trace_end_skips_relabel_when_no_profile(monkeypatch):
    from autoresearch_researcher import orchestrator
    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    renamed = {}

    class FakeCall:
        def set_display_name(self, name):
            renamed["name"] = name

    class FakeClient:
        def finish_call(self, call, output):
            pass

    processor = AutoresearchWeaveTracingProcessor()
    processor._trace_data["trace-1"] = {"metrics": {}, "metadata": {}}
    processor._trace_calls["trace-1"] = FakeCall()
    # no accepted/rejected profile recorded -> report_no_new_tool / unknown
    monkeypatch.setattr(orchestrator, "get_weave_client", lambda: FakeClient())

    processor.on_trace_end(SimpleNamespace(trace_id="trace-1", name="stage_research_1"))

    assert "name" not in renamed


def test_parse_tool_input_accepts_json_string():
    from autoresearch_researcher.orchestrator import parse_tool_input

    assert parse_tool_input('{"name": "Tool A"}') == {"name": "Tool A"}
    assert parse_tool_input("not-json") == {}


def test_iteration_outcome_detects_accepted_rejected_and_no_new(tmp_path):
    from autoresearch_researcher.orchestrator import _iteration_outcome

    (tmp_path / "_new_candidates.jsonl").write_text(
        json.dumps({"slug": "accepted-tool", "name": "Accepted Tool"}) + "\n"
    )
    accepted = _iteration_outcome(
        tmp_path, new_before=0, updated_before=0, rejected_before=0, no_new_before=0
    )
    assert accepted["status"] == "accepted"
    assert accepted["slug"] == "accepted-tool"
    assert accepted["stop"] is False

    (tmp_path / "_rejected_profiles.jsonl").write_text(
        json.dumps({"slug": "rejected-tool", "name": "Rejected Tool", "rejection_reason": "Deep research only"}) + "\n"
    )
    rejected = _iteration_outcome(
        tmp_path, new_before=1, updated_before=0, rejected_before=0, no_new_before=0
    )
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "Deep research only"

    (tmp_path / "_no_new_tool.jsonl").write_text(json.dumps({"reason": "nothing left"}) + "\n")
    no_new = _iteration_outcome(
        tmp_path, new_before=1, updated_before=0, rejected_before=1, no_new_before=0
    )
    assert no_new["status"] == "no_new"
    assert no_new["stop"] is True


def test_build_exclusion_block_lists_registry_and_rejections(tmp_path):
    from autoresearch_researcher.orchestrator import build_exclusion_block
    from autoresearch_researcher.tools.registry import ToolRegistry

    registry = ToolRegistry.load(tmp_path / "_registry")
    (tmp_path / "_rejected_profiles.jsonl").write_text(
        json.dumps({"name": "Rejected Tool", "url": "https://example.com/rejected"}) + "\n"
    )

    block = build_exclusion_block(registry, tmp_path)
    assert "Rejected Tool" in block
    assert "https://example.com/rejected" in block


@pytest.mark.asyncio
async def test_dry_run_writes_profiles_runs_and_feed(tmp_path):
    from autoresearch_researcher.orchestrator import run_briefing

    await run_briefing(
        day="2026-05-28",
        output_dir=tmp_path,
        max_tools=3,
        max_cost_usd=2.0,
        dry_run=True,
    )

    metadata = json.loads((tmp_path / "run_metadata.json").read_text())
    assert metadata["profiled_count"] == 3
    assert metadata["accepted_count"] == 3
    assert metadata["rejected_count"] == 0
    assert metadata["search_backend"] == "serper"
    assert metadata["prompt_refs"] == {"researcher": None}
    assert set(metadata["prompt_hashes"]) == {"researcher"}

    rows = [json.loads(line) for line in (tmp_path / "_profile_runs.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert {row["status"] for row in rows} == {"accepted"}
    assert all(row["run_id"] == metadata["run_id"] for row in rows)
    assert all(row["workflow_name"].startswith("stage_research_") for row in rows)
    assert all(row["search_backend"] == "serper" for row in rows)
    assert all("search_lane_id" not in row for row in rows)
    assert all("search_lane_label" not in row for row in rows)

    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "items").exists()
    assert len(list((tmp_path / "items").glob("*.json"))) == 3
    assert (tmp_path / "raw" / "run_metadata.json").exists()
    # Writer artifacts are gone in the single-agent design.
    assert not (tmp_path / "draft.md").exists()
    assert not (tmp_path / "report.md").exists()
    assert not (tmp_path / "comparison_table.md").exists()


def test_feedback_ingest_writes_events_and_notes(tmp_path):
    from autoresearch_researcher.tools.feedback import ingest_feedback

    profile_run = {
        "day": "2026-05-28",
        "run_id": "run-1",
        "slug": "tool-a",
        "name": "Tool A",
        "url": "https://example.com/tool-a",
        "weave_call_id": "call-123",
    }
    (tmp_path / "_profile_runs.jsonl").write_text(json.dumps(profile_run) + "\n")

    feedback = SimpleNamespace(
        id="fb-1",
        feedback_type="wandb.annotation.profile_accuracy",
        payload={"profile_accuracy": 3, "prompt_issue_type": "source_selection"},
        call_id="call-123",
    )
    client = SimpleNamespace(get_feedback=lambda: [feedback])

    events = ingest_feedback(tmp_path, client)

    assert len(events) == 1
    assert (tmp_path / "feedback_events.jsonl").exists()
    notes = (tmp_path / "prompt_improvement_notes.md").read_text()
    assert "source_selection" in notes
