"""Tests for per-tool independent trace records and feedback ingestion."""

import json
from types import SimpleNamespace

import pytest


def test_append_profile_run_writes_trace_contract(tmp_path):
    from autoresearch_researcher.orchestrator import append_profile_run

    append_profile_run(tmp_path, {
        "day": "2026-05-28",
        "run_id": "2026-05-29-test",
        "slug": "tool-a",
        "name": "Tool A",
        "url": "https://example.com/tool-a",
        "status": "accepted",
        "weave_call_id": "call-123",
        "trace_url": "https://wandb.ai/call-123",
        "profiler_prompt_hash": "abc123",
    })

    rows = [json.loads(line) for line in (tmp_path / "_profile_runs.jsonl").read_text().splitlines()]
    assert rows == [{
        "day": "2026-05-28",
        "run_id": "2026-05-29-test",
        "slug": "tool-a",
        "name": "Tool A",
        "url": "https://example.com/tool-a",
        "status": "accepted",
        "weave_call_id": "call-123",
        "trace_url": "https://wandb.ai/call-123",
        "profiler_prompt_hash": "abc123",
    }]


def test_stage_run_config_names_agent_workflow():
    from autoresearch_researcher.orchestrator import stage_run_config

    config = stage_run_config(
        workflow_name="stage2_profile_tool-a",
        day="2026-05-28",
        run_id="run-123",
        stage="profiling",
        trace_id="trace_123",
        metadata={"tool_name": "Tool A"},
    )

    assert config.workflow_name == "stage2_profile_tool-a"
    assert config.trace_id == "trace_123"
    assert config.group_id == "run-123"
    assert config.trace_metadata == {
        "day": "2026-05-28",
        "run_id": "run-123",
        "stage": "profiling",
        "tool_name": "Tool A",
    }


def test_patch_weave_agent_span_names_names_task_and_turn_spans():
    from agents.tracing import TaskSpanData, TurnSpanData
    from weave.integrations.openai_agents import openai_agents as weave_openai_agents

    from autoresearch_researcher.orchestrator import patch_weave_agent_span_names

    patch_weave_agent_span_names()

    task_span = SimpleNamespace(span_data=TaskSpanData(name="stage1_discovery"))
    turn_span = SimpleNamespace(span_data=TurnSpanData(turn=2, agent_name="DiscoveryAgent"))

    assert weave_openai_agents._call_name(task_span) == "stage1_discovery"
    assert weave_openai_agents._call_name(turn_span) == "DiscoveryAgent turn 2"


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
        span_data=TaskSpanData(name="stage1_discovery"),
    )
    turn_span = SimpleNamespace(
        trace_id="trace-1",
        span_id="turn-1",
        parent_id="task-1",
        span_data=TurnSpanData(turn=0, agent_name="DiscoveryAgent"),
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

    tool_span = SimpleNamespace(
        trace_id="trace-1",
        span_id="tool-1",
        parent_id="turn-1",
    )

    assert processor._get_parent_call(tool_span) is agent_call


def test_render_discovery_review_markdown_lists_candidates():
    from autoresearch_researcher.orchestrator import render_discovery_review_markdown

    markdown = render_discovery_review_markdown(
        candidates=[{
            "name": "Tool A",
            "url": "https://example.com/tool-a",
            "category": "ml-experiment-automation",
            "description": "Runs experiments.",
        }],
        rejections=[{
            "name": "Search Only",
            "url": "https://example.com/search",
            "category": "deep-research",
            "rejection_reason": "Searches and summarizes only.",
        }],
    )

    assert "# Discovery Results" in markdown
    assert "| Tool A | https://example.com/tool-a | ml-experiment-automation | unknown | Runs experiments. |" in markdown
    assert "Rejected During Discovery" in markdown
    assert "Searches and summarizes only." in markdown


def test_discovery_agent_output_contains_review_markdown():
    from agents.tracing import AgentSpanData

    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    processor = AutoresearchWeaveTracingProcessor()
    processor._discovery_candidates["trace-1"] = [{
        "name": "Tool A",
        "url": "https://example.com/tool-a",
        "category": "ml-experiment-automation",
        "description": "Runs experiments.",
    }]
    span = SimpleNamespace(
        trace_id="trace-1",
        span_data=AgentSpanData(
            name="DiscoveryAgent",
            tools=["search_web", "save_candidate_tool"],
            handoffs=[],
            output_type="str",
        ),
    )

    data = processor._agent_log_data(span)

    assert data["outputs"]["candidate_count"] == 1
    assert "Tool A" in data["outputs"]["review_markdown"]
    assert data["outputs"]["candidate_names"] == ["Tool A"]
    assert data["outputs"]["candidate_urls"] == ["https://example.com/tool-a"]


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
    assert output["profile_path"] == "daily_runs/_registry/profiles/tool-a.md"
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
    assert "Primary URL: https://example.com/tool-a" in output["profile_review_markdown"]
    assert "Curated list only." in output["profile_review_markdown"]


def test_writer_review_output_contains_draft_and_table():
    from autoresearch_researcher.orchestrator import writer_review_output

    table = "| Tool Name | License |\n|---|---|\n| Tool A | MIT |\n"
    output = writer_review_output(
        draft_markdown="# Draft\n\nBody",
        comparison_table_markdown=table,
    )

    assert output["tool_count"] == 1
    assert output["draft_markdown"] == "# Draft\n\nBody"
    assert "Writer Output Review" in output["writer_review_markdown"]
    assert "| Tool A | MIT |" in output["writer_review_markdown"]


def test_processor_trace_end_merges_registered_review_output(monkeypatch):
    from autoresearch_researcher import orchestrator
    from autoresearch_researcher.orchestrator import AutoresearchWeaveTracingProcessor

    finished = {}

    class FakeClient:
        def finish_call(self, call, output):
            finished["call"] = call
            finished["output"] = output

    processor = AutoresearchWeaveTracingProcessor()
    processor._trace_data["trace-1"] = {"metrics": {}, "metadata": {"stage": "profiling"}}
    processor._trace_calls["trace-1"] = object()
    processor._profiler_profiles["trace-1"] = {
        "slug": "tool-a",
        "name": "Tool A",
        "github_url": "https://github.com/example/tool-a",
    }
    monkeypatch.setattr(orchestrator, "get_weave_client", lambda: FakeClient())
    trace = SimpleNamespace(trace_id="trace-1", name="stage2_profile_tool-a")

    processor.on_trace_end(trace)

    assert finished["output"]["status"] == "completed"
    assert finished["output"]["verdict"] == "accepted"
    assert "profile_review_markdown" in finished["output"]


def test_parse_tool_input_accepts_json_string():
    from autoresearch_researcher.orchestrator import parse_tool_input

    assert parse_tool_input('{"name": "Tool A"}') == {"name": "Tool A"}
    assert parse_tool_input("not-json") == {}


def test_profile_status_from_files_detects_accepted_and_rejected(tmp_path):
    from autoresearch_researcher.orchestrator import _profile_status_from_files

    (tmp_path / "_new_candidates.jsonl").write_text(
        json.dumps({"slug": "accepted-tool", "name": "Accepted Tool"}) + "\n"
    )
    accepted = _profile_status_from_files(
        tmp_path,
        candidate_name="Accepted Tool",
        new_before=0,
        updated_before=0,
        rejected_before=0,
    )
    assert accepted["status"] == "accepted"
    assert accepted["slug"] == "accepted-tool"

    (tmp_path / "_rejected_profiles.jsonl").write_text(
        json.dumps({
            "slug": "rejected-tool",
            "name": "Rejected Tool",
            "rejection_reason": "Deep research only",
        }) + "\n"
    )
    rejected = _profile_status_from_files(
        tmp_path,
        candidate_name="Rejected Tool",
        new_before=1,
        updated_before=0,
        rejected_before=0,
    )
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "Deep research only"


@pytest.mark.asyncio
async def test_dry_run_writes_profile_runs_and_prompt_hashes(tmp_path):
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
    assert metadata["prompt_refs"] == {"discovery": None, "profiler": None, "writer": None}
    assert set(metadata["prompt_hashes"]) == {"discovery", "profiler", "writer"}

    rows = [json.loads(line) for line in (tmp_path / "_profile_runs.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert {row["status"] for row in rows} == {"accepted"}
    assert all(row["run_id"] == metadata["run_id"] for row in rows)
    assert all(row["workflow_name"].startswith("stage2_profile_") for row in rows)
    assert all(row["search_backend"] == "serper" for row in rows)
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "items").exists()
    assert (tmp_path / "raw" / "run_metadata.json").exists()


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
