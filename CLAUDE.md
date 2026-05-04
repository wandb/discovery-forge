# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Primary references

- **`AGENTS.md`** — the canonical build guide. It contains the Stack, the OpenAI Agents SDK patterns, the **hard rules** (e.g. no hardcoded seed tool names, no pip, no second `weave.init` call), and the running list of "Logged learnings" from each iteration. Read this before making non-trivial changes.
- **`README.md`** — agent architecture diagram, weekly accumulation model, CLI usage.
- **`PRD.md`** — User Stories with checkboxes, scope definition (IN/OUT), and the validation criteria.

When AGENTS.md and CLAUDE.md disagree, AGENTS.md wins.

## Commands

Always use `uv` — `pip` is forbidden.

```bash
# Install / sync dependencies
uv sync

# Run the full unit test suite (LLM mocked, free)
uv run pytest tests/ --ignore=tests/e2e

# Run only the e2e smoke test (dry-run, no real LLM calls)
uv run pytest -m expensive tests/e2e/

# Run a single test file or test
uv run pytest tests/unit/test_us4_profiler.py -v
uv run pytest tests/unit/test_us4_profiler.py::test_profiler_scope_filter_deep_research_tool_is_rejected -v

# Add a new dependency
uv add <package>

# Run the CLI
uv run autoresearch-researcher run --week 2026-W19 [--max-tools N --max-cost-usd N --dry-run --rerun]
uv run autoresearch-researcher diff --week 2026-W19

# One-time migration: import existing per-week tool profiles into the global registry
uv run python scripts/migrate_to_registry.py weekly_runs/<week_dir> <week_id>
```

## Architecture (the parts that span multiple files)

### Three-agent pipeline orchestrated explicitly (no SDK handoffs)

`orchestrator.run_briefing()` is the single entry point. It runs Discovery → Profiling (per candidate) → Writing sequentially with explicit `Runner.run()` calls per stage, never agent-to-agent handoffs. This is intentional: it keeps cost tracking, retry logic, and Weave attribute tagging in one place.

The orchestrator is decorated with `@weave.op` so that every stage (and every per-candidate ProfilerAgent call) becomes a child trace under one root. Without that decorator the traces show up as siblings in the Weave UI.

### Closure binding for function tools

Every `build_*_agent(output_dir, registry, week, ...)` factory captures paths and the registry **in a closure** before declaring `@function_tool` callables. The agent never receives `output_dir` as a tool argument — the model would have to guess it. Always extend agents by adding a new `@function_tool` inside the existing factory body, not by passing more state through arguments.

### Global registry + per-week change log

`weekly_runs/_registry/` is the persistent source of truth. `tools.jsonl` indexes every tool ever profiled (URL-normalized for dedup); `profiles/{slug}.md` stores the canonical `ToolProfile` YAML+body. Each `weekly_runs/{week}/` folder records only the deltas: `_new_candidates.jsonl` (first profiled this week), `_updated_tools.jsonl` (metadata changed), and `highlights.md` (auto-derived from those two).

`ToolRegistry.add(profile, week)` returns `True` for "new" and `False` for "already known, updated metadata". The orchestrator passes that boolean through to decide which jsonl to write to.

DiscoveryAgent uses the registry via the `is_known_tool(url)` function tool to skip re-discovery; ProfilerAgent's `save_tool_profile_tool` routes the canonical profile into the registry; WriterAgent reads profiles from `registry.profiles_dir` instead of `output_dir/tools/`.

### Search backend: Perplexity, not OpenAI WebSearchTool

Both DiscoveryAgent and ProfilerAgent expose a `search_web` function_tool that wraps `tools/search.py:perplexity_search` (sonar-pro). The OpenAI built-in `WebSearchTool` is **not** used — Perplexity gives broader arXiv/GitHub coverage and explicit citation URLs. Setting a different search backend means editing both agent factories and `tools/search.py`.

### The mandatory ProfilerAgent scope filter

The most-tested invariant: ProfilerAgent must reject deep-research / web-summarization tools even if Discovery accidentally seeds them. The pure-Python `is_experiment_automation()` helper in `agents/profiler.py` is the rule-based layer underneath the LLM judgement, and the four `test_profiler_scope_filter_*` tests in `tests/unit/test_us4_profiler.py` are required to pass.

### Cost guardrails preserve partial outputs

`CostBudget.add()` calls `check()` internally and raises `BudgetExceededError` immediately when over. The orchestrator catches this in a `try/finally` so files written before the budget hit (candidates, partial profiles) stay on disk for the next `--rerun` to resume from.

### Resume logic via `_candidates.jsonl`

`should_skip_discovery(output_dir)` checks for a non-empty candidates file. The orchestrator filters candidates against `registry.contains(url)` so already-profiled tools are silently skipped on re-run. There is no separate "resume" flag — just delete `_candidates.jsonl` to force re-discovery.

### Instructions live in markdown files, not code

Every agent loads its prompt from `instructions/{agent_name}.md` via `load_instructions()`. **Never inline an agent prompt in Python code.** This separation lets you A/B test prompts via git history and is the v2 surface for feedback-driven prompt updates.

## TDD expectation

Per AGENTS.md: write a failing test (Red), minimal implementation (Green), refactor, commit only after `uv run pytest tests/` passes. Commit message format: `US{N}: {short description}`. Iteration learnings get appended to AGENTS.md "Logged learnings".
