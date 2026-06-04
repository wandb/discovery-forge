"""Prompt-improvement agents: proposer + applier.

Both agents read the human free-text feedback collected on Weave traces and
either (a) emit a concrete prompt-only improvement plan, or (b) apply that plan
to the instructions/*.md files. They never touch Python code, schemas,
registry, orchestrator, or CLI logic.
"""

from __future__ import annotations

from pathlib import Path

from agents import Agent, function_tool

from discovery_forge.agents.researcher import load_instructions


PROMPT_FILENAMES = {
    "researcher": "researcher.md",
}


def build_prompt_proposer_agent(
    *,
    plan_path: Path,
    instructions_override: str | None = None,
) -> Agent:
    """Agent that turns free-text feedback into a structured prompt-improvement plan.

    The agent writes the plan to ``plan_path`` via ``save_improvement_plan`` and
    has no other tools.
    """
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    @function_tool
    def save_improvement_plan(content: str) -> str:
        """Persist the prompt improvement plan as Markdown."""
        plan_path.write_text(content)
        return f"Saved improvement plan to {plan_path}"

    instructions = instructions_override or load_instructions("prompt_proposer")

    return Agent(
        name="PromptImprovementProposerAgent",
        instructions=instructions,
        tools=[save_improvement_plan],
        model="gpt-5.4-mini",
    )


def build_prompt_applier_agent(
    *,
    instructions_dir: Path,
    instructions_override: str | None = None,
) -> Agent:
    """Agent that rewrites instructions/*.md files from a prompt-improvement plan.

    Each instruction file has its own tool so the agent picks the files to
    update explicitly. The agent never touches Python source.
    """
    instructions_dir.mkdir(parents=True, exist_ok=True)

    @function_tool
    def update_researcher_instructions(content: str) -> str:
        """Overwrite instructions/researcher.md with the full new Markdown content."""
        path = instructions_dir / PROMPT_FILENAMES["researcher"]
        path.write_text(content)
        return f"Updated {path}"

    instructions = instructions_override or load_instructions("prompt_applier")

    return Agent(
        name="PromptImprovementApplierAgent",
        instructions=instructions,
        tools=[
            update_researcher_instructions,
        ],
        model="gpt-5.4-mini",
    )
