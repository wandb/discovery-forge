"""W&B Weave setup and Agents SDK trace shaping for discovery-forge."""

from __future__ import annotations

import json
import os
from typing import Any

import weave
from agents import set_trace_processors
from agents.tracing import AgentSpanData, FunctionSpanData, TaskSpanData, TurnSpanData
from weave.integrations.openai_agents import openai_agents as weave_openai_agents
from weave.integrations.openai_agents.openai_agents import WeaveTracingProcessor
from weave.trace.context.weave_client_context import get_weave_client

from discovery_forge.review import profile_review_output

_AGENT_TRACE_CALLS: dict[str, tuple[str | None, str | None]] = {}


def patch_weave_agent_span_names() -> None:
    """Teach Weave's Agents integration to name SDK task/turn spans."""
    if getattr(weave_openai_agents, "_discovery_forge_span_names_patched", False):
        return

    original_call_name = weave_openai_agents._call_name

    def named_call(span) -> str:
        span_data = getattr(span, "span_data", None)
        if isinstance(span_data, TaskSpanData):
            return span_data.name
        if isinstance(span_data, TurnSpanData):
            return f"{span_data.agent_name} turn {span_data.turn}"
        return original_call_name(span)

    weave_openai_agents._call_name = named_call
    weave_openai_agents._discovery_forge_span_names_patched = True


class DiscoveryForgeWeaveTracingProcessor(WeaveTracingProcessor):
    """Weave processor tuned for readable single-agent research traces."""

    def __init__(self) -> None:
        super().__init__()
        self._hidden_span_parent_calls = {}
        self._accepted_profiles: dict[str, dict[str, Any]] = {}
        self._rejected_profiles: dict[str, dict[str, Any]] = {}
        self._no_new_results: dict[str, dict[str, Any]] = {}
        self._search_queries: dict[str, list[str]] = {}

    def on_trace_start(self, trace) -> None:
        super().on_trace_start(trace)
        if trace.trace_id in self._trace_data:
            self._trace_data[trace.trace_id]["metadata"] = _trace_metadata(trace)
        trace_call = self._trace_calls.get(trace.trace_id)
        if trace_call is not None:
            _AGENT_TRACE_CALLS[trace.trace_id] = (
                getattr(trace_call, "id", None),
                getattr(trace_call, "ui_url", None) or getattr(trace_call, "url", None),
            )

    def on_trace_end(self, trace) -> None:
        if (wc := get_weave_client()) is None:
            return

        tid = trace.trace_id
        if tid not in self._trace_data or tid not in self._trace_calls:
            return

        self._ended_traces.add(tid)
        call = self._trace_calls[tid]

        # The workflow_name is fixed before search, so relabel after a tool is known.
        if trace.name and trace.name.startswith("research_run_"):
            self._set_research_display_name(call, tid)

        output: dict[str, Any] = {}
        output.update(self._review_output_for_trace(tid, trace.name))
        wc.finish_call(call, output=output)

        self._trace_calls.pop(tid, None)
        self._trace_data.pop(tid, None)
        self._ended_traces.discard(tid)
        self._accepted_profiles.pop(tid, None)
        self._rejected_profiles.pop(tid, None)
        self._no_new_results.pop(tid, None)
        self._search_queries.pop(tid, None)

    def _get_parent_call(self, span):
        parent_span_id = getattr(span, "parent_id", None)
        if parent_span_id is not None:
            if call := self._span_calls.get(parent_span_id):
                return call
            if call := self._hidden_span_parent_calls.get(parent_span_id):
                return call
        if call := self._trace_calls.get(span.trace_id):
            return call
        return None

    def on_span_start(self, span) -> None:
        span_data = getattr(span, "span_data", None)
        if isinstance(span_data, TaskSpanData | TurnSpanData):
            if parent_call := self._get_parent_call(span):
                self._hidden_span_parent_calls[span.span_id] = parent_call
            return

        super().on_span_start(span)

        if isinstance(span_data, AgentSpanData):
            agent_call = self._span_calls.get(span.span_id)
            parent_span_id = getattr(span, "parent_id", None)
            if agent_call is not None and parent_span_id in self._hidden_span_parent_calls:
                self._hidden_span_parent_calls[parent_span_id] = agent_call

    def on_span_end(self, span) -> None:
        span_data = getattr(span, "span_data", None)
        if isinstance(span_data, TaskSpanData | TurnSpanData):
            return
        if isinstance(span_data, FunctionSpanData):
            self._collect_review_function_call(span)
        super().on_span_end(span)

    def _agent_log_data(self, span):
        data = super()._agent_log_data(span)
        if getattr(span.span_data, "name", None) == "ResearcherAgent":
            data["outputs"] = self._research_review_output_for_trace(span.trace_id)
        return data

    def _review_output_for_trace(self, trace_id: str, trace_name: str) -> dict[str, Any]:
        if trace_name and trace_name.startswith("research_run_"):
            return self._research_review_output_for_trace(trace_id)
        return {}

    def _research_display_name(self, trace_id: str) -> str | None:
        """Display name for a finished research trace, if the tool is known."""
        profile = (
            self._accepted_profiles.get(trace_id)
            or self._rejected_profiles.get(trace_id)
            or self._no_new_results.get(trace_id)
        )
        if not profile:
            return None
        name = profile.get("name") or profile.get("slug")
        return f"research_{name}" if name else None

    def _set_research_display_name(self, call, trace_id: str) -> None:
        """Relabel a research call with a tool-specific display name (best-effort)."""
        display = self._research_display_name(trace_id)
        if not display:
            return
        setter = getattr(call, "set_display_name", None)
        if setter is None:
            return
        try:
            setter(display)
        except Exception:
            pass

    def _research_review_output_for_trace(self, trace_id: str) -> dict[str, Any]:
        search_queries = self._search_queries.get(trace_id, [])
        metadata = (self._trace_data.get(trace_id) or {}).get("metadata", {})
        common = {
            "search_queries": search_queries,
            "search_backend": metadata.get("search_backend"),
            "search_recency": metadata.get("recency"),
            "workflow_name": metadata.get("workflow_name"),
            "researcher_prompt_ref": metadata.get("researcher_prompt_ref"),
            "researcher_prompt_hash": metadata.get("researcher_prompt_hash"),
        }
        if trace_id in self._accepted_profiles:
            return profile_review_output(
                self._accepted_profiles[trace_id],
                status="accepted",
                **common,
            )
        if trace_id in self._rejected_profiles:
            return profile_review_output(
                self._rejected_profiles[trace_id],
                status="rejected",
                **common,
            )
        if trace_id in self._no_new_results:
            return profile_review_output(
                self._no_new_results[trace_id],
                status="no_new",
                **common,
            )
        return profile_review_output({}, status="unknown", **common)

    def _collect_review_function_call(self, span) -> None:
        tool_name = getattr(span.span_data, "name", "")
        payload = parse_tool_input(getattr(span.span_data, "input", None))
        if not payload:
            return

        trace_id = span.trace_id
        if tool_name == "search_web":
            query = payload.get("query")
            if isinstance(query, str) and query.strip():
                self._search_queries.setdefault(trace_id, []).append(query.strip())
        elif tool_name == "save_tool_profile_tool":
            self._accepted_profiles[trace_id] = payload
        elif tool_name == "save_rejected_profile_tool":
            self._rejected_profiles[trace_id] = payload
        elif tool_name == "report_no_new_tool":
            self._no_new_results[trace_id] = {
                "slug": "no-new-finding",
                "name": "No new finding",
                "verdict_reason": payload.get("reason"),
            }


def get_agent_trace_call_metadata(trace_id: str) -> tuple[str | None, str | None]:
    """Return the Weave call id/url created for an Agents SDK trace."""
    return _AGENT_TRACE_CALLS.get(trace_id, (None, None))


def weave_project_path() -> str:
    """Resolve the Weave ``entity/project`` from required env vars."""
    entity = os.environ.get("WANDB_ENTITY", "").strip()
    project = os.environ.get("WANDB_PROJECT", "").strip()
    missing = []
    if not entity:
        missing.append("WANDB_ENTITY")
    if not project:
        missing.append("WANDB_PROJECT")
    if missing:
        raise ValueError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env before running. Copy .env.example and fill "
            "WANDB_ENTITY=<your-wandb-entity>; WANDB_PROJECT=discovery-forge is the hands-on default."
        )
    return f"{entity}/{project}"


def init_observability(day_id: str):
    """Initialize W&B Weave tracing. Call exactly once per app lifecycle."""
    client = weave.init(weave_project_path())
    patch_weave_agent_span_names()
    set_trace_processors([DiscoveryForgeWeaveTracingProcessor()])
    return client


def parse_tool_input(input_value: Any) -> dict[str, Any]:
    """Parse an Agents SDK function-tool input payload into a dict."""
    if isinstance(input_value, dict):
        return input_value
    if not isinstance(input_value, str):
        return {}
    try:
        parsed = json.loads(input_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _trace_metadata(trace) -> dict[str, Any]:
    try:
        exported = trace.export() or {}
    except Exception:
        return {}
    metadata = exported.get("metadata")
    return metadata if isinstance(metadata, dict) else {}
