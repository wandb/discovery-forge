"""Orchestrator: flow control, cost tracking, and Weave tracing setup."""

import hashlib
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
    """Weave processor tuned for readable autoresearch agent traces."""

    def __init__(self) -> None:
        super().__init__()
        self._hidden_span_parent_calls = {}
        self._discovery_candidates: dict[str, list[dict[str, Any]]] = {}
        self._discovery_rejections: dict[str, list[dict[str, Any]]] = {}

    def on_trace_start(self, trace) -> None:
        super().on_trace_start(trace)
        trace_call = self._trace_calls.get(trace.trace_id)
        if trace_call is not None:
            _AGENT_TRACE_CALLS[trace.trace_id] = (
                getattr(trace_call, "id", None),
                getattr(trace_call, "ui_url", None) or getattr(trace_call, "url", None),
            )

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
            self._collect_discovery_function_call(span)
        super().on_span_end(span)

    def _agent_log_data(self, span):
        data = super()._agent_log_data(span)
        if getattr(span.span_data, "name", None) == "DiscoveryAgent":
            candidates = self._discovery_candidates.get(span.trace_id, [])
            rejections = self._discovery_rejections.get(span.trace_id, [])
            data["outputs"] = {
                "review_markdown": render_discovery_review_markdown(candidates, rejections),
                "candidate_count": len(candidates),
                "rejected_count": len(rejections),
            }
        return data

    def _collect_discovery_function_call(self, span) -> None:
        tool_name = getattr(span.span_data, "name", "")
        if tool_name not in {"save_candidate_tool", "save_rejected_candidate_tool"}:
            return

        payload = parse_tool_input(getattr(span.span_data, "input", None))
        if not payload:
            return

        trace_id = span.trace_id
        if tool_name == "save_candidate_tool":
            self._discovery_candidates.setdefault(trace_id, []).append(payload)
        else:
            self._discovery_rejections.setdefault(trace_id, []).append(payload)


def get_agent_trace_call_metadata(trace_id: str) -> tuple[str | None, str | None]:
    """Return the Weave call id/url created for an Agents SDK trace."""
    return _AGENT_TRACE_CALLS.get(trace_id, (None, None))


def init_observability(week_id: str):
    """Initialize W&B Weave tracing. Call exactly once per app lifecycle."""
    client = weave.init("wandb-smle/autoresearch-researcher")
    patch_weave_agent_span_names()
    set_trace_processors([AutoresearchWeaveTracingProcessor()])
    return client


def create_run_id(week: str) -> str:
    """Return a stable-looking unique ID for linking weekly and per-tool traces."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{week}-{stamp}-{uuid4().hex[:8]}"


def prompt_hash(agent_name: str) -> str:
    """Hash an instruction file so traces can be tied to prompt versions."""
    from autoresearch_researcher.agents.discovery import load_instructions

    return hashlib.sha256(load_instructions(agent_name).encode("utf-8")).hexdigest()[:12]


def ensure_run_metadata(
    metadata_path: Path,
    *,
    week: str,
    run_id: str,
    prompt_hashes: dict[str, str],
) -> None:
    """Merge run identity and prompt versions into run_metadata.json."""
    data: dict[str, Any] = {}
    if metadata_path.exists():
        data = json.loads(metadata_path.read_text())
    data.setdefault("week", week)
    data["run_id"] = run_id
    data["prompt_hashes"] = prompt_hashes
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
    """Merge high-level weekly trace counters into run_metadata.json."""
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


def render_discovery_review_markdown(
    candidates: list[dict[str, Any]],
    rejections: list[dict[str, Any]] | None = None,
) -> str:
    """Render DiscoveryAgent output as a reviewer-friendly Markdown table."""
    rejections = rejections or []
    lines = [
        "# Discovery Results",
        "",
        f"Accepted candidates: {len(candidates)}",
        f"Rejected candidates: {len(rejections)}",
        "",
    ]

    if candidates:
        lines.extend([
            "## Candidate Tools",
            "",
            "| Name | Representative URL | Category | Release / First Seen | Why Candidate |",
            "|---|---|---|---|---|",
        ])
        for item in candidates:
            lines.append(
                "| "
                + " | ".join([
                    _md_cell(item.get("name")),
                    _md_cell(item.get("url")),
                    _md_cell(item.get("category")),
                    _md_cell(item.get("release_date") or item.get("first_seen") or "unknown"),
                    _md_cell(item.get("description")),
                ])
                + " |"
            )
        lines.append("")
    else:
        lines.extend(["No accepted candidates were saved.", ""])

    if rejections:
        lines.extend([
            "## Rejected During Discovery",
            "",
            "| Name | URL | Category | Reason |",
            "|---|---|---|---|",
        ])
        for item in rejections:
            lines.append(
                "| "
                + " | ".join([
                    _md_cell(item.get("name")),
                    _md_cell(item.get("url")),
                    _md_cell(item.get("category")),
                    _md_cell(item.get("rejection_reason")),
                ])
                + " |"
            )
        lines.append("")

    return "\n".join(lines)


def name_to_slug(name: str) -> str:
    """Convert a tool name to a filesystem-safe slug."""
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def backup_week_dir(week_dir: Path) -> Path:
    """
    Rename week_dir to a numbered backup and return the backup path.
    Leaves week_dir non-existent so a fresh run can recreate it.
    """
    parent = week_dir.parent
    base = week_dir.name
    n = 1
    while True:
        backup = parent / f"{base}_backup_{n}"
        if not backup.exists():
            shutil.move(str(week_dir), str(backup))
            return backup
        n += 1


def should_skip_discovery(output_dir: Path) -> bool:
    """Return True if a non-empty _candidates.jsonl already exists."""
    candidates_file = output_dir / "_candidates.jsonl"
    if not candidates_file.exists():
        return False
    content = candidates_file.read_text().strip()
    return bool(content)


def get_unprofiled_candidates(output_dir: Path) -> list:
    """Return candidates that have not yet been profiled (no tools/{slug}.md)."""
    from autoresearch_researcher.tools.persistence import load_candidates
    candidates_file = output_dir / "_candidates.jsonl"
    tools_dir = output_dir / "tools"
    candidates = load_candidates(candidates_file)
    profiled_slugs = {f.stem for f in tools_dir.glob("*.md")} if tools_dir.exists() else set()
    return [c for c in candidates if name_to_slug(c.name) not in profiled_slugs]


def append_profile_run(output_dir: Path, record: dict[str, Any]) -> None:
    """Append one per-tool profiling trace link to _profile_runs.jsonl."""
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
    week: str,
    run_id: str,
    stage: str,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RunConfig:
    """Build a named Agents SDK trace config for a pipeline stage."""
    trace_metadata = {"week": week, "run_id": run_id, "stage": stage}
    if metadata:
        trace_metadata.update(metadata)
    return RunConfig(
        workflow_name=workflow_name,
        trace_id=trace_id,
        group_id=run_id,
        trace_metadata=trace_metadata,
    )


def _profile_status_from_files(
    output_dir: Path,
    *,
    candidate_name: str,
    new_before: int,
    updated_before: int,
    rejected_before: int,
) -> dict[str, Any]:
    """Infer accepted/rejected result from profiler tool output files."""
    new_rows = load_jsonl(output_dir / "_new_candidates.jsonl")
    updated_rows = load_jsonl(output_dir / "_updated_tools.jsonl")
    rejected_rows = load_jsonl(output_dir / "_rejected_profiles.jsonl")

    for row in new_rows[new_before:]:
        return {
            "status": "accepted",
            "slug": row.get("slug") or name_to_slug(row.get("name", candidate_name)),
            "rejection_reason": None,
        }
    for row in updated_rows[updated_before:]:
        return {
            "status": "accepted",
            "slug": row.get("slug") or name_to_slug(row.get("name", candidate_name)),
            "rejection_reason": None,
        }
    for row in rejected_rows[rejected_before:]:
        return {
            "status": "rejected",
            "slug": row.get("slug") or name_to_slug(row.get("name", candidate_name)),
            "rejection_reason": row.get("rejection_reason"),
        }
    return {"status": "unknown", "slug": name_to_slug(candidate_name), "rejection_reason": None}


async def profile_tool_candidate(
    *,
    candidate,
    week: str,
    run_id: str,
    output_dir: Path,
    registry,
    profiler_prompt_hash: str,
) -> tuple[int, int, float, dict[str, Any]]:
    """Profile a single candidate as a named Agents SDK root trace."""
    from autoresearch_researcher.agents.profiler import build_profiler_agent

    workflow_name = f"stage2_profile_{name_to_slug(candidate.name)}"
    profile_trace_id = gen_trace_id()
    new_before = len(load_jsonl(output_dir / "_new_candidates.jsonl"))
    updated_before = len(load_jsonl(output_dir / "_updated_tools.jsonl"))
    rejected_before = len(load_jsonl(output_dir / "_rejected_profiles.jsonl"))

    profile_prompt = (
        f"Profile this tool candidate and determine if it is in scope:\n"
        f"Name: {candidate.name}\nURL: {candidate.url}\nDescription: {candidate.description}"
    )
    profiler_agent = build_profiler_agent(
        output_dir=output_dir, registry=registry, week=week,
    )

    with weave.attributes({
        "week": week,
        "run_id": run_id,
        "stage": "profiling",
        "tool_name": candidate.name,
        "candidate_url": candidate.url,
        "profiler_prompt_hash": profiler_prompt_hash,
    }):
        prof_result = await Runner.run(
            profiler_agent,
            input=profile_prompt,
            max_turns=15,
            run_config=stage_run_config(
                workflow_name=workflow_name,
                week=week,
                run_id=run_id,
                stage="profiling",
                trace_id=profile_trace_id,
                metadata={
                    "tool_name": candidate.name,
                    "candidate_url": candidate.url,
                    "profiler_prompt_hash": profiler_prompt_hash,
                },
            ),
        )

    usage = _extract_usage(prof_result)
    call_id, trace_url = get_agent_trace_call_metadata(profile_trace_id)
    status = _profile_status_from_files(
        output_dir,
        candidate_name=candidate.name,
        new_before=new_before,
        updated_before=updated_before,
        rejected_before=rejected_before,
    )
    record = {
        "week": week,
        "run_id": run_id,
        "slug": status["slug"],
        "name": candidate.name,
        "url": candidate.url,
        "status": status["status"],
        "rejection_reason": status["rejection_reason"],
        "agent_trace_id": profile_trace_id,
        "workflow_name": workflow_name,
        "weave_call_id": call_id,
        "trace_url": trace_url,
        "profiler_prompt_hash": profiler_prompt_hash,
        "prompt_tokens": usage[0],
        "completion_tokens": usage[1],
        "cost_usd": usage[2],
    }
    append_profile_run(output_dir, record)
    return usage[0], usage[1], usage[2], record

async def run_briefing(
    week: str,
    output_dir: Path,
    max_tools: int,
    max_cost_usd: float,
    dry_run: bool,
) -> None:
    """
    Full pipeline: Discovery → Profiling → Writing.

    Respects max_cost_usd; preserves partial outputs on budget exceeded.
    Weave tracing must be initialized before calling this (init_observability).
    """
    from autoresearch_researcher.agents.discovery import build_discovery_agent
    from autoresearch_researcher.agents.writer import build_writer_agent, generate_highlights
    from autoresearch_researcher.tools.persistence import load_candidates
    from autoresearch_researcher.tools.registry import ToolRegistry

    metadata_path = output_dir / "run_metadata.json"
    run_id = create_run_id(week)
    prompt_hashes = {
        "discovery": prompt_hash("discovery"),
        "profiler": prompt_hash("profiler"),
        "writer": prompt_hash("writer"),
    }
    ensure_run_metadata(metadata_path, week=week, run_id=run_id, prompt_hashes=prompt_hashes)

    budget = CostBudget(max_usd=max_cost_usd)
    prompt_tokens = 0
    completion_tokens = 0
    total_cost = 0.0
    discovery_count = 0
    profiled_count = 0
    accepted_count = 0
    rejected_count = 0

    candidates_file = output_dir / "_candidates.jsonl"
    registry_dir = output_dir.parent / "_registry"
    registry = ToolRegistry.load(registry_dir)
    print(f"[orchestrator] Registry loaded: {len(registry.get_all_entries())} known tools")

    if dry_run:
        # In dry-run mode, skip real LLM calls; create placeholder outputs
        _write_dry_run_outputs(
            output_dir,
            week,
            run_id=run_id,
            profiler_prompt_hash=prompt_hashes["profiler"],
        )
        update_metadata_counts(
            metadata_path,
            discovery_count=_DRY_RUN_TOOL_COUNT,
            profiled_count=_DRY_RUN_TOOL_COUNT,
            accepted_count=_DRY_RUN_TOOL_COUNT,
            rejected_count=0,
        )
        update_metadata_costs(metadata_path, 0.0, 0, 0)
        return

    try:
        # ── Stage 1: Discovery (skip if _candidates.jsonl already exists) ─────
        if should_skip_discovery(output_dir):
            print(f"[orchestrator] Skipping Discovery — {candidates_file} already exists.")
        else:
            discovery_agent = build_discovery_agent(
                output_dir=output_dir, max_tools=max_tools, registry=registry,
            )
            discovery_prompt = (
                f"Discover experiment-automation tools for the week of {week}. "
                f"Find up to {max_tools} candidates and save them. "
                "For each URL, first call is_known_tool to skip ones already in the registry."
            )
            with weave.attributes({
                "week": week,
                "run_id": run_id,
                "stage": "discovery",
                "discovery_prompt_hash": prompt_hashes["discovery"],
            }):
                disc_result = await Runner.run(
                    discovery_agent,
                    input=discovery_prompt,
                    max_turns=120,
                    run_config=stage_run_config(
                        workflow_name="stage1_discovery",
                        week=week,
                        run_id=run_id,
                        stage="discovery",
                        metadata={"discovery_prompt_hash": prompt_hashes["discovery"]},
                    ),
                )

            usage = _extract_usage(disc_result)
            prompt_tokens += usage[0]
            completion_tokens += usage[1]
            total_cost += usage[2]
            budget.add(usage[2])

        # ── Stage 2: Profiling (registry-aware) ───────────────────────────────
        candidates = load_candidates(candidates_file)
        discovery_count = len(candidates)
        # Filter out candidates that are already in the global registry
        candidates = [c for c in candidates if not registry.contains(c.url)]
        print(f"[orchestrator] Profiling {len(candidates)} new candidates (registry already has known ones)")

        for candidate in candidates:
            budget.check()
            with weave.attributes({
                "week": week,
                "run_id": run_id,
                "stage": "profiling",
                "tool_name": candidate.name,
                "candidate_url": candidate.url,
                "profiler_prompt_hash": prompt_hashes["profiler"],
            }):
                usage_p, usage_c, usage_cost, record = await profile_tool_candidate(
                    candidate=candidate,
                    week=week,
                    run_id=run_id,
                    output_dir=output_dir,
                    registry=registry,
                    profiler_prompt_hash=prompt_hashes["profiler"],
                )
            prompt_tokens += usage_p
            completion_tokens += usage_c
            total_cost += usage_cost
            budget.add(usage_cost)
            profiled_count += 1
            if record["status"] == "accepted":
                accepted_count += 1
            elif record["status"] == "rejected":
                rejected_count += 1

        # ── Stage 3: Writing ──────────────────────────────────────────────────
        # Build highlights from this week's _new_candidates / _updated_tools
        highlights_md = generate_highlights(output_dir, week=week)
        (output_dir / "highlights.md").write_text(highlights_md)

        # Writer reads from the global registry, not week_dir/tools/
        writer_agent = build_writer_agent(
            output_dir=output_dir, week=week, registry=registry,
        )
        write_prompt = (
            f"Generate the weekly briefing for {week}. "
            "Call read_tool_profiles_tool to load profiles from the global registry, "
            "then incorporate the pre-generated highlights from highlights.md, "
            "and save the final draft via save_draft_tool and save_comparison_table_tool."
        )
        with weave.attributes({
            "week": week,
            "run_id": run_id,
            "stage": "writing",
            "writer_prompt_hash": prompt_hashes["writer"],
        }):
            write_result = await Runner.run(
                writer_agent,
                input=write_prompt,
                max_turns=20,
                run_config=stage_run_config(
                    workflow_name="stage3_writer",
                    week=week,
                    run_id=run_id,
                    stage="writing",
                    metadata={"writer_prompt_hash": prompt_hashes["writer"]},
                ),
            )

        usage = _extract_usage(write_result)
        prompt_tokens += usage[0]
        completion_tokens += usage[1]
        total_cost += usage[2]

    except BudgetExceededError:
        # Partial outputs already on disk — do not clean up
        raise

    finally:
        update_metadata_counts(
            metadata_path,
            discovery_count=discovery_count,
            profiled_count=profiled_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
        )
        if metadata_path.exists():
            update_metadata_costs(metadata_path, total_cost, prompt_tokens, completion_tokens)


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
    week: str,
    *,
    run_id: str | None = None,
    profiler_prompt_hash: str | None = None,
) -> None:
    """
    Create synthetic placeholder output files for dry-run mode.
    Generates exactly _DRY_RUN_TOOL_COUNT in-scope experiment-automation tool profiles.
    """
    import yaml

    tools_dir = output_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    sources_file = output_dir / "sources.jsonl"
    candidates_lines = []

    for i in range(_DRY_RUN_TOOL_COUNT):
        slug = f"synthetic-exp-tool-{i}"
        name = f"Synthetic Experiment Tool {i}"
        category = _DRY_RUN_CATEGORIES[i % len(_DRY_RUN_CATEGORIES)]
        description = _DRY_RUN_DESCRIPTIONS[i % len(_DRY_RUN_DESCRIPTIONS)]

        candidates_lines.append(json.dumps({
            "name": name, "url": f"https://example-{i}.com",
            "description": description, "category": category,
        }))

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
            f"## Known Limitations\n- Dry run synthetic entry [^{i+1}]\n"
        )
        profile_md = "---\n" + yaml.dump(front, allow_unicode=True, sort_keys=False) + "---\n\n" + body
        (tools_dir / f"{slug}.md").write_text(profile_md)

        from datetime import datetime, timezone
        source = json.dumps({
            "id": i + 1,
            "url": f"https://example-{i}.com",
            "title": f"Example Source {i}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "used_in": [slug],
        })
        with sources_file.open("a") as f:
            f.write(source + "\n")

        append_profile_run(output_dir, {
            "week": week,
            "run_id": run_id,
            "slug": slug,
            "name": name,
            "url": f"https://example-{i}.com",
            "status": "accepted",
            "rejection_reason": None,
            "agent_trace_id": None,
            "workflow_name": f"stage2_profile_{slug}",
            "weave_call_id": None,
            "trace_url": None,
            "profiler_prompt_hash": profiler_prompt_hash,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        })

    (output_dir / "_candidates.jsonl").write_text("\n".join(candidates_lines) + "\n")

    # Build comparison table from synthetic profiles
    from autoresearch_researcher.agents.writer import load_tool_profiles_from_dir, generate_comparison_table
    profiles = load_tool_profiles_from_dir(tools_dir)
    table = generate_comparison_table(profiles)
    (output_dir / "comparison_table.md").write_text(table)

    # Build draft with all citations
    draft_lines = [
        f"# Weekly Briefing: Experiment-Automation Tools",
        f"**Week**: {week}",
        f"**Published**: (dry run)",
        f"**Tools covered**: {_DRY_RUN_TOOL_COUNT}",
        f"**Sources**: {_DRY_RUN_TOOL_COUNT}",
        "",
        "## This Week's Highlights",
        "",
        "First issue — baseline established.",
        "",
    ]
    for i in range(_DRY_RUN_TOOL_COUNT):
        slug = f"synthetic-exp-tool-{i}"
        draft_lines += [f"## Synthetic Experiment Tool {i}", "", f"Dry run entry. [^{i+1}]", ""]

    draft_lines += ["## References", ""]
    for i in range(_DRY_RUN_TOOL_COUNT):
        draft_lines.append(f"[^{i+1}]: https://example-{i}.com")

    (output_dir / "draft.md").write_text("\n".join(draft_lines) + "\n")
