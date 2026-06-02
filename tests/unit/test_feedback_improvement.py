"""Tests for the LLM-driven prompt-only improvement proposer/applier (single prompt)."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from autoresearch_researcher.cli import app

runner = CliRunner()


def _event(*, name: str, note: str, slug: str | None = None) -> dict:
    return {
        "day": "2026-05-28",
        "run_id": "run-1",
        "name": name,
        "slug": slug or name.lower().replace(" ", "-"),
        "weave_call_id": "call-1",
        "feedback": {
            "feedback_type": "wandb.annotation.D20260528_Research",
            "payload": {"value": note},
        },
    }


def _write_feedback(day_dir: Path, events: list[dict]) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "feedback_events.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + ("\n" if events else "")
    )


def _bootstrap_instructions(instructions_dir: Path) -> None:
    instructions_dir.mkdir(parents=True, exist_ok=True)
    (instructions_dir / "researcher.md").write_text("# Researcher\nSeed researcher rules.\n")


def test_load_feedback_context_reads_all_artifacts(tmp_path):
    from autoresearch_researcher.tools.improvement import load_feedback_context

    _write_feedback(tmp_path, [_event(name="Tool A", note="Bad. Curated list.")])

    context = load_feedback_context(tmp_path)

    assert context.day == tmp_path.name
    assert len(context.feedback_events) == 1
    assert context.feedback_events[0]["name"] == "Tool A"


def test_annotation_target_prompt_routes_research_annotations():
    from autoresearch_researcher.tools.feedback import annotation_target_prompt

    assert annotation_target_prompt(
        {"feedback_type": "wandb.annotation.D20260528_Research"},
        "2026-05-28",
    ) == "researcher"
    assert annotation_target_prompt(
        {"feedback_type": "wandb.annotation.D20260527_Research"},
        "2026-05-28",
    ) is None
    assert annotation_target_prompt(
        {"annotation_queue_name": "D20260528_Research"},
        "2026-05-28",
    ) == "researcher"


def test_enrich_feedback_resolves_annotation_queue_name():
    from autoresearch_researcher.tools.feedback import enrich_feedback_with_queue_name

    class FakeServer:
        def annotation_queue_read(self, req):
            assert req.project_id == "entity/project"
            assert req.queue_id == "queue-1"
            return SimpleNamespace(queue=SimpleNamespace(name="D20260528_Research"))

    client = SimpleNamespace(
        server=FakeServer(),
        _project_id=lambda: "entity/project",
    )

    feedback = enrich_feedback_with_queue_name(
        client,
        {"queue_id": "queue-1", "feedback_type": "wandb.annotation.QualityReviewer"},
    )

    assert feedback["annotation_queue_name"] == "D20260528_Research"


def test_feedback_ingest_collects_day_scoped_research_annotations(tmp_path):
    from autoresearch_researcher.tools.feedback import ingest_feedback

    profile_run = {
        "day": "2026-05-28",
        "run_id": "run-1",
        "slug": "tool-a",
        "name": "Tool A",
        "url": "https://example.com/tool-a",
        "weave_call_id": "profile-call",
    }
    (tmp_path / "_profile_runs.jsonl").write_text(json.dumps(profile_run) + "\n")

    feedback_items = [
        SimpleNamespace(
            id="fb-research",
            feedback_type="wandb.annotation.D20260528_Research",
            payload={"value": "Researcher should reject this scoped-out tool."},
            call_id="profile-call",
        ),
        SimpleNamespace(
            id="fb-other-day",
            feedback_type="wandb.annotation.D20260527_Research",
            payload={"value": "Old day feedback."},
            call_id="old-call",
        ),
    ]
    client = SimpleNamespace(get_feedback=lambda: feedback_items)

    events = ingest_feedback(tmp_path, client)

    assert len(events) == 1
    assert events[0]["target_prompt"] == "researcher"
    assert events[0]["weave_call_id"] == "profile-call"
    notes = (tmp_path / "prompt_improvement_notes.md").read_text()
    assert "`researcher.md`: 1" in notes


def test_render_proposer_input_includes_feedback_and_current_prompt(tmp_path):
    from autoresearch_researcher.tools.improvement import (
        load_feedback_context,
        render_proposer_input,
    )

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    day_dir = tmp_path / "2026-05-28"
    _write_feedback(
        day_dir,
        [
            _event(name="Curated Case", note="Bad. Curated list. Should be rejected."),
            _event(name="Good Case", note="good"),
        ],
    )

    context = load_feedback_context(day_dir)
    rendered = render_proposer_input(context, instructions_dir=instructions_dir)

    assert "Day: 2026-05-28" in rendered
    assert "Human Feedback Events" in rendered
    assert "Curated list. Should be rejected." in rendered
    assert "Current Prompt: researcher.md" in rendered
    assert "Seed researcher rules." in rendered


def test_render_proposer_input_handles_no_feedback(tmp_path):
    from autoresearch_researcher.tools.improvement import (
        load_feedback_context,
        render_proposer_input,
    )

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()

    context = load_feedback_context(day_dir)
    rendered = render_proposer_input(context, instructions_dir=instructions_dir)

    assert "No feedback events were found." in rendered


def test_render_applier_input_includes_plan_and_current_prompt(tmp_path):
    from autoresearch_researcher.tools.improvement import render_applier_input

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    plan_md = "# Prompt Improvement Plan\n\n## Proposed Changes: researcher.md\nReject curated lists."

    rendered = render_applier_input(
        plan_markdown=plan_md,
        instructions_dir=instructions_dir,
    )

    assert "Prompt Improvement Plan" in rendered
    assert "Reject curated lists." in rendered
    assert "Seed researcher rules." in rendered


def test_propose_prompt_improvements_runs_agent_and_returns_plan(tmp_path):
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    day_dir = tmp_path / "2026-05-28"
    _write_feedback(
        day_dir,
        [_event(name="Curated Case", note="Bad. Curated list. Should be rejected.")],
    )

    plan_markdown = "# Prompt Improvement Plan for 2026-05-28\n\nReject curated lists."

    async def fake_runner(*, day_dir, instructions_dir, max_turns):
        plan_path = day_dir / improvement.PLAN_FILENAME
        plan_path.write_text(plan_markdown)
        return plan_path

    with patch.object(improvement, "_run_proposer_agent", side_effect=fake_runner):
        result = improvement.propose_prompt_improvements(
            day_dir, instructions_dir=instructions_dir
        )

    assert result["prompt_only"] is True
    assert result["applies_code_changes"] is False
    assert result["feedback_event_count"] == 1
    assert result["plan_markdown"] == plan_markdown
    assert result["target_prompt_files"] == [
        "src/autoresearch_researcher/instructions/researcher.md"
    ]
    assert Path(result["plan_path"]).name == "prompt_improvement_plan.md"
    assert Path(result["plan_path"]).exists()


def test_propose_prompt_improvements_errors_when_agent_skips_save(tmp_path):
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    day_dir = tmp_path / "2026-05-28"
    _write_feedback(day_dir, [_event(name="X", note="bad")])

    async def fake_runner(*, day_dir, instructions_dir, max_turns):
        return day_dir / improvement.PLAN_FILENAME

    with patch.object(improvement, "_run_proposer_agent", side_effect=fake_runner):
        try:
            improvement.propose_prompt_improvements(
                day_dir, instructions_dir=instructions_dir
            )
        except FileNotFoundError:
            pass
        else:
            assert False, "expected propose to fail when agent skips save_improvement_plan"


def test_apply_prompt_improvements_publishes_when_files_change(tmp_path):
    from autoresearch_researcher.tools import improvement
    from autoresearch_researcher.tools.prompts import InstructionPromptVersion

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    plan_path = day_dir / improvement.PLAN_FILENAME
    plan_path.write_text("# Plan\n\n## Proposed Changes: researcher.md\nReject curated lists.")

    async def fake_runner(*, day_dir, instructions_dir, max_turns):
        (instructions_dir / "researcher.md").write_text("# Researcher\nReject curated lists.\n")
        return plan_path, [instructions_dir / "researcher.md"]

    fake_versions = {
        "researcher": InstructionPromptVersion(
            agent_name="researcher",
            object_name="autoresearch-researcher-instructions",
            content="",
            formatted_content="",
            content_hash="h2",
            ref_uri="weave:///r:v2",
        ),
    }

    with patch.object(improvement, "_run_applier_agent", side_effect=fake_runner), \
         patch.object(improvement, "publish_instruction_prompts", return_value=fake_versions) as mock_publish:
        result = improvement.apply_prompt_improvements_traced(
            day_dir, instructions_dir=instructions_dir
        )

    mock_publish.assert_called_once()
    assert result["prompt_only"] is True
    assert result["changed_prompt_files"] == [str(instructions_dir / "researcher.md")]
    assert result["published"] is True
    assert result["prompt_refs"] == {"researcher": "weave:///r:v2"}
    assert "weave:///r:v2" in result["apply_markdown"]
    assert (day_dir / "prompt_improvement_applied.md").exists()


def test_apply_prompt_improvements_skips_publish_when_no_changes(tmp_path):
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    plan_path = day_dir / improvement.PLAN_FILENAME
    plan_path.write_text("# Plan")

    async def fake_runner(*, day_dir, instructions_dir, max_turns):
        return plan_path, []

    with patch.object(improvement, "_run_applier_agent", side_effect=fake_runner), \
         patch.object(improvement, "publish_instruction_prompts") as mock_publish:
        result = improvement.apply_prompt_improvements_traced(
            day_dir, instructions_dir=instructions_dir
        )

    mock_publish.assert_not_called()
    assert result["published"] is False
    assert "prompt_refs" not in result


def test_apply_prompt_improvements_requires_existing_plan(tmp_path):
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()

    try:
        improvement.apply_prompt_improvements_traced(
            day_dir, instructions_dir=instructions_dir
        )
    except FileNotFoundError as exc:
        assert "prompt_improvement_plan.md" in str(exc)
    else:
        assert False, "expected FileNotFoundError when plan is missing"


def test_render_apply_result_markdown_lists_changed_files(tmp_path):
    from autoresearch_researcher.tools.improvement import render_apply_result_markdown

    markdown = render_apply_result_markdown(
        day="2026-05-28",
        plan_path=tmp_path / "prompt_improvement_plan.md",
        changed_paths=[tmp_path / "instructions" / "researcher.md"],
    )

    assert "Prompt Improvement Apply Result" in markdown
    assert "Python code changes: not applied" in markdown
    assert "researcher.md" in markdown


def test_improve_propose_cli_invokes_agent_and_writes_plan(tmp_path):
    from autoresearch_researcher.tools import improvement

    day_dir = tmp_path / "2026-05-28"
    _write_feedback(day_dir, [_event(name="X", note="bad")])

    async def fake_runner(*, day_dir, instructions_dir, max_turns):
        plan_path = day_dir / improvement.PLAN_FILENAME
        plan_path.write_text("# Plan")
        return plan_path

    with patch("autoresearch_researcher.orchestrator.init_observability"), \
         patch.object(improvement, "_run_proposer_agent", side_effect=fake_runner):
        result = runner.invoke(
            app,
            ["improve", "propose", "--day", "2026-05-28", "--output-dir", str(tmp_path)],
        )

    assert result.exit_code == 0, result.output
    assert (day_dir / "prompt_improvement_plan.md").exists()


def test_improve_apply_cli_invokes_agent_and_reports_changes(tmp_path):
    from autoresearch_researcher.tools import improvement

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    (day_dir / "prompt_improvement_plan.md").write_text("# Plan")

    async def fake_runner(*, day_dir, instructions_dir, max_turns):
        return day_dir / improvement.PLAN_FILENAME, []

    with patch("autoresearch_researcher.orchestrator.init_observability"), \
         patch.object(improvement, "_run_applier_agent", side_effect=fake_runner):
        result = runner.invoke(
            app,
            ["improve", "apply", "--day", "2026-05-28", "--output-dir", str(tmp_path)],
        )

    assert result.exit_code == 0, result.output
    assert "No prompt files updated." in result.output
    assert (day_dir / "prompt_improvement_applied.md").exists()


def test_improve_propose_subcommand_exists():
    result = runner.invoke(app, ["improve", "propose", "--help"])
    assert result.exit_code == 0
    assert "day" in result.output.lower()


def test_improve_apply_subcommand_exists():
    result = runner.invoke(app, ["improve", "apply", "--help"])
    assert result.exit_code == 0
    assert "day" in result.output.lower()
