# Build Conventions for Claude Code (Ralph Loop)

This file is the **build guide** Claude Code reads on every iteration.
It is the guide for the *coder building the agents*, not the runtime guide for the research agent.

---

## Stack

- Python 3.11+
- Package manager: **`uv`** (do not use pip)
- Framework: `openai-agents` (OpenAI Agents SDK)
- **Observability: `weave` (W&B Weave) — auto-integrated via the OpenAI Agents SDK trace processor**
- Models: `gpt-5.4-mini` for all three agents (Discovery, Profiler, Writer)
- Search: Perplexity `sonar-pro` (replaces OpenAI WebSearchTool for Discovery + Profiler)
- Tests: `pytest`, `pytest-asyncio`
- Env loading: `python-dotenv` from `.env`
  - `OPENAI_API_KEY` (required)
  - `PERPLEXITY_API_KEY` (required for Discovery and Profiler search)
  - `WANDB_API_KEY` (required for Weave tracing)
  - `GITHUB_TOKEN` (optional, raises GitHub API rate limit)

---

## Directory Layout

```
src/autoresearch_researcher/
├── __init__.py
├── cli.py                  # entrypoint (Typer)
├── orchestrator.py         # flow control + cost budget + tracing
├── agents/
│   ├── __init__.py
│   ├── discovery.py
│   ├── profiler.py
│   └── writer.py
├── instructions/           # agent prompts (kept separate from code)
│   ├── discovery.md
│   ├── profiler.md
│   └── writer.md
├── tools/                  # function_tool definitions
│   ├── __init__.py
│   ├── persistence.py      # save_candidate_tool, save_tool_profile, save_draft, ...
│   ├── github.py           # fetch_github_metadata
│   ├── search.py           # perplexity_search
│   ├── citations.py        # SourceRegistry + verify_citations
│   ├── registry.py         # ToolRegistry (global accumulator)
│   └── diff.py             # draft vs final diff
└── schemas/                # pydantic models
    ├── __init__.py
    ├── candidate.py
    ├── tool_profile.py
    ├── sources.py
    └── registry.py

tests/
├── conftest.py
├── unit/
├── e2e/
└── fixtures/

weekly_runs/                # output (.gitignore)
├── _registry/              # global tool accumulator (persistent across weeks)
└── .gitkeep
```

---

## OpenAI Agents SDK core patterns

### Defining an Agent

```python
from agents import Agent, function_tool

def build_profiler_agent() -> Agent:
    return Agent(
        name="ProfilerAgent",
        instructions=load_instructions("profiler"),
        tools=[
            search_web,                # Perplexity-backed function_tool
            fetch_github_metadata,
            save_tool_profile,
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
    """Persist a tool profile as tools/{slug}.md with YAML front-matter."""
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
from agents import set_trace_processors
from weave.integrations.openai_agents.openai_agents import WeaveTracingProcessor

def init_observability(week_id: str):
    weave.init("wandb-smle/autoresearch-researcher")
    set_trace_processors([WeaveTracingProcessor()])

# Tag each weekly run via attributes (lets you filter by week)
import weave

async def run_briefing(week_id: str):
    with weave.attributes({"week": week_id, "stage": "discovery"}):
        await Runner.run(discovery_agent, ...)
    with weave.attributes({"week": week_id, "stage": "profiling"}):
        for candidate in candidates:
            await Runner.run(profiler_agent, ...)
    with weave.attributes({"week": week_id, "stage": "writing"}):
```

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

- DiscoveryAgent and ProfilerAgent both use the `search_web` function_tool, which wraps **Perplexity `sonar-pro`** (not the OpenAI built-in WebSearchTool)
- Why: Perplexity gives wider coverage of arXiv/GitHub for fresh tools and returns explicit citation URLs
- The OpenAI built-in `WebSearchTool` is **not** used anymore. If you need to add it back for any reason, remember it requires Responses-API models (gpt-4o family, gpt-5 family).

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
    result = await run_weekly_briefing(
        week="2026-W99-test",
        max_tools=3,
        max_cost_usd=2.0,
        output_dir=tmp_path,
    )
    assert (tmp_path / "draft.md").exists()
    assert (tmp_path / "comparison_table.md").exists()
    tools_dir = tmp_path / "tools"
    assert len(list(tools_dir.glob("*.md"))) >= 3
```

---

## Rules for writing agent instructions

Keep instructions in `src/autoresearch_researcher/instructions/{agent_name}.md`.

Why:
1. Tune prompts without touching code
2. v2 feedback loop only edits these files
3. Version history of how prompts evolved

`load_instructions("profiler")` reads the file and returns a string.

---

## Citation integrity (US6)

```python
# schemas/sources.py
class Source(BaseModel):
    id: int
    url: str
    title: str
    fetched_at: datetime
    used_in: list[str]  # tool slugs

# WriterAgent output verification
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
  → DiscoveryAgent must find them via search. Only category definitions go in instructions.
- ❌ **Do not use pip**. Always `uv add`, `uv run`, `uv sync`.
- ❌ Do not expose API keys in code, tests, comments, or git.
- ❌ Do not omit `--max-cost-usd` in E2E tests.
- ❌ Do not bypass ProfilerAgent's scope filter (deep-research tools quietly slipping in is the most common failure).
- ❌ Do not hardcode an Agent's instructions in code. Always load from `instructions/*.md`.
- ❌ Do not call the built-in `WebSearchTool` on a plain ChatCompletions model (Responses API only). We don't use it anymore — Perplexity replaces it.
- ❌ **Do not call `weave.init()` more than once per process** — exactly one call from the orchestrator entrypoint.
- ❌ **Use `set_trace_processors([WeaveTracingProcessor()])` to *replace*, not add** — never use `add_trace_processor`.
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
