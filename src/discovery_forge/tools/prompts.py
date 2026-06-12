"""Weave prompt versioning for agent instruction markdown files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import weave


INSTRUCTIONS_DIR = Path(__file__).parent.parent / "agents"

PROMPT_OBJECT_NAMES = {
    "researcher": "researcher_instructions",
}


@dataclass
class InstructionPromptVersion:
    agent_name: str
    object_name: str
    content: str
    formatted_content: str
    content_hash: str
    ref_uri: str | None


def load_instruction_content(agent_name: str, instructions_dir: Path = INSTRUCTIONS_DIR) -> str:
    """Read one local instruction markdown file."""
    return (instructions_dir / f"{agent_name}.md").read_text()


def instruction_hash(content: str) -> str:
    """Return the stable short hash used in run metadata and trace attributes."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def load_local_instruction_prompts(
    *,
    max_tools: int,
    instructions_dir: Path = INSTRUCTIONS_DIR,
) -> dict[str, InstructionPromptVersion]:
    """Load local instructions without publishing. Used for dry-run/tests."""
    versions = {}
    for agent_name, object_name in PROMPT_OBJECT_NAMES.items():
        content = load_instruction_content(agent_name, instructions_dir=instructions_dir)
        versions[agent_name] = InstructionPromptVersion(
            agent_name=agent_name,
            object_name=object_name,
            content=content,
            formatted_content=format_instruction_content(agent_name, content, max_tools=max_tools),
            content_hash=instruction_hash(content),
            ref_uri=None,
        )
    return versions


def publish_instruction_prompts(
    *,
    max_tools: int,
    instructions_dir: Path = INSTRUCTIONS_DIR,
) -> dict[str, InstructionPromptVersion]:
    """Publish instruction files as Weave StringPrompt objects and return registered content."""
    versions = {}
    for agent_name, object_name in PROMPT_OBJECT_NAMES.items():
        local_content = load_instruction_content(agent_name, instructions_dir=instructions_dir)
        prompt = weave.StringPrompt(local_content)
        ref = weave.publish(prompt, name=object_name)
        ref_uri = _ref_uri(ref)
        registered_prompt = _get_prompt_from_ref(ref, ref_uri)
        registered_content = getattr(registered_prompt, "content", local_content)
        versions[agent_name] = InstructionPromptVersion(
            agent_name=agent_name,
            object_name=object_name,
            content=registered_content,
            formatted_content=format_instruction_content(
                agent_name, registered_content, max_tools=max_tools,
            ),
            content_hash=instruction_hash(registered_content),
            ref_uri=ref_uri,
        )
    return versions


def prompt_hashes(versions: dict[str, InstructionPromptVersion]) -> dict[str, str]:
    return {agent: version.content_hash for agent, version in versions.items()}


def prompt_refs(versions: dict[str, InstructionPromptVersion]) -> dict[str, str | None]:
    return {agent: version.ref_uri for agent, version in versions.items()}


def prompt_contents(versions: dict[str, InstructionPromptVersion]) -> dict[str, str]:
    return {agent: version.formatted_content for agent, version in versions.items()}


def load_prompt_ref_content(prompt_ref: str) -> str:
    """Load StringPrompt content from a versioned Weave prompt ref."""
    prompt = weave.ref(prompt_ref).get()
    content = getattr(prompt, "content", None)
    if not isinstance(content, str):
        raise ValueError(f"Weave prompt ref does not contain string content: {prompt_ref}")
    return content


def format_instruction_content(agent_name: str, content: str, *, max_tools: int) -> str:
    """Apply runtime variables after retrieving the registered prompt content.

    The single researcher prompt has no formatting variables; the per-run
    exclusion list is passed at call time instead of being baked into the prompt.
    """
    return content


def _ref_uri(ref: Any) -> str | None:
    uri = getattr(ref, "uri", None)
    if callable(uri):
        return uri()
    if isinstance(uri, str):
        return uri
    if ref is not None:
        return str(ref)
    return None


def _get_prompt_from_ref(ref: Any, ref_uri: str | None) -> Any:
    if ref_uri:
        return weave.ref(ref_uri).get()
    return ref
