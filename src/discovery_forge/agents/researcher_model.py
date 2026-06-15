"""Weave Model wrapper for the ResearcherAgent."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import weave
from agents import RunConfig, Runner
from pydantic import PrivateAttr

from discovery_forge.agents.researcher import build_researcher_agent, load_instructions
from discovery_forge.review import profile_review_output
from discovery_forge.schemas.tool_profile import RejectedProfile, ToolProfile
from discovery_forge.tools.prompts import PROMPT_OBJECT_NAMES, load_prompt_ref_content, weave_ref_uri
from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND, RecencyWindow, SearchBackend

RESEARCHER_MODEL_OBJECT_NAME = "ResearcherAgentModel"
RESEARCHER_AGENT_NAME = "ResearcherAgent"
RESEARCHER_AGENT_MODEL_ID = "gpt-5.4-mini"
DEFAULT_RESEARCHER_MAX_TURNS = 40


class EvalPersistenceRecorder:
    """Capture one eval row's final persistence tool result in memory."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.search_queries: list[str] = []

    def record_search_query(self, query: str) -> None:
        if query.strip():
            self.search_queries.append(query.strip())

    def save_tool_profile(self, profile: ToolProfile) -> str:
        self.events.append(("accepted", profile))
        return f"Saved profile: {profile.slug}"

    def save_rejected_profile(self, rejected: RejectedProfile) -> str:
        self.events.append(("rejected", rejected))
        primary_url = rejected.github_url or rejected.project_url or rejected.paper_url or rejected.url or "unknown"
        return f"Rejected: {rejected.name} ({primary_url}) - {rejected.verdict_reason}"

    def report_no_new_tool(self, reason: str) -> str:
        self.events.append(("unknown", reason))
        return f"No new tool found: {reason}"

    def output(self) -> dict[str, Any]:
        if not self.events:
            return {
                "scope_status": "unknown",
                "verdict_reason": "ResearcherAgent did not save or reject a profile.",
                "profile": None,
            }

        status, payload = self.events[-1]
        if status == "accepted":
            return {
                "scope_status": "accepted",
                "verdict_reason": None,
                "profile": payload.model_dump(),
            }
        if status == "rejected":
            return {
                "scope_status": "rejected",
                "verdict_reason": payload.verdict_reason,
                "profile": None,
            }
        return {
            "scope_status": "unknown",
            "verdict_reason": str(payload),
            "profile": None,
        }

    def review_output(
        self,
        *,
        search_backend: str | None,
        search_recency: str | None,
        workflow_name: str | None,
        researcher_prompt_ref: str | None,
        researcher_prompt_hash: str | None,
        researcher_model_ref: str | None,
    ) -> dict[str, Any]:
        if not self.events:
            profile: dict[str, Any] = {}
            status = "unknown"
        else:
            status, payload = self.events[-1]
            if status == "accepted":
                profile = payload.model_dump()
            elif status == "rejected":
                profile = payload.model_dump()
            else:
                profile = {
                    "slug": "no-new-finding",
                    "name": "No new finding",
                    "verdict_reason": str(payload),
                }
                status = "no_new"
        return profile_review_output(
            profile,
            status=status,
            search_queries=self.search_queries,
            search_backend=search_backend,
            search_recency=search_recency,
            workflow_name=workflow_name,
            researcher_prompt_ref=researcher_prompt_ref,
            researcher_prompt_hash=researcher_prompt_hash,
            researcher_model_ref=researcher_model_ref,
        )


class ResearcherAgentModel(weave.Model):
    """Versioned Weave model that runs the Discovery Forge ResearcherAgent."""

    agent_name: str = RESEARCHER_AGENT_NAME
    agent_model: str = RESEARCHER_AGENT_MODEL_ID
    prompt_object_name: str = PROMPT_OBJECT_NAMES["researcher"]
    researcher_prompt_ref: str | None = None
    researcher_prompt_hash: str
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND
    recency: RecencyWindow | None = None
    max_turns: int = DEFAULT_RESEARCHER_MAX_TURNS

    _researcher_model_ref: str | None = PrivateAttr(default=None)
    _output_dir: Path | None = PrivateAttr(default=None)
    _registry: Any = PrivateAttr(default=None)
    _day: str | None = PrivateAttr(default=None)
    _instructions_override: str | None = PrivateAttr(default=None)
    _capture_persistence: bool = PrivateAttr(default=False)
    _save_tool_profile_callback: Any = PrivateAttr(default=None)
    _save_rejected_profile_callback: Any = PrivateAttr(default=None)
    _report_no_new_tool_callback: Any = PrivateAttr(default=None)
    _last_usage: tuple[int, int, float] = PrivateAttr(default=(0, 0, 0.0))

    @property
    def researcher_model_ref(self) -> str | None:
        return self._researcher_model_ref

    @property
    def last_usage(self) -> tuple[int, int, float]:
        return self._last_usage

    def bind_runtime(
        self,
        *,
        output_dir: Path,
        registry: Any = None,
        day: str | None = None,
        instructions_override: str | None = None,
        capture_persistence: bool = False,
        save_tool_profile_callback: Any = None,
        save_rejected_profile_callback: Any = None,
        report_no_new_tool_callback: Any = None,
    ) -> "ResearcherAgentModel":
        """Attach process-local runtime dependencies that should not be versioned."""
        self._output_dir = output_dir
        self._registry = registry
        self._day = day
        self._instructions_override = instructions_override
        self._capture_persistence = capture_persistence
        self._save_tool_profile_callback = save_tool_profile_callback
        self._save_rejected_profile_callback = save_rejected_profile_callback
        self._report_no_new_tool_callback = report_no_new_tool_callback
        return self

    @weave.op()
    async def predict(
        self,
        research_prompt: str | None = None,
        input_tool_name: str | None = None,
        input_candidate_url: str | None = None,
        input_candidate_description: str | None = None,
        day: str | None = None,
        run_id: str | None = None,
        workflow_name: str | None = None,
        trace_id: str | None = None,
        stage: str = "research",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the underlying ResearcherAgent for a daily prompt or eval row."""
        prompt = research_prompt or render_candidate_prompt(
            input_tool_name=input_tool_name,
            input_candidate_url=input_candidate_url,
            input_candidate_description=input_candidate_description,
        )
        output_dir = self._output_dir_for(input_tool_name if research_prompt is None else None)
        recorder = EvalPersistenceRecorder()
        agent = build_researcher_agent(
            output_dir=output_dir,
            registry=self._registry,
            day=self._day or day,
            search_backend=self.search_backend,
            recency=self.recency,
            instructions_override=self._instructions(),
            save_tool_profile_callback=(
                recorder.save_tool_profile if self._capture_persistence else self._save_tool_profile_callback
            ),
            save_rejected_profile_callback=(
                recorder.save_rejected_profile
                if self._capture_persistence
                else self._save_rejected_profile_callback
            ),
            report_no_new_tool_callback=(
                recorder.report_no_new_tool
                if self._capture_persistence
                else self._report_no_new_tool_callback
            ),
            search_query_observer=recorder.record_search_query,
            save_tool_profile_observer=None if self._capture_persistence else recorder.save_tool_profile,
            save_rejected_profile_observer=(
                None if self._capture_persistence else recorder.save_rejected_profile
            ),
            report_no_new_tool_observer=None if self._capture_persistence else recorder.report_no_new_tool,
        )

        runner_kwargs: dict[str, Any] = {}
        run_config = _run_config(
            workflow_name=workflow_name,
            day=self._day or day,
            run_id=run_id,
            stage=stage,
            trace_id=trace_id,
            metadata=metadata,
        )
        if run_config is not None:
            runner_kwargs["run_config"] = run_config

        result = await Runner.run(agent, input=prompt, max_turns=self.max_turns, **runner_kwargs)
        self._last_usage = _extract_usage(result)
        persistence_output = recorder.output()
        review_output = recorder.review_output(
            search_backend=self.search_backend,
            search_recency=self.recency,
            workflow_name=workflow_name,
            researcher_prompt_ref=self.researcher_prompt_ref,
            researcher_prompt_hash=self.researcher_prompt_hash,
            researcher_model_ref=self.researcher_model_ref,
        )
        return {
            **review_output,
            "scope_status": persistence_output["scope_status"],
            "verdict_reason": persistence_output["verdict_reason"],
            "final_output": str(getattr(result, "final_output", "")),
            "profile": persistence_output["profile"],
        }

    def _instructions(self) -> str:
        if self._instructions_override is not None:
            return self._instructions_override
        if self.researcher_prompt_ref is not None:
            return load_prompt_ref_content(self.researcher_prompt_ref)
        return load_instructions("researcher")

    def _output_dir_for(self, input_tool_name: str | None) -> Path:
        if self._output_dir is None:
            raise ValueError("ResearcherAgentModel runtime output_dir is not bound.")
        if input_tool_name is None:
            return self._output_dir
        return self._output_dir / safe_name(input_tool_name)


def render_candidate_prompt(
    *,
    input_tool_name: str | None,
    input_candidate_url: str | None,
    input_candidate_description: str | None,
) -> str:
    """Render the fixed-candidate offline eval prompt."""
    if not input_tool_name or not input_candidate_url or not input_candidate_description:
        raise ValueError("Provide input_tool_name, input_candidate_url, and input_candidate_description.")
    return (
        "Profile this specific tool candidate and determine if it is in scope:\n"
        f"Name: {input_tool_name}\n"
        f"URL: {input_candidate_url}\n"
        f"Description: {input_candidate_description}\n"
        "If in scope, save sources then call save_tool_profile_tool. "
        "If out of scope, call save_rejected_profile_tool with a clear reason."
    )


def publish_researcher_model(model: ResearcherAgentModel) -> str | None:
    """Publish the model configuration and attach its Weave ref to the local instance."""
    ref = weave.publish(model, name=RESEARCHER_MODEL_OBJECT_NAME)
    ref_uri = weave_ref_uri(ref)
    model._researcher_model_ref = ref_uri
    return ref_uri


def safe_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()
    return slug or next(tempfile._get_candidate_names())


def _run_config(
    *,
    workflow_name: str | None,
    day: str | None,
    run_id: str | None,
    stage: str,
    trace_id: str | None,
    metadata: dict[str, Any] | None,
) -> RunConfig | None:
    if workflow_name is None or day is None or run_id is None:
        return None
    trace_metadata = {"day": day, "run_id": run_id, "stage": stage}
    if metadata:
        trace_metadata.update(metadata)
    return RunConfig(
        workflow_name=workflow_name,
        trace_id=trace_id,
        group_id=run_id,
        trace_metadata=trace_metadata,
    )


def _extract_usage(result) -> tuple[int, int, float]:
    try:
        usage = result.raw_responses[-1].usage
        prompt_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0)
        cost_usd = (prompt_tokens * 5 + completion_tokens * 15) / 1_000_000
        return prompt_tokens, completion_tokens, cost_usd
    except Exception:
        return 0, 0, 0.0
