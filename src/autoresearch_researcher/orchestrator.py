"""Orchestrator: flow control, cost tracking, and Weave tracing setup.

The pipeline is a single ResearcherAgent run sequentially up to ``max_tools``
times. Each run finds one experiment-automation tool not yet covered, profiles
it, and saves a canonical profile (or rejects it). The reviewable trace unit is
``stage_research_{i}`` -> ``ResearcherAgent``. After the loop, ``build_feed_output``
turns the saved profiles into ``items/*`` + ``manifest.json``.
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import weave
from agents import RunConfig, Runner, gen_trace_id, set_trace_processors
from agents.tracing import AgentSpanData, FunctionSpanData, TaskSpanData, TurnSpanData
from weave.integrations.openai_agents import openai_agents as weave_openai_agents
from weave.integrations.openai_agents.openai_agents import WeaveTracingProcessor
from weave.trace.context.weave_client_context import get_weave_client

from autoresearch_researcher.tools.search import DEFAULT_SEARCH_BACKEND, RecencyWindow, SearchBackend


_AGENT_TRACE_CALLS: dict[str, tuple[str | None, str | None]] = {}


class BudgetExceededError(Exception):
    """Raised when the cumulative API cost exceeds the configured limit."""

    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        super().__init__(f"Budget exceeded: ${spent:.4f} spent, limit ${limit:.2f}")


class CostBudget:
    """Tracks cumulative USD cost and enforces a hard ceiling."""

    def __init__(self, max_usd: float) -> None:
        self._max = max_usd
        self._total = 0.0

    @property
    def total_usd(self) -> float:
        return self._total

    def add(self, amount_usd: float) -> None:
        self._total += amount_usd
        self.check()

    def check(self) -> None:
        if self._total > self._max:
            raise BudgetExceededError(spent=self._total, limit=self._max)


def patch_weave_agent_span_names() -> None:
    """Teach Weave's Agents integration to name SDK task/turn spans."""
    if getattr(weave_openai_agents, "_autoresearch_span_names_patched", False):
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
    weave_openai_agents._autoresearch_span_names_patched = True


class AutoresearchWeaveTracingProcessor(WeaveTracingProcessor):
    """Weave processor tuned for readable single-agent research traces."""

    def __init__(self) -> None:
        super().__init__()
        self._hidden_span_parent_calls = {}
        self._accepted_profiles: dict[str, dict[str, Any]] = {}
        self._rejected_profiles: dict[str, dict[str, Any]] = {}

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

        trace_data = self._trace_data[tid]
        self._ended_traces.add(tid)
        call = self._trace_calls[tid]

        # The workflow_name (stage_research_{i}) is fixed before the search runs,
        # so the tool isn't known yet. Once the agent has saved/rejected a profile
        # we relabel the call's display name with the tool name for easy review.
        if trace.name and trace.name.startswith("stage_research_"):
            self._set_research_display_name(call, tid)

        output = {
            "status": "completed",
            "metrics": trace_data.get("metrics", {}),
            "metadata": trace_data.get("metadata", {}),
        }
        output.update(self._review_output_for_trace(tid, trace.name))
        wc.finish_call(call, output=output)

        self._trace_calls.pop(tid, None)
        self._trace_data.pop(tid, None)
        self._ended_traces.discard(tid)
        self._accepted_profiles.pop(tid, None)
        self._rejected_profiles.pop(tid, None)

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

        # Tool/function spans are often children of hidden turn spans. Once the
        # visible agent call exists, route that hidden turn's later children to it.
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
        if trace_name and trace_name.startswith("stage_research_"):
            return self._research_review_output_for_trace(trace_id)
        return {}

    def _research_display_name(self, trace_id: str) -> str | None:
        """Tool name for a finished research trace (accepted or rejected), if known."""
        profile = self._accepted_profiles.get(trace_id) or self._rejected_profiles.get(trace_id)
        if not profile:
            return None
        name = profile.get("name") or profile.get("slug")
        return str(name) if name else None

    def _set_research_display_name(self, call, trace_id: str) -> None:
        """Relabel a research call with the tool name (best-effort; never fatal)."""
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
        if trace_id in self._accepted_profiles:
            return profile_review_output(self._accepted_profiles[trace_id], status="accepted")
        if trace_id in self._rejected_profiles:
            return profile_review_output(self._rejected_profiles[trace_id], status="rejected")
        return profile_review_output({}, status="unknown")

    def _collect_review_function_call(self, span) -> None:
        tool_name = getattr(span.span_data, "name", "")
        payload = parse_tool_input(getattr(span.span_data, "input", None))
        if not payload:
            return

        trace_id = span.trace_id
        if tool_name == "save_tool_profile_tool":
            self._accepted_profiles[trace_id] = payload
        elif tool_name == "save_rejected_profile_tool":
            self._rejected_profiles[trace_id] = payload


def get_agent_trace_call_metadata(trace_id: str) -> tuple[str | None, str | None]:
    """Return the Weave call id/url created for an Agents SDK trace."""
    return _AGENT_TRACE_CALLS.get(trace_id, (None, None))


def init_observability(day_id: str):
    """Initialize W&B Weave tracing. Call exactly once per app lifecycle."""
    client = weave.init("wandb-smle/autoresearch-researcher")
    patch_weave_agent_span_names()
    set_trace_processors([AutoresearchWeaveTracingProcessor()])
    return client


def create_run_id(day: str) -> str:
    """Return a stable-looking unique ID for linking daily and per-tool traces."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{day}-{stamp}-{uuid4().hex[:8]}"


def ensure_run_metadata(
    metadata_path: Path,
    *,
    day: str,
    run_id: str,
    prompt_hashes: dict[str, str],
    search_backend: str,
    prompt_refs: dict[str, str | None] | None = None,
) -> None:
    """Merge run identity and prompt versions into run_metadata.json."""
    data: dict[str, Any] = {}
    if metadata_path.exists():
        data = json.loads(metadata_path.read_text())
    data.setdefault("day", day)
    data["run_id"] = run_id
    data["prompt_hashes"] = prompt_hashes
    if prompt_refs is not None:
        data["prompt_refs"] = prompt_refs
    data["search_backend"] = search_backend
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(data, indent=2))


def update_metadata_costs(
    metadata_path: Path,
    total_cost_usd: float,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Merge cost/token telemetry into the existing run_metadata.json."""
    data: dict = {}
    if metadata_path.exists():
        data = json.loads(metadata_path.read_text())
    data["total_cost_usd"] = total_cost_usd
    data["prompt_tokens"] = prompt_tokens
    data["completion_tokens"] = completion_tokens
    metadata_path.write_text(json.dumps(data, indent=2))


def update_metadata_counts(
    metadata_path: Path,
    *,
    discovery_count: int,
    profiled_count: int,
    accepted_count: int,
    rejected_count: int,
) -> None:
    """Merge high-level daily trace counters into run_metadata.json."""
    data: dict[str, Any] = {}
    if metadata_path.exists():
        data = json.loads(metadata_path.read_text())
    data["discovery_count"] = discovery_count
    data["profiled_count"] = profiled_count
    data["accepted_count"] = accepted_count
    data["rejected_count"] = rejected_count
    metadata_path.write_text(json.dumps(data, indent=2))


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


def _md_cell(value: Any) -> str:
    text = "unknown" if value is None or value == "" else str(value)
    return text.replace("\n", "<br>").replace("|", "\\|")


def _trace_metadata(trace) -> dict[str, Any]:
    try:
        exported = trace.export() or {}
    except Exception:
        return {}
    metadata = exported.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def profile_review_output(profile: dict[str, Any], *, status: str) -> dict[str, Any]:
    """Return Annotation Queue-friendly research output fields."""
    from autoresearch_researcher.tools.feed import feed_metadata_for_profile

    slug = profile.get("slug") or "unknown"
    primary_url = (
        profile.get("github_url")
        or profile.get("project_url")
        or profile.get("paper_url")
        or profile.get("url")
        or "unknown"
    )
    output = {
        "profile_review_markdown": render_profile_review_markdown(profile, status=status),
        "verdict": status,
        "tool_name": profile.get("name") or "unknown",
        "slug": slug,
        "primary_url": primary_url,
        "rejection_reason": profile.get("rejection_reason"),
        "autonomy_level": profile.get("autonomy_level"),
        "domains": profile.get("domains"),
        "github_url": profile.get("github_url"),
        "paper_url": profile.get("paper_url"),
        "project_url": profile.get("project_url"),
        "key_limitations": profile.get("key_limitations"),
        "source_ids": profile.get("source_ids"),
        "profile_path": f"daily_runs/_registry/profiles/{slug}.md" if status == "accepted" else None,
        "prompt_ref": profile.get("researcher_prompt_ref"),
    }
    if status == "accepted":
        output.update(feed_metadata_for_profile(profile))
    else:
        output.update({
            "feed_item_id": None,
            "feed_item_path": None,
            "feed_dedupe_key": None,
            "feed_canonical_url": None,
            "feed_tags": [],
            "feed_manifest_path": None,
        })
    return output


def render_profile_review_markdown(profile: dict[str, Any], *, status: str) -> str:
    """Render ResearcherAgent output as a reviewer-friendly Markdown block."""
    name = profile.get("name") or "unknown"
    slug = profile.get("slug") or name_to_slug(name)
    primary_url = (
        profile.get("github_url")
        or profile.get("project_url")
        or profile.get("paper_url")
        or profile.get("url")
        or "unknown"
    )
    limitations = profile.get("key_limitations") or []
    if isinstance(limitations, str):
        limitations = [limitations]

    lines = [
        f"# Tool Profile Review: {name}",
        "",
        f"Verdict: {status}",
        f"Slug: {slug}",
        f"Primary URL: {primary_url}",
        "",
    ]

    if status == "rejected":
        lines.extend([
            "## Scope Decision",
            profile.get("rejection_reason") or "No rejection reason captured.",
            "",
        ])
    elif status == "accepted":
        lines.extend([
            "## Scope Decision",
            profile.get("autonomy_rationale") or "No autonomy rationale captured.",
            "",
            "## Key Metadata",
            f"- Autonomy: {_md_cell(profile.get('autonomy_level'))}",
            f"- Domains: {_md_cell(profile.get('domains'))}",
            f"- License: {_md_cell(profile.get('license'))}",
            f"- GitHub: {_md_cell(profile.get('github_url'))}",
            f"- Paper: {_md_cell(profile.get('paper_url'))}",
            f"- Project: {_md_cell(profile.get('project_url'))}",
            f"- Resource requirements: {_md_cell(profile.get('resource_requirements'))}",
            "",
            "## Known Limitations",
        ])
        if limitations:
            lines.extend(f"- {limitation}" for limitation in limitations)
        else:
            lines.append("- unknown")
        lines.append("")
    else:
        lines.extend([
            "## Scope Decision",
            "The agent did not call save_tool_profile or save_rejected_profile, so the result is unresolved.",
            "",
        ])

    lines.extend([
        "## Reviewer Checklist",
        "- Is the scope verdict correct?",
        "- Are sources primary and sufficient?",
        "- Is any metadata wrong or unverified?",
        "- Should this feedback become a prompt improvement?",
        "",
    ])
    return "\n".join(lines)


def name_to_slug(name: str) -> str:
    """Convert a tool name to a filesystem-safe slug."""
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def backup_run_dir(run_dir: Path) -> Path:
    """
    Rename run_dir to a numbered backup and return the backup path.
    Leaves run_dir non-existent so a fresh run can recreate it.
    """
    parent = run_dir.parent
    base = run_dir.name
    n = 1
    while True:
        backup = parent / f"{base}_backup_{n}"
        if not backup.exists():
            shutil.move(str(run_dir), str(backup))
            return backup
        n += 1


def append_profile_run(output_dir: Path, record: dict[str, Any]) -> None:
    """Append one per-tool research trace link to _profile_runs.jsonl."""
    path = output_dir / "_profile_runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL rows from a file that may not exist yet."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def stage_run_config(
    *,
    workflow_name: str,
    day: str,
    run_id: str,
    stage: str,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RunConfig:
    """Build a named Agents SDK trace config for a pipeline stage."""
    trace_metadata = {"day": day, "run_id": run_id, "stage": stage}
    if metadata:
        trace_metadata.update(metadata)
    return RunConfig(
        workflow_name=workflow_name,
        trace_id=trace_id,
        group_id=run_id,
        trace_metadata=trace_metadata,
    )


def build_exclusion_block(registry, output_dir: Path) -> str:
    """List tools already covered (registry + this run's rejections) for the prompt."""
    lines: list[str] = []
    seen: set[str] = set()
    for entry in registry.get_all_entries():
        key = (entry.url or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {entry.name} ({entry.url})")
    for row in load_jsonl(output_dir / "_rejected_profiles.jsonl"):
        url = (
            row.get("github_url")
            or row.get("project_url")
            or row.get("paper_url")
            or row.get("url")
            or ""
        )
        lines.append(f"- {row.get('name')} ({url}) [rejected]")
    return "\n".join(lines) if lines else "(none yet)"


def _registry_url_for_slug(registry, slug: str) -> str | None:
    for entry in registry.get_all_entries():
        if entry.slug == slug:
            return entry.url
    return None


def _iteration_outcome(
    output_dir: Path,
    *,
    new_before: int,
    updated_before: int,
    rejected_before: int,
    no_new_before: int,
) -> dict[str, Any]:
    """Infer what a single ResearcherAgent run produced, from its output files."""
    new_rows = load_jsonl(output_dir / "_new_candidates.jsonl")
    updated_rows = load_jsonl(output_dir / "_updated_tools.jsonl")
    rejected_rows = load_jsonl(output_dir / "_rejected_profiles.jsonl")
    no_new_rows = load_jsonl(output_dir / "_no_new_tool.jsonl")

    for row in reversed(new_rows[new_before:]):
        return {
            "status": "accepted",
            "slug": row.get("slug") or name_to_slug(row.get("name", "")),
            "name": row.get("name"),
            "rejection_reason": None,
            "stop": False,
        }
    for row in reversed(updated_rows[updated_before:]):
        return {
            "status": "accepted",
            "slug": row.get("slug") or name_to_slug(row.get("name", "")),
            "name": row.get("name"),
            "rejection_reason": None,
            "stop": False,
        }
    for row in reversed(rejected_rows[rejected_before:]):
        return {
            "status": "rejected",
            "slug": row.get("slug") or name_to_slug(row.get("name", "")),
            "name": row.get("name"),
            "url": (
                row.get("github_url")
                or row.get("project_url")
                or row.get("paper_url")
                or row.get("url")
            ),
            "rejection_reason": row.get("rejection_reason"),
            "stop": False,
        }
    if no_new_rows[no_new_before:]:
        return {"status": "no_new", "stop": True}
    return {"status": "unknown", "stop": True}


async def run_briefing(
    day: str,
    output_dir: Path,
    max_tools: int,
    max_cost_usd: float,
    dry_run: bool,
    search_backend: SearchBackend = DEFAULT_SEARCH_BACKEND,
    recency: RecencyWindow | None = None,
) -> None:
    """
    Single-agent pipeline: run ResearcherAgent up to ``max_tools`` times, each
    profiling one new tool, then build the Agentforge feed (items/* + manifest).

    Respects max_cost_usd; preserves partial outputs on budget exceeded.
    Weave tracing must be initialized before calling this (init_observability).
    """
    from autoresearch_researcher.agents.researcher import build_researcher_agent
    from autoresearch_researcher.tools.feed import build_feed_output
    from autoresearch_researcher.tools.prompts import (
        load_local_instruction_prompts,
        prompt_contents,
        prompt_hashes,
        prompt_refs,
        publish_instruction_prompts,
    )
    from autoresearch_researcher.tools.registry import ToolRegistry

    metadata_path = output_dir / "run_metadata.json"
    run_id = create_run_id(day)
    prompt_versions = (
        load_local_instruction_prompts(max_tools=max_tools)
        if dry_run
        else publish_instruction_prompts(max_tools=max_tools)
    )
    prompt_hash_map = prompt_hashes(prompt_versions)
    prompt_ref_map = prompt_refs(prompt_versions)
    prompt_content_map = prompt_contents(prompt_versions)
    ensure_run_metadata(
        metadata_path,
        day=day,
        run_id=run_id,
        prompt_hashes=prompt_hash_map,
        prompt_refs=prompt_ref_map,
        search_backend=search_backend,
    )

    budget = CostBudget(max_usd=max_cost_usd)
    prompt_tokens = 0
    completion_tokens = 0
    total_cost = 0.0
    profiled_count = 0
    accepted_count = 0
    rejected_count = 0

    registry_dir = output_dir.parent / "_registry"
    registry = ToolRegistry.load(registry_dir)
    print(f"[orchestrator] Registry loaded: {len(registry.get_all_entries())} known tools")

    if dry_run:
        _write_dry_run_outputs(
            output_dir,
            day,
            run_id=run_id,
            researcher_prompt_hash=prompt_hash_map["researcher"],
            search_backend=search_backend,
        )
        update_metadata_counts(
            metadata_path,
            discovery_count=_DRY_RUN_TOOL_COUNT,
            profiled_count=_DRY_RUN_TOOL_COUNT,
            accepted_count=_DRY_RUN_TOOL_COUNT,
            rejected_count=0,
        )
        update_metadata_costs(metadata_path, 0.0, 0, 0)
        build_feed_output(output_dir, registry=None, day=day)
        return

    try:
        for i in range(max_tools):
            budget.check()

            new_before = len(load_jsonl(output_dir / "_new_candidates.jsonl"))
            updated_before = len(load_jsonl(output_dir / "_updated_tools.jsonl"))
            rejected_before = len(load_jsonl(output_dir / "_rejected_profiles.jsonl"))
            no_new_before = len(load_jsonl(output_dir / "_no_new_tool.jsonl"))

            workflow_name = f"stage_research_{i + 1}"
            trace_id = gen_trace_id()
            exclusion_block = build_exclusion_block(registry, output_dir)
            recency_hint = (
                f" Prefer tools and sources from the last {recency}." if recency else ""
            )
            research_prompt = (
                f"Find ONE new experiment-automation tool for {day} and profile it.\n\n"
                "Already covered — do NOT re-profile any of these:\n"
                f"{exclusion_block}\n\n"
                "Search the web for a single in-scope tool that is not in the list above."
                f"{recency_hint} "
                "Call is_known_tool(url) before committing to a candidate. "
                "If in scope, save sources then call save_tool_profile_tool. "
                "If out of scope, call save_rejected_profile_tool with a clear reason. "
                "If you cannot find any new in-scope tool, call report_no_new_tool."
            )

            agent = build_researcher_agent(
                output_dir=output_dir,
                registry=registry,
                day=day,
                search_backend=search_backend,
                recency=recency,
                instructions_override=prompt_content_map["researcher"],
            )

            with weave.attributes({
                "day": day,
                "run_id": run_id,
                "stage": "research",
                "iteration": i + 1,
                "researcher_prompt_hash": prompt_hash_map["researcher"],
                "researcher_prompt_ref": prompt_ref_map["researcher"],
                "search_backend": search_backend,
            }):
                result = await Runner.run(
                    agent,
                    input=research_prompt,
                    max_turns=40,
                    run_config=stage_run_config(
                        workflow_name=workflow_name,
                        day=day,
                        run_id=run_id,
                        stage="research",
                        trace_id=trace_id,
                        metadata={
                            "iteration": i + 1,
                            "researcher_prompt_hash": prompt_hash_map["researcher"],
                            "researcher_prompt_ref": prompt_ref_map["researcher"],
                            "search_backend": search_backend,
                        },
                    ),
                )

            usage = _extract_usage(result)
            prompt_tokens += usage[0]
            completion_tokens += usage[1]
            total_cost += usage[2]

            outcome = _iteration_outcome(
                output_dir,
                new_before=new_before,
                updated_before=updated_before,
                rejected_before=rejected_before,
                no_new_before=no_new_before,
            )

            if outcome["status"] in ("accepted", "rejected"):
                call_id, trace_url = get_agent_trace_call_metadata(trace_id)
                url = outcome.get("url")
                if outcome["status"] == "accepted":
                    url = _registry_url_for_slug(registry, outcome["slug"])
                append_profile_run(output_dir, {
                    "day": day,
                    "run_id": run_id,
                    "slug": outcome["slug"],
                    "name": outcome.get("name"),
                    "url": url,
                    "status": outcome["status"],
                    "rejection_reason": outcome.get("rejection_reason"),
                    "agent_trace_id": trace_id,
                    "workflow_name": workflow_name,
                    "weave_call_id": call_id,
                    "trace_url": trace_url,
                    "researcher_prompt_hash": prompt_hash_map["researcher"],
                    "researcher_prompt_ref": prompt_ref_map["researcher"],
                    "search_backend": search_backend,
                    "prompt_tokens": usage[0],
                    "completion_tokens": usage[1],
                    "cost_usd": usage[2],
                })
                profiled_count += 1
                if outcome["status"] == "accepted":
                    accepted_count += 1
                else:
                    rejected_count += 1

            budget.add(usage[2])

            if outcome["stop"]:
                print(f"[orchestrator] Stopping after iteration {i + 1}: no new tool found.")
                break

    except BudgetExceededError:
        # Partial outputs already on disk — do not clean up
        raise

    finally:
        update_metadata_counts(
            metadata_path,
            discovery_count=profiled_count,
            profiled_count=profiled_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
        )
        if metadata_path.exists():
            update_metadata_costs(metadata_path, total_cost, prompt_tokens, completion_tokens)
        build_feed_output(output_dir, registry=registry, day=day)


def _extract_usage(result) -> tuple[int, int, float]:
    """Extract (prompt_tokens, completion_tokens, cost_usd) from a Runner result."""
    try:
        usage = result.raw_responses[-1].usage
        p = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0)
        c = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0)
        # Rough cost estimate: $5/1M input, $15/1M output (gpt-4o pricing)
        cost = (p * 5 + c * 15) / 1_000_000
        return p, c, cost
    except Exception:
        return 0, 0, 0.0


_DRY_RUN_TOOL_COUNT = 3

_DRY_RUN_CATEGORIES = [
    "ml-experiment-automation",
    "end-to-end-paper-generation",
    "hypothesis-generation",
]

_DRY_RUN_DESCRIPTIONS = [
    "Autonomously runs ML training experiments in a loop and generates a paper from results.",
    "Proposes scientific hypotheses, designs experiments, and produces full research reports.",
    "Executes chemistry synthesis experiments and writes lab reports with citations.",
]


def _write_dry_run_outputs(
    output_dir: Path,
    day: str,
    *,
    run_id: str | None = None,
    researcher_prompt_hash: str | None = None,
    search_backend: str | None = None,
) -> None:
    """
    Create synthetic placeholder output files for dry-run mode.
    Generates exactly _DRY_RUN_TOOL_COUNT in-scope experiment-automation tool profiles
    so the feed builder has profiles to turn into items/* + manifest.json.
    """
    import yaml

    tools_dir = output_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    new_candidates_file = output_dir / "_new_candidates.jsonl"

    for i in range(_DRY_RUN_TOOL_COUNT):
        slug = f"synthetic-exp-tool-{i}"
        name = f"Synthetic Experiment Tool {i}"
        category = _DRY_RUN_CATEGORIES[i % len(_DRY_RUN_CATEGORIES)]

        front = {
            "slug": slug, "name": name, "license": "MIT",
            "domains": [category.split("-")[0]],
            "autonomy_level": "Scientist",
            "autonomy_rationale": "Executes full experiment loop autonomously",
            "interface": "Python lib",
            "resource_requirements": "Single GPU",
            "last_commit": "2025-01-01", "stars": 300 + i * 100,
            "open_issues": 10, "pricing_note": "Free",
            "github_url": f"https://github.com/example/tool-{i}",
            "paper_url": None, "project_url": None,
            "source_ids": [i + 1],
        }
        body = (
            f"# {name}\n\n"
            f"**Autonomy level**: Scientist — Executes full experiment loop autonomously\n\n"
            f"## Known Limitations\n- Dry run synthetic entry\n"
        )
        profile_md = "---\n" + yaml.dump(front, allow_unicode=True, sort_keys=False) + "---\n\n" + body
        (tools_dir / f"{slug}.md").write_text(profile_md)

        with new_candidates_file.open("a") as f:
            f.write(json.dumps({"slug": slug, "name": name, "stars": front["stars"]}) + "\n")

        append_profile_run(output_dir, {
            "day": day,
            "run_id": run_id,
            "slug": slug,
            "name": name,
            "url": f"https://github.com/example/tool-{i}",
            "status": "accepted",
            "rejection_reason": None,
            "agent_trace_id": None,
            "workflow_name": f"stage_research_{i + 1}",
            "weave_call_id": None,
            "trace_url": None,
            "researcher_prompt_hash": researcher_prompt_hash,
            "search_backend": search_backend,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        })
