"""Tests for the Weave-versioned ResearcherAgent model wrapper."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def test_researcher_agent_model_predict_returns_saved_profile(tmp_path):
    from discovery_forge.agents.researcher_model import ResearcherAgentModel
    from discovery_forge.schemas.tool_profile import ToolProfile

    captured = {}

    def fake_build_researcher_agent(**kwargs):
        captured.update(kwargs)
        return object()

    async def fake_run(agent, input, max_turns):
        captured["runner_input"] = input
        captured["max_turns"] = max_turns
        captured["save_tool_profile_callback"](
            ToolProfile(
                slug="tool-a",
                name="Tool A",
                license="Apache-2.0",
                domains=["ml"],
                autonomy_level="Scientist",
                autonomy_rationale="Runs experiments.",
                interface="CLI",
                resource_requirements="GPU",
                last_commit=None,
                stars=None,
                open_issues=None,
                pricing_note="unknown",
                key_limitations=["Requires compute"],
                github_url="https://github.com/example/tool-a",
                paper_url=None,
                project_url=None,
                source_ids=[0],
            )
        )
        return SimpleNamespace(final_output="done", raw_responses=[])

    model = ResearcherAgentModel(
        search_backend="serper",
        recency="month",
        max_turns=40,
        prompt_object_name="researcher_instructions",
        researcher_prompt_ref="weave:///prompt:v1",
        researcher_prompt_hash="hash123",
    ).bind_runtime(
        output_dir=tmp_path,
        instructions_override="Prompt",
        capture_persistence=True,
    )

    with patch(
        "discovery_forge.agents.researcher_model.build_researcher_agent",
        side_effect=fake_build_researcher_agent,
    ), patch(
        "discovery_forge.agents.researcher_model.Runner.run",
        new=AsyncMock(side_effect=fake_run),
    ):
        output = asyncio.run(
            model.predict(
                input_tool_name="Tool A",
                input_candidate_url="https://github.com/example/tool-a",
                input_candidate_description="Runs experiments.",
            )
        )

    assert set(output) == {
        "profile_review_markdown",
        "verdict",
        "tool_name",
        "primary_url",
        "urls",
        "summary",
        "search_queries",
        "search",
        "run",
        "scope_status",
        "verdict_reason",
        "final_output",
        "profile",
    }
    assert output["verdict"] == "accepted"
    assert output["scope_status"] == "accepted"
    assert output["verdict_reason"] is None
    assert output["final_output"] == "done"
    assert output["tool_name"] == "Tool A"
    assert output["profile"]["slug"] == "tool-a"
    assert "Tool Profile Review: Tool A" in output["profile_review_markdown"]
    assert output["run"]["researcher_prompt_ref"] == "weave:///prompt:v1"
    assert output["run"]["researcher_model_ref"] is None
    assert output["summary"]["autonomy_level"] == "Scientist"
    assert captured["instructions_override"] == "Prompt"
    assert captured["recency"] == "month"
    assert captured["max_turns"] == 40
    assert "Profile this specific tool candidate" in captured["runner_input"]


def test_researcher_agent_model_predict_returns_review_output_for_daily_run(tmp_path):
    from discovery_forge.agents.researcher_model import ResearcherAgentModel
    from discovery_forge.schemas.tool_profile import ToolProfile

    captured = {}

    def fake_build_researcher_agent(**kwargs):
        captured.update(kwargs)
        return object()

    async def fake_run(agent, input, max_turns, run_config=None):
        captured["search_query_observer"]("site:github.com experiment automation")
        captured["save_tool_profile_observer"](
            ToolProfile(
                slug="tool-a",
                name="Tool A",
                license="Apache-2.0",
                domains=["ml"],
                autonomy_level="Scientist",
                autonomy_rationale="Runs experiments.",
                interface="CLI",
                resource_requirements="GPU",
                last_commit=None,
                stars=None,
                open_issues=None,
                pricing_note="unknown",
                key_limitations=["Requires compute"],
                github_url="https://github.com/example/tool-a",
                paper_url=None,
                project_url=None,
                source_ids=[0],
            )
        )
        return SimpleNamespace(final_output="done", raw_responses=[])

    model = ResearcherAgentModel(
        search_backend="serper",
        recency="month",
        max_turns=40,
        prompt_object_name="researcher_instructions",
        researcher_prompt_ref="weave:///prompt:v1",
        researcher_prompt_hash="hash123",
    ).bind_runtime(output_dir=tmp_path, instructions_override="Prompt")
    model._researcher_model_ref = "weave:///model:v1"

    with patch(
        "discovery_forge.agents.researcher_model.build_researcher_agent",
        side_effect=fake_build_researcher_agent,
    ), patch(
        "discovery_forge.agents.researcher_model.Runner.run",
        new=AsyncMock(side_effect=fake_run),
    ):
        output = asyncio.run(
            model.predict(
                research_prompt="Find one tool.",
                day="2026-06-14",
                run_id="run-1",
                workflow_name="research_run_1",
            )
        )

    assert captured["save_tool_profile_callback"] is None
    assert set(output) == {
        "profile_review_markdown",
        "verdict",
        "tool_name",
        "primary_url",
        "urls",
        "summary",
        "search_queries",
        "search",
        "run",
        "scope_status",
        "verdict_reason",
        "final_output",
        "profile",
    }
    assert output["verdict"] == "accepted"
    assert output["scope_status"] == "accepted"
    assert output["verdict_reason"] is None
    assert output["final_output"] == "done"
    assert output["tool_name"] == "Tool A"
    assert output["profile"]["slug"] == "tool-a"
    assert output["search_queries"] == ["site:github.com experiment automation"]
    assert output["search"] == {"backend": "serper", "recency": "month"}
    assert output["run"] == {
        "workflow_name": "research_run_1",
        "researcher_prompt_ref": "weave:///prompt:v1",
        "researcher_prompt_hash": "hash123",
        "researcher_model_ref": "weave:///model:v1",
    }
    assert "Tool Profile Review: Tool A" in output["profile_review_markdown"]


def test_publish_researcher_model_uses_stable_object_name(monkeypatch):
    from discovery_forge.agents import researcher_model

    model = researcher_model.ResearcherAgentModel(
        search_backend="serper",
        recency="month",
        max_turns=40,
        prompt_object_name="researcher_instructions",
        researcher_prompt_ref="weave:///prompt:v1",
        researcher_prompt_hash="hash123",
    )

    class FakeRef:
        def uri(self):
            return "weave:///entity/project/object/ResearcherAgentModel:v1"

    published = {}

    def fake_publish(obj, name):
        published["obj"] = obj
        published["name"] = name
        return FakeRef()

    monkeypatch.setattr(researcher_model.weave, "publish", fake_publish)

    ref = researcher_model.publish_researcher_model(model)

    assert published == {"obj": model, "name": "ResearcherAgentModel"}
    assert ref == "weave:///entity/project/object/ResearcherAgentModel:v1"
    assert model.researcher_model_ref == ref
