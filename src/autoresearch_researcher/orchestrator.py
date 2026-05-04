"""Orchestrator: flow control, cost tracking, and Weave tracing setup."""

import json
import re
import shutil
from pathlib import Path

import weave
from agents import Runner, set_trace_processors
from weave.integrations.openai_agents.openai_agents import WeaveTracingProcessor


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


def init_observability(week_id: str):
    """Initialize W&B Weave tracing. Call exactly once per app lifecycle."""
    client = weave.init("wandb-smle/autoresearch-researcher")
    set_trace_processors([WeaveTracingProcessor()])
    return client


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


@weave.op
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
    from autoresearch_researcher.agents.profiler import build_profiler_agent
    from autoresearch_researcher.agents.writer import build_writer_agent, generate_highlights
    from autoresearch_researcher.tools.persistence import load_candidates
    from autoresearch_researcher.tools.registry import ToolRegistry

    budget = CostBudget(max_usd=max_cost_usd)
    prompt_tokens = 0
    completion_tokens = 0
    total_cost = 0.0

    candidates_file = output_dir / "_candidates.jsonl"
    registry_dir = output_dir.parent / "_registry"
    registry = ToolRegistry.load(registry_dir)
    print(f"[orchestrator] Registry loaded: {len(registry.get_all_entries())} known tools")

    if dry_run:
        # In dry-run mode, skip real LLM calls; create placeholder outputs
        _write_dry_run_outputs(output_dir, week)
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
            with weave.attributes({"week": week, "stage": "discovery"}):
                disc_result = await Runner.run(discovery_agent, input=discovery_prompt, max_turns=120)

            usage = _extract_usage(disc_result)
            prompt_tokens += usage[0]
            completion_tokens += usage[1]
            total_cost += usage[2]
            budget.add(usage[2])

        # ── Stage 2: Profiling (registry-aware) ───────────────────────────────
        candidates = load_candidates(candidates_file)
        # Filter out candidates that are already in the global registry
        candidates = [c for c in candidates if not registry.contains(c.url)]
        print(f"[orchestrator] Profiling {len(candidates)} new candidates (registry already has known ones)")

        profiler_agent = build_profiler_agent(
            output_dir=output_dir, registry=registry, week=week,
        )

        with weave.attributes({"week": week, "stage": "profiling"}):
            for candidate in candidates:
                budget.check()
                profile_prompt = (
                    f"Profile this tool candidate and determine if it is in scope:\n"
                    f"Name: {candidate.name}\nURL: {candidate.url}\nDescription: {candidate.description}"
                )
                prof_result = await Runner.run(profiler_agent, input=profile_prompt, max_turns=15)
                usage = _extract_usage(prof_result)
                prompt_tokens += usage[0]
                completion_tokens += usage[1]
                total_cost += usage[2]
                budget.add(usage[2])

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
        with weave.attributes({"week": week, "stage": "writing"}):
            write_result = await Runner.run(writer_agent, input=write_prompt, max_turns=20)

        usage = _extract_usage(write_result)
        prompt_tokens += usage[0]
        completion_tokens += usage[1]
        total_cost += usage[2]

    except BudgetExceededError:
        # Partial outputs already on disk — do not clean up
        raise

    finally:
        metadata_path = output_dir / "run_metadata.json"
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


def _write_dry_run_outputs(output_dir: Path, week: str) -> None:
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
