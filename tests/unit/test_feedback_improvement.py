"""Tests for the LLM-driven prompt-only improvement proposer/applier."""

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from autoresearch_researcher.cli import app

runner = CliRunner()


def _event(*, name: str, note: str, slug: str | None = None) -> dict:
    return {
        "week": "2026-W99",
        "run_id": "run-1",
        "name": name,
        "slug": slug or name.lower().replace(" ", "-"),
        "weave_call_id": "call-1",
        "feedback": {
            "feedback_type": "wandb.annotation.ProfilerAgentScorer",
            "payload": {"value": note},
        },
    }


def _write_feedback(week_dir: Path, events: list[dict]) -> None:
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "feedback_events.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + ("\n" if events else "")
    )


def _bootstrap_instructions(instructions_dir: Path) -> None:
    instructions_dir.mkdir(parents=True, exist_ok=True)
    (instructions_dir / "discovery.md").write_text("# Discovery\nSeed discovery rules.\n")
    (instructions_dir / "profiler.md").write_text("# Profiler\nSeed profiler rules.\n")
    (instructions_dir / "writer.md").write_text("# Writer\nSeed writer rules.\n")


def test_load_feedback_context_reads_all_artifacts(tmp_path):
    from autoresearch_researcher.tools.improvement import load_feedback_context

    _write_feedback(tmp_path, [_event(name="Tool A", note="Bad. Curated list.")])

    context = load_feedback_context(tmp_path)

    assert context.week == tmp_path.name
    assert len(context.feedback_events) == 1
    assert context.feedback_events[0]["name"] == "Tool A"


def test_render_proposer_input_includes_feedback_and_current_prompts(tmp_path):
    from autoresearch_researcher.tools.improvement import (
        load_feedback_context,
        render_proposer_input,
    )

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    week_dir = tmp_path / "2026-W99"
    _write_feedback(
        week_dir,
        [
            _event(name="Curated Case", note="Bad. Curated list. Should be rejected."),
            _event(name="Good Case", note="good"),
        ],
    )

    context = load_feedback_context(week_dir)
    rendered = render_proposer_input(context, instructions_dir=instructions_dir)

    assert "Week: 2026-W99" in rendered
    assert "Human Feedback Events" in rendered
    assert "Curated list. Should be rejected." in rendered
    assert "Current Prompt: discovery.md" in rendered
    assert "Current Prompt: profiler.md" in rendered
    assert "Current Prompt: writer.md" in rendered
    assert "Seed profiler rules." in rendered


def test_render_proposer_input_handles_no_feedback(tmp_path):
    from autoresearch_researcher.tools.improvement import (
        load_feedback_context,
        render_proposer_input,
    )

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    week_dir = tmp_path / "2026-W99"
    week_dir.mkdir()

    context = load_feedback_context(week_dir)
    rendered = render_proposer_input(context, instructions_dir=instructions_dir)

    assert "No feedback events were found." in rendered


def test_render_applier_input_includes_plan_and_current_prompts(tmp_path):
    from autoresearch_researcher.tools.improvement import render_applier_input

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    plan_md = "# Prompt Improvement Plan\n\n## Proposed Changes: profiler.md\nReject curated lists."

    rendered = render_applier_input(
        plan_markdown=plan_md,
        instructions_dir=instructions_dir,
    )

    assert "Prompt Improvement Plan" in rendered
    assert "Reject curated lists." in rendered
    assert "Seed discovery rules." in rendered
    assert "Seed profiler rules." in rendered
    assert "Seed writer rules." in rendered


def test_propose_prompt_improvements_runs_agent_and_returns_plan(tmp_path):
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    week_dir = tmp_path / "2026-W99"
    _write_feedback(
        week_dir,
        [_event(name="Curated Case", note="Bad. Curated list. Should be rejected.")],
    )

    plan_markdown = "# Prompt Improvement Plan for 2026-W99\n\nReject curated lists."

    async def fake_runner(*, week_dir, instructions_dir, max_turns):
        plan_path = week_dir / improvement.PLAN_FILENAME
        plan_path.write_text(plan_markdown)
        return plan_path

    with patch.object(improvement, "_run_proposer_agent", side_effect=fake_runner):
        result = improvement.propose_prompt_improvements(
            week_dir, instructions_dir=instructions_dir
        )

    assert result["prompt_only"] is True
    assert result["applies_code_changes"] is False
    assert result["feedback_event_count"] == 1
    assert result["plan_markdown"] == plan_markdown
    assert result["proposal_markdown"] == plan_markdown
    assert Path(result["plan_path"]).name == "prompt_improvement_plan.md"
    assert Path(result["plan_path"]).exists()


def test_propose_prompt_improvements_errors_when_agent_skips_save(tmp_path):
    """The proposer agent must call save_improvement_plan; otherwise we fail loudly."""
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    week_dir = tmp_path / "2026-W99"
    _write_feedback(week_dir, [_event(name="X", note="bad")])

    async def fake_runner(*, week_dir, instructions_dir, max_turns):
        # Intentionally do not write a plan file.
        return week_dir / improvement.PLAN_FILENAME

    with patch.object(improvement, "_run_proposer_agent", side_effect=fake_runner):
        # propose_prompt_improvements wraps asyncio.run on _run_proposer_agent,
        # so the missing plan file surfaces as the underlying RuntimeError.
        try:
            improvement.propose_prompt_improvements(
                week_dir, instructions_dir=instructions_dir
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
    week_dir = tmp_path / "2026-W99"
    week_dir.mkdir()
    plan_path = week_dir / improvement.PLAN_FILENAME
    plan_path.write_text("# Plan\n\n## Proposed Changes: profiler.md\nReject curated lists.")

    async def fake_runner(*, week_dir, instructions_dir, max_turns):
        (instructions_dir / "profiler.md").write_text("# Profiler\nReject curated lists.\n")
        return plan_path, [instructions_dir / "profiler.md"]

    fake_versions = {
        "discovery": InstructionPromptVersion(
            agent_name="discovery",
            object_name="autoresearch-discovery-instructions",
            content="",
            formatted_content="",
            content_hash="h1",
            ref_uri="weave:///d:v1",
        ),
        "profiler": InstructionPromptVersion(
            agent_name="profiler",
            object_name="autoresearch-profiler-instructions",
            content="",
            formatted_content="",
            content_hash="h2",
            ref_uri="weave:///p:v2",
        ),
        "writer": InstructionPromptVersion(
            agent_name="writer",
            object_name="autoresearch-writer-instructions",
            content="",
            formatted_content="",
            content_hash="h3",
            ref_uri="weave:///w:v1",
        ),
    }

    with patch.object(improvement, "_run_applier_agent", side_effect=fake_runner), \
         patch.object(improvement, "publish_instruction_prompts", return_value=fake_versions) as mock_publish:
        result = improvement.apply_prompt_improvements_traced(
            week_dir, instructions_dir=instructions_dir
        )

    mock_publish.assert_called_once()
    assert result["prompt_only"] is True
    assert result["applies_code_changes"] is False
    assert result["changed_prompt_files"] == [str(instructions_dir / "profiler.md")]
    assert result["published"] is True
    assert result["prompt_refs"] == {
        "discovery": "weave:///d:v1",
        "profiler": "weave:///p:v2",
        "writer": "weave:///w:v1",
    }
    assert "weave:///p:v2" in result["apply_markdown"]
    assert (week_dir / "prompt_improvement_applied.md").exists()


def test_apply_prompt_improvements_skips_publish_when_no_changes(tmp_path):
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    week_dir = tmp_path / "2026-W99"
    week_dir.mkdir()
    plan_path = week_dir / improvement.PLAN_FILENAME
    plan_path.write_text("# Plan")

    async def fake_runner(*, week_dir, instructions_dir, max_turns):
        return plan_path, []

    with patch.object(improvement, "_run_applier_agent", side_effect=fake_runner), \
         patch.object(improvement, "publish_instruction_prompts") as mock_publish:
        result = improvement.apply_prompt_improvements_traced(
            week_dir, instructions_dir=instructions_dir
        )

    mock_publish.assert_not_called()
    assert result["published"] is False
    assert "prompt_refs" not in result


def test_apply_prompt_improvements_requires_existing_plan(tmp_path):
    from autoresearch_researcher.tools import improvement

    instructions_dir = tmp_path / "instructions"
    _bootstrap_instructions(instructions_dir)
    week_dir = tmp_path / "2026-W99"
    week_dir.mkdir()

    try:
        improvement.apply_prompt_improvements_traced(
            week_dir, instructions_dir=instructions_dir
        )
    except FileNotFoundError as exc:
        assert "prompt_improvement_plan.md" in str(exc)
    else:
        assert False, "expected FileNotFoundError when plan is missing"


def test_render_apply_result_markdown_lists_changed_files(tmp_path):
    from autoresearch_researcher.tools.improvement import render_apply_result_markdown

    markdown = render_apply_result_markdown(
        week="2026-W99",
        plan_path=tmp_path / "prompt_improvement_plan.md",
        changed_paths=[tmp_path / "instructions" / "profiler.md"],
    )

    assert "Prompt Improvement Apply Result" in markdown
    assert "Python code changes: not applied" in markdown
    assert "profiler.md" in markdown


def test_improve_propose_cli_invokes_agent_and_writes_plan(tmp_path):
    from autoresearch_researcher.tools import improvement

    week_dir = tmp_path / "2026-W99"
    _write_feedback(week_dir, [_event(name="X", note="bad")])

    async def fake_runner(*, week_dir, instructions_dir, max_turns):
        plan_path = week_dir / improvement.PLAN_FILENAME
        plan_path.write_text("# Plan")
        return plan_path

    with patch("autoresearch_researcher.orchestrator.init_observability"), \
         patch.object(improvement, "_run_proposer_agent", side_effect=fake_runner):
        result = runner.invoke(
            app,
            ["improve", "propose", "--week", "2026-W99", "--output-dir", str(tmp_path)],
        )

    assert result.exit_code == 0, result.output
    assert (week_dir / "prompt_improvement_plan.md").exists()


def test_improve_apply_cli_invokes_agent_and_reports_changes(tmp_path):
    from autoresearch_researcher.tools import improvement

    week_dir = tmp_path / "2026-W99"
    week_dir.mkdir()
    (week_dir / "prompt_improvement_plan.md").write_text("# Plan")

    async def fake_runner(*, week_dir, instructions_dir, max_turns):
        return week_dir / improvement.PLAN_FILENAME, []

    with patch("autoresearch_researcher.orchestrator.init_observability"), \
         patch.object(improvement, "_run_applier_agent", side_effect=fake_runner):
        result = runner.invoke(
            app,
            ["improve", "apply", "--week", "2026-W99", "--output-dir", str(tmp_path)],
        )

    assert result.exit_code == 0, result.output
    assert "No prompt files updated." in result.output
    assert (week_dir / "prompt_improvement_applied.md").exists()


def test_improve_propose_subcommand_exists():
    result = runner.invoke(app, ["improve", "propose", "--help"])
    assert result.exit_code == 0
    assert "week" in result.output.lower()


def test_improve_apply_subcommand_exists():
    result = runner.invoke(app, ["improve", "apply", "--help"])
    assert result.exit_code == 0
    assert "week" in result.output.lower()
