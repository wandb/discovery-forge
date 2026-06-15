"""Orchestrator: flow control, cost tracking, and Weave tracing setup.

The pipeline is a single ResearcherAgent run sequentially up to ``max_tools``
times. Each run finds one experiment-automation tool not yet covered, profiles
it, and saves a canonical profile (or rejects it). The reviewable trace unit is
``research_run_{i}`` -> ``ResearcherAgent``. After the loop, ``build_feed_output``
turns the saved profiles into ``items/*`` + ``manifest.json``.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import weave
from agents import RunConfig, gen_trace_id

from discovery_forge.observability import get_agent_trace_call_metadata
from discovery_forge.review import name_to_slug
from discovery_forge.tools.search import DEFAULT_SEARCH_BACKEND, RecencyWindow, SearchBackend

MAX_UNKNOWN_RETRIES = 5


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
    model_refs: dict[str, str | None] | None = None,
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
        data["researcher_prompt_ref"] = prompt_refs.get("researcher")
    if model_refs is not None:
        data["model_refs"] = model_refs
        data["researcher_model_ref"] = model_refs.get("researcher")
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
    no_new_count: int = 0,
    attempted_count: int | None = None,
) -> None:
    """Merge high-level daily trace counters into run_metadata.json."""
    data: dict[str, Any] = {}
    if metadata_path.exists():
        data = json.loads(metadata_path.read_text())
    data["discovery_count"] = discovery_count
    data["attempted_count"] = attempted_count if attempted_count is not None else discovery_count
    data["profiled_count"] = profiled_count
    data["accepted_count"] = accepted_count
    data["rejected_count"] = rejected_count
    data["no_new_count"] = no_new_count
    metadata_path.write_text(json.dumps(data, indent=2))


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


def append_no_new_tool(output_dir: Path, reason: str) -> None:
    """Append one no-new finding result to _no_new_tool.jsonl."""
    path = output_dir / "_no_new_tool.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"verdict_reason": reason}) + "\n")


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


def render_research_prompt(
    *,
    day: str,
    exclusion_block: str,
    iteration: int,
    recency: RecencyWindow | None = None,
) -> str:
    """Render the per-tool ResearcherAgent prompt."""
    recency_hint = f" Prefer tools and sources from the last {recency}." if recency else ""
    return (
        f"Find ONE new experiment-automation tool for {day} and profile it.\n\n"
        f"Iteration: {iteration}\n"
        "Use the Query Example Pool in your system instructions as inspiration, "
        "then write your own search queries for this run. "
        "Choose a different search angle than earlier runs when possible.\n\n"
        "Search budget:\n"
        "- Start with 2-3 adapted queries inspired by the pool.\n"
        "- Do not repeat the same broad query unless narrower searches fail.\n"
        "- Prefer choosing a promising candidate after 2-3 searches over exhaustive re-searching.\n\n"
        "Already covered — do NOT re-profile any of these:\n"
        f"{exclusion_block}\n\n"
        "Search the web for a single in-scope tool that is not in the list above."
        f"{recency_hint} "
        "Call is_known_tool(url) before committing to a candidate. "
        "If in scope, save sources then call save_tool_profile_tool. "
        "If out of scope, call save_rejected_profile_tool with a clear verdict_reason. "
        "If you cannot find any new in-scope tool, call report_no_new_tool."
    )


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
            "verdict_reason": None,
            "stop": False,
        }
    for row in reversed(updated_rows[updated_before:]):
        return {
            "status": "accepted",
            "slug": row.get("slug") or name_to_slug(row.get("name", "")),
            "name": row.get("name"),
            "verdict_reason": None,
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
            "verdict_reason": row.get("verdict_reason"),
            "stop": False,
        }
    if no_new_rows[no_new_before:]:
        row = no_new_rows[-1]
        return {
            "status": "no_new",
            "slug": "no-new-finding",
            "name": "No new finding",
            "verdict_reason": row.get("verdict_reason"),
            "stop": False,
        }
    return {"status": "unknown", "stop": False}


def _retry_research_prompt(base_prompt: str, attempt: int) -> str:
    return (
        f"{base_prompt}\n\n"
        f"Retry attempt {attempt}: the previous attempt ended without calling "
        "`save_tool_profile_tool`, `save_rejected_profile_tool`, or "
        "`report_no_new_tool`. You must call exactly one of those final result "
        "tools before ending this attempt."
    )


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
    from discovery_forge.agents.researcher_model import (
        DEFAULT_RESEARCHER_MAX_TURNS,
        ResearcherAgentModel,
        publish_researcher_model,
    )
    from discovery_forge.tools.feed import build_feed_output
    from discovery_forge.tools.prompts import (
        prompt_contents,
        prompt_hashes,
        prompt_refs,
        resolve_instruction_prompts,
    )
    from discovery_forge.tools.registry import ToolRegistry

    metadata_path = output_dir / "run_metadata.json"
    run_id = create_run_id(day)
    prompt_versions = resolve_instruction_prompts(
        max_tools=max_tools,
        publish_local=not dry_run,
    )
    prompt_hash_map = prompt_hashes(prompt_versions)
    prompt_ref_map = prompt_refs(prompt_versions)
    prompt_content_map = prompt_contents(prompt_versions)
    researcher_model = ResearcherAgentModel(
        search_backend=search_backend,
        recency=recency,
        max_turns=DEFAULT_RESEARCHER_MAX_TURNS,
        prompt_object_name=prompt_versions["researcher"].object_name,
        researcher_prompt_ref=prompt_ref_map["researcher"],
        researcher_prompt_hash=prompt_hash_map["researcher"],
    )
    model_ref_map = {
        "researcher": None if dry_run else publish_researcher_model(researcher_model),
    }
    ensure_run_metadata(
        metadata_path,
        day=day,
        run_id=run_id,
        prompt_hashes=prompt_hash_map,
        prompt_refs=prompt_ref_map,
        model_refs=model_ref_map,
        search_backend=search_backend,
    )

    budget = CostBudget(max_usd=max_cost_usd)
    prompt_tokens = 0
    completion_tokens = 0
    total_cost = 0.0
    profiled_count = 0
    accepted_count = 0
    rejected_count = 0
    no_new_count = 0
    attempted_count = 0

    registry_dir = output_dir.parent / "_registry"
    registry = ToolRegistry.load(registry_dir)
    print(f"[orchestrator] Registry loaded: {len(registry.get_all_entries())} known tools")
    researcher_model.bind_runtime(
        output_dir=output_dir,
        registry=registry,
        day=day,
        instructions_override=prompt_content_map["researcher"],
    )

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
            no_new_count=0,
            attempted_count=_DRY_RUN_TOOL_COUNT,
        )
        update_metadata_costs(metadata_path, 0.0, 0, 0)
        # Dry runs produce synthetic profiles, so they only write local files and
        # never publish to the shared Turso feed.
        build_feed_output(output_dir, registry=None, day=day)
        return

    try:
        for i in range(max_tools):
            budget.check()

            new_before = len(load_jsonl(output_dir / "_new_candidates.jsonl"))
            updated_before = len(load_jsonl(output_dir / "_updated_tools.jsonl"))
            rejected_before = len(load_jsonl(output_dir / "_rejected_profiles.jsonl"))
            no_new_before = len(load_jsonl(output_dir / "_no_new_tool.jsonl"))

            exclusion_block = build_exclusion_block(registry, output_dir)
            base_research_prompt = render_research_prompt(
                day=day,
                exclusion_block=exclusion_block,
                iteration=i + 1,
                recency=recency,
            )

            outcome: dict[str, Any] = {"status": "unknown", "stop": False}
            usage = (0, 0, 0.0)
            trace_id: str | None = None
            workflow_name = f"research_run_{i + 1}"
            for attempt in range(MAX_UNKNOWN_RETRIES + 1):
                budget.check()
                trace_id = gen_trace_id()
                workflow_name = (
                    f"research_run_{i + 1}"
                    if attempt == 0
                    else f"research_run_{i + 1}_retry_{attempt}"
                )
                research_prompt = (
                    base_research_prompt
                    if attempt == 0
                    else _retry_research_prompt(base_research_prompt, attempt)
                )

                with weave.attributes({
                    "day": day,
                    "run_id": run_id,
                    "stage": "research",
                    "iteration": i + 1,
                    "attempt": attempt + 1,
                    "researcher_prompt_hash": prompt_hash_map["researcher"],
                    "researcher_prompt_ref": prompt_ref_map["researcher"],
                    "researcher_model_ref": model_ref_map["researcher"],
                    "search_backend": search_backend,
                }):
                    await researcher_model.predict(
                        research_prompt=research_prompt,
                        day=day,
                        run_id=run_id,
                        workflow_name=workflow_name,
                        trace_id=trace_id,
                        stage="research",
                        metadata={
                            "iteration": i + 1,
                            "attempt": attempt + 1,
                            "workflow_name": workflow_name,
                            "researcher_prompt_hash": prompt_hash_map["researcher"],
                            "researcher_prompt_ref": prompt_ref_map["researcher"],
                            "researcher_model_ref": model_ref_map["researcher"],
                            "search_backend": search_backend,
                            "recency": recency,
                        },
                    )

                usage = researcher_model.last_usage
                prompt_tokens += usage[0]
                completion_tokens += usage[1]
                total_cost += usage[2]
                budget.add(usage[2])

                outcome = _iteration_outcome(
                    output_dir,
                    new_before=new_before,
                    updated_before=updated_before,
                    rejected_before=rejected_before,
                    no_new_before=no_new_before,
                )
                if outcome["status"] != "unknown":
                    break

                if attempt < MAX_UNKNOWN_RETRIES:
                    print(
                        f"[orchestrator] Retrying iteration {i + 1} after "
                        f"missing final result tool call ({attempt + 1}/{MAX_UNKNOWN_RETRIES})."
                    )
                else:
                    reason = (
                        "No final result tool call after "
                        f"{MAX_UNKNOWN_RETRIES + 1} attempts; marking this iteration as no_new."
                    )
                    append_no_new_tool(output_dir, reason)
                    outcome = _iteration_outcome(
                        output_dir,
                        new_before=new_before,
                        updated_before=updated_before,
                        rejected_before=rejected_before,
                        no_new_before=no_new_before,
                    )
            attempted_count += 1

            if outcome["status"] in ("accepted", "rejected", "no_new"):
                assert trace_id is not None
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
                    "verdict_reason": outcome.get("verdict_reason"),
                    "agent_trace_id": trace_id,
                    "workflow_name": workflow_name,
                    "weave_call_id": call_id,
                    "trace_url": trace_url,
                    "researcher_prompt_hash": prompt_hash_map["researcher"],
                    "researcher_prompt_ref": prompt_ref_map["researcher"],
                    "researcher_model_ref": model_ref_map["researcher"],
                    "search_backend": search_backend,
                    "prompt_tokens": usage[0],
                    "completion_tokens": usage[1],
                    "cost_usd": usage[2],
                })
                if outcome["status"] == "accepted":
                    profiled_count += 1
                    accepted_count += 1
                elif outcome["status"] == "rejected":
                    profiled_count += 1
                    rejected_count += 1
                else:
                    no_new_count += 1

            if outcome["stop"]:
                print(f"[orchestrator] Stopping after iteration {i + 1}: {outcome['status']}.")
                break

    except BudgetExceededError:
        # Partial outputs already on disk — do not clean up
        raise

    finally:
        update_metadata_counts(
            metadata_path,
            discovery_count=attempted_count,
            profiled_count=profiled_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            no_new_count=no_new_count,
            attempted_count=attempted_count,
        )
        if metadata_path.exists():
            update_metadata_costs(metadata_path, total_cost, prompt_tokens, completion_tokens)
        manifest = build_feed_output(output_dir, registry=registry, day=day)
        from discovery_forge.tools.turso_feed import write_feed_to_turso

        write_feed_to_turso(output_dir, manifest, day)


def _extract_usage(result) -> tuple[int, int, float]:
    """Extract (prompt_tokens, completion_tokens, cost_usd) from a Runner result."""
    if isinstance(result, dict):
        usage = result.get("usage")
        if isinstance(usage, dict):
            return (
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
                float(usage.get("cost_usd") or 0.0),
            )
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
            "verdict_reason": None,
            "agent_trace_id": None,
            "workflow_name": f"research_run_{i + 1}",
            "weave_call_id": None,
            "trace_url": None,
            "researcher_prompt_hash": researcher_prompt_hash,
            "search_backend": search_backend,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        })
