"""LLM-driven prompt-only improvement proposal and application.

`propose_prompt_improvements` and `apply_prompt_improvements` each run a small
OpenAI Agents SDK agent. They never touch Python code; the only deliverables
are the prompt-improvement plan Markdown and, for apply, the rewritten
`instructions/*.md` files.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import weave
from agents import Runner

from autoresearch_researcher.agents.improver import (
    PROMPT_FILENAMES,
    build_prompt_applier_agent,
    build_prompt_proposer_agent,
)
from autoresearch_researcher.tools.prompts import (
    INSTRUCTIONS_DIR,
    prompt_refs as prompt_refs_for_versions,
    publish_instruction_prompts,
)

PLAN_FILENAME = "prompt_improvement_plan.md"
APPLY_LOG_FILENAME = "prompt_improvement_applied.md"
DEFAULT_PUBLISH_MAX_TOOLS = 12


@dataclass
class FeedbackImprovementContext:
    """Inputs gathered from a week directory for the proposer agent."""

    week: str
    week_dir: Path
    feedback_events: list[dict[str, Any]]
    profile_runs: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    rejected_profiles: list[dict[str, Any]]


def load_feedback_context(week_dir: Path) -> FeedbackImprovementContext:
    """Load feedback and weekly artifacts needed for prompt proposal generation."""
    return FeedbackImprovementContext(
        week=week_dir.name,
        week_dir=week_dir,
        feedback_events=_read_jsonl(week_dir / "feedback_events.jsonl"),
        profile_runs=_read_jsonl(week_dir / "_profile_runs.jsonl"),
        candidates=_read_jsonl(week_dir / "_candidates.jsonl"),
        rejected_profiles=_read_jsonl(week_dir / "_rejected_profiles.jsonl"),
    )


def render_proposer_input(
    context: FeedbackImprovementContext,
    *,
    instructions_dir: Path = INSTRUCTIONS_DIR,
) -> str:
    """Render the user message passed to PromptImprovementProposerAgent."""
    lines = [
        f"# Week: {context.week}",
        "",
        "You are improving prompt-only behavior for the autoresearch pipeline.",
        "Read every feedback event, then call `save_improvement_plan` exactly once.",
        "",
        "## Weekly Context",
        f"- Candidates discovered: {len(context.candidates)}",
        f"- Profile runs: {len(context.profile_runs)}",
        f"- Rejected profiles: {len(context.rejected_profiles)}",
        f"- Feedback events to review: {len(context.feedback_events)}",
        "",
        "## Human Feedback Events",
        "",
    ]

    if not context.feedback_events:
        lines.append("No feedback events were found. Produce a plan that recommends no changes.")
    else:
        for idx, event in enumerate(context.feedback_events, start=1):
            lines.extend(_render_feedback_event(idx, event))

    lines.extend([
        "## Current Prompt: discovery.md",
        "",
        "```markdown",
        _read_text(instructions_dir / PROMPT_FILENAMES["discovery"]),
        "```",
        "",
        "## Current Prompt: profiler.md",
        "",
        "```markdown",
        _read_text(instructions_dir / PROMPT_FILENAMES["profiler"]),
        "```",
        "",
        "## Current Prompt: writer.md",
        "",
        "```markdown",
        _read_text(instructions_dir / PROMPT_FILENAMES["writer"]),
        "```",
        "",
    ])
    return "\n".join(lines)


def render_applier_input(
    *,
    plan_markdown: str,
    instructions_dir: Path = INSTRUCTIONS_DIR,
) -> str:
    """Render the user message passed to PromptImprovementApplierAgent."""
    lines = [
        "You are applying a prompt-improvement plan to instructions/*.md.",
        "Call only the `update_*_instructions` tools whose plan section proposes a change.",
        "Each tool call must include the full new Markdown content for that file.",
        "",
        "## Prompt Improvement Plan",
        "",
        plan_markdown.strip(),
        "",
        "## Current Prompt: discovery.md",
        "",
        "```markdown",
        _read_text(instructions_dir / PROMPT_FILENAMES["discovery"]),
        "```",
        "",
        "## Current Prompt: profiler.md",
        "",
        "```markdown",
        _read_text(instructions_dir / PROMPT_FILENAMES["profiler"]),
        "```",
        "",
        "## Current Prompt: writer.md",
        "",
        "```markdown",
        _read_text(instructions_dir / PROMPT_FILENAMES["writer"]),
        "```",
        "",
    ]
    return "\n".join(lines)


async def _run_proposer_agent(
    *,
    week_dir: Path,
    instructions_dir: Path,
    max_turns: int,
) -> Path:
    """Build, run the proposer agent, and return the path to the plan file."""
    plan_path = week_dir / PLAN_FILENAME
    agent = build_prompt_proposer_agent(plan_path=plan_path)
    context = load_feedback_context(week_dir)
    user_input = render_proposer_input(context, instructions_dir=instructions_dir)
    await Runner.run(agent, input=user_input, max_turns=max_turns)
    if not plan_path.exists():
        raise RuntimeError(
            "PromptImprovementProposerAgent ended without calling save_improvement_plan."
        )
    return plan_path


async def _run_applier_agent(
    *,
    week_dir: Path,
    instructions_dir: Path,
    max_turns: int,
) -> tuple[Path, list[Path]]:
    """Build, run the applier agent, and return (plan_path, changed instruction paths)."""
    plan_path = week_dir / PLAN_FILENAME
    if not plan_path.exists():
        raise FileNotFoundError(
            f"{plan_path} does not exist. Run `autoresearch-researcher improve propose` first."
        )

    instructions_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_instruction_files(instructions_dir)

    agent = build_prompt_applier_agent(instructions_dir=instructions_dir)
    user_input = render_applier_input(
        plan_markdown=plan_path.read_text(),
        instructions_dir=instructions_dir,
    )
    await Runner.run(agent, input=user_input, max_turns=max_turns)

    changed_paths = _detect_changed_files(snapshot, instructions_dir)
    return plan_path, changed_paths


@weave.op(name="improve_propose")
def propose_prompt_improvements(
    week_dir: Path,
    *,
    instructions_dir: Path = INSTRUCTIONS_DIR,
    max_turns: int = 6,
) -> dict[str, Any]:
    """Run the proposer agent and return Weave-friendly review output."""
    plan_path = asyncio.run(
        _run_proposer_agent(
            week_dir=week_dir,
            instructions_dir=instructions_dir,
            max_turns=max_turns,
        )
    )
    plan_markdown = plan_path.read_text()
    context = load_feedback_context(week_dir)
    return {
        "week": week_dir.name,
        "plan_path": str(plan_path),
        "proposal_path": str(plan_path),
        "feedback_event_count": len(context.feedback_events),
        "target_prompt_files": [
            f"src/autoresearch_researcher/instructions/{name}"
            for name in PROMPT_FILENAMES.values()
        ],
        "prompt_only": True,
        "applies_code_changes": False,
        "plan_markdown": plan_markdown,
        "proposal_markdown": plan_markdown,
    }


@weave.op(name="improve_apply")
def apply_prompt_improvements_traced(
    week_dir: Path,
    *,
    instructions_dir: Path = INSTRUCTIONS_DIR,
    max_turns: int = 6,
    publish_max_tools: int = DEFAULT_PUBLISH_MAX_TOOLS,
) -> dict[str, Any]:
    """Run the applier agent and return Weave-friendly review output.

    When the agent actually changes any instruction file, the new content is
    also published as Weave StringPrompt objects so the next weekly run picks
    up the updated version refs immediately. There is no manual review step
    in this pipeline, so publishing is unconditional.
    """
    plan_path, changed_paths = asyncio.run(
        _run_applier_agent(
            week_dir=week_dir,
            instructions_dir=instructions_dir,
            max_turns=max_turns,
        )
    )

    published_refs: dict[str, str | None] | None = None
    if changed_paths:
        versions = publish_instruction_prompts(
            max_tools=publish_max_tools,
            instructions_dir=instructions_dir,
        )
        published_refs = prompt_refs_for_versions(versions)

    apply_log = render_apply_result_markdown(
        week=week_dir.name,
        plan_path=plan_path,
        changed_paths=changed_paths,
        prompt_refs=published_refs,
    )
    log_path = week_dir / APPLY_LOG_FILENAME
    log_path.write_text(apply_log)

    output: dict[str, Any] = {
        "week": week_dir.name,
        "plan_path": str(plan_path),
        "proposal_path": str(plan_path),
        "apply_log_path": str(log_path),
        "changed_prompt_files": [str(path) for path in changed_paths],
        "prompt_only": True,
        "applies_code_changes": False,
        "apply_markdown": apply_log,
        "published": bool(published_refs),
    }
    if published_refs is not None:
        output["prompt_refs"] = published_refs
    return output


def render_apply_result_markdown(
    *,
    week: str,
    plan_path: Path,
    changed_paths: list[Path],
    prompt_refs: dict[str, str | None] | None = None,
) -> str:
    """Render a Markdown summary for `improve apply` Weave output."""
    lines = [
        f"# Prompt Improvement Apply Result for {week}",
        "",
        f"Plan: `{plan_path}`",
        "",
        "## Scope",
        "- Prompt files only",
        "- Python code changes: not applied",
        "",
        "## Changed Prompt Files",
        "",
    ]
    if changed_paths:
        lines.extend(f"- `{path}`" for path in changed_paths)
    else:
        lines.append("No prompt files updated.")
    lines.append("")

    if prompt_refs:
        lines.extend([
            "## Published Weave Prompt Refs",
            "",
        ])
        for agent_name, ref in prompt_refs.items():
            lines.append(f"- {agent_name}: `{ref}`")
        lines.append("")

    return "\n".join(lines)


def _snapshot_instruction_files(instructions_dir: Path) -> dict[Path, str]:
    """Snapshot existing instruction file contents for change detection."""
    snapshot: dict[Path, str] = {}
    for filename in PROMPT_FILENAMES.values():
        path = instructions_dir / filename
        snapshot[path] = path.read_text() if path.exists() else ""
    return snapshot


def _detect_changed_files(snapshot: dict[Path, str], instructions_dir: Path) -> list[Path]:
    """Return instruction paths whose content differs from the snapshot."""
    changed: list[Path] = []
    for filename in PROMPT_FILENAMES.values():
        path = instructions_dir / filename
        previous = snapshot.get(path, "")
        current = path.read_text() if path.exists() else ""
        if current != previous:
            changed.append(path)
    return changed


def _render_feedback_event(index: int, event: dict[str, Any]) -> list[str]:
    payload = _feedback_payload(event)
    value = payload.get("value")
    feedback_text = value if value is not None else payload
    return [
        f"### Feedback {index}: {event.get('name') or event.get('slug') or 'unknown item'}",
        "",
        f"- Trace call ID: `{event.get('weave_call_id')}`",
        f"- Tool slug: `{event.get('slug')}`",
        f"- Tool URL: `{event.get('url')}`",
        f"- Feedback type: `{event.get('feedback', {}).get('feedback_type')}`",
        f"- Human feedback: {feedback_text}",
        "",
    ]


def _feedback_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("feedback", {}).get("payload", {})
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _read_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""
