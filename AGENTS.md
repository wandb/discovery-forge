# Build Conventions for Claude Code (Ralph Loop)

This file is the **build guide** Claude Code reads on every iteration.
It is the guide for the *coder building the agents*, not the runtime guide for the research agent.

For feedback-driven work, also read `skills/autoresearch-feedback-improvement/SKILL.md`. It is the shared workflow for turning Weave annotations and local annotation seeds into prompt or code improvements.

---

## Primary References

- `AGENTS.md` — the canonical build guide and source of truth for coding agents.
- `README.md` — agent architecture diagram, daily accumulation model, CLI usage.
- `PRD.md` — User Stories with checkboxes, scope definition, and validation criteria.
- `skills/autoresearch-feedback-improvement/SKILL.md` — workflow for using Weave annotations and local feedback seeds to guide prompt or code improvements.

---

## Stack

- Python 3.11+
- Package manager: **`uv`** (do not use pip)
- Framework: `openai-agents` (OpenAI Agents SDK)
- **Observability: `weave` (W&B Weave) — auto-integrated via the OpenAI Agents SDK trace processor**
- Models: `gpt-5.4-mini` for the `ResearcherAgent` and the prompt-improvement proposer/applier
- Search: Serper by default; Perplexity `sonar-pro` via `--search-backend perplexity`; OpenAI hosted `WebSearchTool` via `--search-backend openai` (no extra search key)
- Tests: `pytest`, `pytest-asyncio`
- Env loading: `python-dotenv` from `.env`
  - `OPENAI_API_KEY` (required)
 - `SERPER_API_KEY` (required for the default Serper search; not needed with `--search-backend openai`)
 - `PERPLEXITY_API_KEY` (required only for `--search-backend perplexity`)
  - `WANDB_API_KEY` (required for Weave tracing)
  - `GITHUB_TOKEN` (optional, raises GitHub API rate limit)

---

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
uv run pytest tests/unit/test_researcher.py -v
uv run pytest tests/unit/test_researcher.py::test_scope_filter_deep_research_tool_is_rejected -v

# Add a new dependency
uv add <package>

# Run the CLI
uv run autoresearch-researcher run --day 2026-05-19 [--max-tools N --max-cost-usd N --dry-run --rerun --search-backend serper|perplexity|openai --since day|week|month|year|all]

# Ingest Weave annotations, then improve the prompt (prompt-only loop)
uv run autoresearch-researcher feedback ingest --day 2026-05-19
uv run autoresearch-researcher improve propose --day 2026-05-19
uv run autoresearch-researcher improve apply --day 2026-05-19
```

---

## Directory Layout

```
src/autoresearch_researcher/
├── __init__.py
├── cli.py                  # entrypoint (Typer)
├── orchestrator.py         # single-agent loop + cost budget + tracing
├── agents/
│   ├── __init__.py
│   ├── researcher.py       # the single discover+profile ResearcherAgent
│   └── improver.py         # prompt-improvement proposer + applier
├── instructions/           # agent prompts (kept separate from code)
│   ├── researcher.md
│   ├── prompt_proposer.md
│   └── prompt_applier.md
├── tools/                  # function_tool definitions + helpers
│   ├── __init__.py
│   ├── persistence.py      # save_tool_profile, save_source, load_sources
│   ├── profiles.py         # load_tool_profiles_from_dir (YAML front-matter)
│   ├── github.py           # fetch_github_metadata
│   ├── search.py           # serper / perplexity backends (openai uses WebSearchTool)
│   ├── citations.py        # SourceRegistry + verify_citations (retained, not yet wired in)
│   ├── registry.py         # ToolRegistry (global accumulator)
│   ├── feedback.py         # ingest Weave feedback by research call id
│   ├── improvement.py      # propose/apply prompt-improvement ops
│   ├── prompts.py          # Weave StringPrompt versioning for researcher.md
│   ├── evaluation.py       # Weave Evaluation for the researcher scope/profile decision
│   └── feed.py             # Agentforge manifest/items/raw export
└── schemas/                # pydantic models
    ├── __init__.py
    ├── tool_profile.py
    ├── sources.py
    └── registry.py

tests/
├── conftest.py
├── unit/
├── e2e/
└── fixtures/

daily_runs/                # output (.gitignore)
├── _registry/              # global tool accumulator (persistent across days)
└── .gitkeep
```

---

## OpenAI Agents SDK core patterns

### Defining an Agent

```python
from agents import Agent, WebSearchTool, function_tool

def build_researcher_agent(search_backend="serper") -> Agent:
    # search tool depends on the backend: WebSearchTool for "openai",
    # else a function_tool wrapping the serper/perplexity backend.
    search_tool = WebSearchTool() if search_backend == "openai" else search_web
    return Agent(
        name="ResearcherAgent",
        instructions=load_instructions("researcher"),
        tools=[
            search_tool,
            is_known_tool,
            fetch_github_metadata_tool,
            save_source_tool,
            save_tool_profile_tool,
            save_rejected_profile_tool,
            report_no_new_tool,
        ],
        model="gpt-5.4-mini",
    )
```

### Function tools

```python
from agents import function_tool
from pydantic import BaseModel

class ToolProfile(BaseModel):
    slug: str
    name: str
    license: str
    domains: list[str]
    autonomy_level: str
    interface: str
    resource_requirements: str
    last_commit: str | None
    stars: int | None
    pricing_note: str
    key_limitations: list[str]
    sources: list[int]  # source IDs

@function_tool
def save_tool_profile(profile: ToolProfile) -> str:
    """Persist a canonical tool profile as _registry/profiles/{slug}.md with YAML front-matter."""
    ...
```

### Runner

```python
from agents import Runner

result = await Runner.run(
    agent,
    input=prompt,
    max_turns=15,
)
```

### Tracing (W&B Weave)

Weave auto-captures every agent run, tool call, and model invocation through the OpenAI Agents SDK trace processor. Setup is one init + one processor registration per app lifecycle.

```python
# orchestrator.py — call once per app lifecycle
import weave
from agents import RunConfig, set_trace_processors

def init_observability(day_id: str):
    weave.init("wandb-smle/autoresearch-researcher")
    set_trace_processors([AutoresearchWeaveTracingProcessor()])

# Tag each per-tool research run via attributes
import weave

async def run_briefing(day_id: str):
    for i in range(max_tools):
        with weave.attributes({"day": day_id, "stage": "research", "iteration": i + 1}):
            await Runner.run(
                researcher_agent,
                ...,
                run_config=RunConfig(
                    workflow_name=f"stage_research_{i + 1}",
                    group_id=run_id,
                    trace_metadata={"day": day_id, "run_id": run_id, "stage": "research"},
                ),
            )
    # after the loop: build_feed_output(...) -> items/* + manifest.json
```

The displayed review unit is the named Agents SDK trace `stage_research_{i}` — one run per tool. Each is linked from `_profile_runs.jsonl` by `weave_call_id`, `agent_trace_id`, `workflow_name`, `run_id`, `slug`, `status`, and the researcher prompt hash. Do not add a separate `daily_run` trace unless it carries real diagnostic detail; the daily summary belongs in `run_metadata.json`.

Always pass a named `RunConfig` to `Runner.run()` so Weave shows `stage_research_{i}` instead of the SDK default `Agent workflow`. `init_observability()` uses `AutoresearchWeaveTracingProcessor`, which records the Weave call ID for each Agents trace and hides SDK task/turn spans while re-parenting their child tool calls to the nearest visible agent call. A run should read as `stage_research_{i} → ResearcherAgent → openai.responses.create/search_web/save_*`.

The ResearcherAgent's visible output is a reviewer-friendly profile review (accepted profile or rejection), built from `save_tool_profile_tool` / `save_rejected_profile_tool` calls.

Feedback-driven improvement is a two-stage AI loop and is **prompt-only**. Neither stage may modify Python code, schemas, registry, orchestrator, CLI, or deployment files.

- `improve propose` runs `PromptImprovementProposerAgent` (`instructions/prompt_proposer.md`). Inputs: every free-text human feedback event in `feedback_events.jsonl` plus the full current contents of `researcher.md`. Tool: `save_improvement_plan(content)`. Output: `prompt_improvement_plan.md` — a concrete plan with failure modes, exact proposed edits, and diff snippets. Items needing Python changes go under `## Out of scope (code change required)`.
- `improve apply` runs `PromptImprovementApplierAgent` (`instructions/prompt_applier.md`). Inputs: `prompt_improvement_plan.md` and the current `researcher.md`. Tool: `update_researcher_instructions`, which overwrites the instruction file with a full new Markdown body, and only if the plan proposes a change. A summary is written to `prompt_improvement_applied.md`. Whenever the applier actually changes the file, `improve apply` also calls `publish_instruction_prompts` so the new content becomes a Weave `StringPrompt` version in the same run; the resulting `prompt_refs` are returned in the trace output. This pipeline has no manual git-diff review step, so publishing is unconditional.

On every non-dry run, publish the `researcher.md` instruction file as a Weave `StringPrompt` object and construct the agent from the registered prompt content. Record prompt hashes and Weave prompt refs in `run_metadata.json` and trace metadata.

Trace both improvement steps. `improve propose` must call the `improve_propose` Weave op and return the plan Markdown in the call output. `improve apply` must call the `improve_apply` Weave op and return changed prompt file paths plus an `apply_markdown` summary in the call output.

Stage root outputs must be reviewer-friendly for Weave Annotation Queues. `stage_research_{i}` should expose `profile_review_markdown`, `verdict`, key metadata, source IDs, and prompt refs. Day-scoped annotations use the queue name `D{YYYYMMDD}_Research` and route to `researcher.md`.

**Tracing your own functions**: decorate plain functions with `@weave.op` to include them in traces.
```python
@weave.op
def verify_citations(report: str, sources: list[Source]) -> list[str]:
    ...
```

**Weave setup**:
- Run `wandb login` locally (or set `WANDB_API_KEY`)
- The first run prints a trace URL to the console — echo this in CLI output too

---

## Search backend constraints

- The ResearcherAgent's search tool is chosen by backend in `build_researcher_agent`.
- Default backend is **Serper** (`SERPER_API_KEY`), wrapped as the `search_web` function_tool. This intentionally exposes rawer search-result quality for the annotation/feedback demo.
- Perplexity `sonar-pro` remains available via `--search-backend perplexity` (`PERPLEXITY_API_KEY`) for A/B comparisons.
- `--search-backend openai` uses the OpenAI built-in **`WebSearchTool`** (hosted, server-side). It needs only `OPENAI_API_KEY` (no Serper/Perplexity key) and requires a Responses-API model (gpt-4o / gpt-5 family). Useful for a keys-minimal hands-on run, but results are more synthesized, so there is less rawness for reviewers to annotate.
- `--since {day|week|month|year|all}` (default `month`) sets a recency window via `search_web_query(..., recency=...)`: `serper` maps it to `tbs=qdr:<x>`, `perplexity` to `search_recency_filter`. The `openai` backend has no date filter, so recency only appears as a prompt hint. `all` disables the filter.
- Do not add automatic fallback between backends. If a selected backend is missing credentials or fails, return an explicit error string.

---

## Test cost control

### Unit tests (mocked LLM)

```python
from unittest.mock import AsyncMock, patch

async def test_profiler_filters_out_deep_research():
    with patch("agents.Runner.run") as mock_run:
        mock_run.return_value.final_output = ToolProfile(
            slug="some-deep-research-tool",
            autonomy_level="analyst",  # does not actually run experiments
            ...
        )
        result = await profile_candidate(candidate)
        assert result.is_rejected
        assert "deep research" in result.rejection_reason.lower()
```

### E2E tests

- One small category only (`--max-tools 3`)
- `@pytest.mark.expensive` marker
- Skipped in CI; run locally with `pytest -m expensive`
- Cost ceiling enforced (`--max-cost-usd 2`)

```python
@pytest.mark.expensive
async def test_e2e_smoke_run(tmp_path):
    await run_briefing(
        day="2026-05-29-test",
        max_tools=3,
        max_cost_usd=2.0,
        output_dir=tmp_path,
        dry_run=True,
    )
    assert (tmp_path / "manifest.json").exists()
    items_dir = tmp_path / "items"
    assert len(list(items_dir.glob("*.json"))) >= 3
```

---

## Rules for writing agent instructions

Keep instructions in `src/autoresearch_researcher/instructions/{agent_name}.md`.

Why:
1. Tune prompts without touching code
2. v2 feedback loop only edits these files
3. Version history of how prompts evolved

`load_instructions("researcher")` reads the file and returns a string.

---

## Citation integrity (US6 — retained, not yet wired in)

`tools/citations.py` (`SourceRegistry`, `verify_citations`) and `Source` are kept for
future use (e.g. attaching per-tool sources to feed items). The single-agent pipeline
no longer produces a draft to verify, and `save_source_tool` is currently a stub, so
nothing in the runtime path calls these yet. Do not delete without removing the matching
tests in `tests/unit/test_us6_citations.py`.

```python
# schemas/sources.py
class Source(BaseModel):
    id: int
    url: str
    title: str
    fetched_at: datetime
    used_in: list[str]  # tool slugs

# Citation verification helper (report vs known sources)
import re
def verify_citations(report: str, sources: list[Source]) -> list[str]:
    cited_ids = {int(m) for m in re.findall(r'\[\^(\d+)\]', report)}
    available_ids = {s.id for s in sources}

    errors = []
    if not cited_ids.issubset(available_ids):
        errors.append(f"Missing source IDs: {cited_ids - available_ids}")

    orphans = available_ids - cited_ids
    if orphans:
        errors.append(f"Orphan sources (in jsonl but never cited): {orphans}")

    return errors
```

---

## Sources of Truth (consult when in doubt)

- OpenAI Agents SDK docs: https://openai.github.io/openai-agents-python/
- WebSearchTool / FileSearchTool: docs/tools/ pages
- Official cookbook: https://cookbook.openai.com (Deep Research API and Agents SDK patterns)
- **W&B Weave + OpenAI Agents integration**: https://weave-docs.wandb.ai/guides/integrations/openai_agents/
- **Weave basics**: https://weave-docs.wandb.ai/ (`@weave.op`, `weave.attributes`, evaluations)

---

## Hard rules (the things Ralph keeps breaking)

- ❌ **Do not hardcode seed tool names** ("AI Scientist", "Agent Laboratory", etc.).
  → The ResearcherAgent must find them via search. Only category definitions go in instructions.
- ❌ **Do not use pip**. Always `uv add`, `uv run`, `uv sync`.
- ❌ Do not expose API keys in code, tests, comments, or git.
- ❌ Do not omit `--max-cost-usd` in E2E tests.
- ❌ Do not bypass the ResearcherAgent's scope filter (deep-research / curated-list tools quietly slipping in is the most common failure).
- ❌ Do not hardcode an Agent's instructions in code. Always load from `instructions/*.md`.
- ❌ Do not call the built-in `WebSearchTool` on a plain ChatCompletions model (Responses API only). It is only wired in for `--search-backend openai`, which assumes a Responses-API model (gpt-4o / gpt-5 family).
- ❌ **Do not call `weave.init()` more than once per process** — exactly one call from the orchestrator entrypoint.
- ❌ **Use `set_trace_processors([AutoresearchWeaveTracingProcessor()])` to *replace*, not add** — never use `add_trace_processor`.
- ❌ Do not call real `weave.init` from unit tests — mock it via the fixture for token savings and isolation.

---

## TDD rules

For every User Story:

1. **Red**: write a failing test first. One unit test plus one e2e test if relevant.
2. **Green**: minimal implementation that makes it pass.
3. **Refactor**: tidy up while keeping it green.
4. **Commit**: only after `uv run pytest tests/` passes. Commit message format: `US{N}: {short description}`.

---

## Logged learnings

(Ralph appends one line per iteration)

<!-- Ralph fills in below this line. -->
- US1: After `uv sync`, a stale `VIRTUAL_ENV` env pointing to a different venv triggers a warning — `uv run` still works, but the warning shows up whenever a different venv was already active. Safe to ignore.
- US2: When a Typer CLI calls an async orchestrator via `asyncio.run()`, tests must `AsyncMock` patch at `autoresearch_researcher.cli.run_briefing` — the wrong module path silently no-ops the mock.
- US3: `@function_tool` definitions need to capture `output_dir` via a closure inside the agent factory. Passing the path as a tool arg means the model has to know it; the `build_*_agent(output_dir)` pattern with closure binding is the right shape.
- US4: Splitting a pure helper like `is_experiment_automation()` out of the agent module lets you unit-test the scope filter without LLM mocking. Layering rule-based filters under LLM judgement is the key to test-ability.
- US5: WriterAgent's `read_tool_profiles_tool` should strip the `_body` field and return JSON to keep the context window small. Fetch the full body via `get_tool_body_tool(slug)` only when needed — much more token-efficient.
- US6: `SourceRegistry` must rewrite the file when re-registering an existing URL (to refresh `used_in`). Append-only JSONL risks duplicate IDs, so dedup needs an in-memory dict + full rewrite.
- US7: `CostBudget.add()` calls `check()` internally and raises immediately. To set up an "already over budget" state in tests, set `budget._total` directly and then call `check()` separately — calling `add()` will raise during setup.
- US8: `difflib.unified_diff` lines end with `\n`, so classify regexes need `line.rstrip()` first — otherwise the `^` anchor collides with trailing whitespace and produces false positives.
- US9: `shutil.move(str(src), str(dst))` should pass strings — Python ≤3.11 can fail with `Path` objects directly. Wrapping with `str()` is the safe form.
- Smoke e2e: in dry-run mode, `sources.jsonl` must align 1:1 with `[^N]` footnotes in `draft.md` for `verify_citations` to pass — generate source_ids and footnote numbers in lockstep so there are no orphan citations.
- Trace redesign: keep `run_briefing()` as the plain orchestrator and use named Agents SDK traces for visible stages. Stage 2 should display as `stage2_profile_{slug} → ProfilerAgent`; daily rollups stay in `run_metadata.json` unless they need real trace detail.
- US11/US12 rewrite: rule-based classification of feedback by a `prompt_issue_type` field does not survive free-text human annotations. `improve propose` and `improve apply` are now real LLM agents (`PromptImprovementProposerAgent`, `PromptImprovementApplierAgent`) — propose synthesizes the plan, apply rewrites instruction files. Tests mock `_run_proposer_agent` / `_run_applier_agent` rather than the rule-based classifier.
