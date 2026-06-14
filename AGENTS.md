# Build Conventions for Claude Code (Ralph Loop)

This file is the **build guide** Claude Code reads on every iteration.
It is the guide for the *coder building the agents*, not the runtime guide for the research agent.

For annotation-driven work, use `skills/annotation-improvement/SKILL.md`. For offline evaluation failure analysis, use `skills/offline-eval-improvement/SKILL.md`. Both are coding-agent workflows for using W&B Weave evidence through W&B Skills to plan, apply, publish, and validate prompt improvements.

---

## W&B Skills Setup

Before any coding-agent workflow that touches W&B or Weave traces, feedback, annotations, prompts, datasets, evaluations, or reports, ensure the official W&B Skills are available.

- Install if needed: `npx skills add wandb/skills`
- Read and use the W&B Skills as the source of truth for Weave data access, feedback, datasets, prompts, and evaluations.

---

## Primary References

- `AGENTS.md` — the canonical build guide and source of truth for coding agents.
- `README.md` — agent architecture diagram, daily accumulation model, CLI usage.
- `PRD.md` — User Stories with checkboxes, scope definition, and validation criteria.
- `skills/annotation-improvement/SKILL.md` — workflow for using Weave trace and annotation evidence through W&B Skills to plan, apply, validate, and publish prompt improvements.
- `skills/offline-eval-improvement/SKILL.md` — workflow for using Weave Evaluation failed rows and `verdict_quality_scorer` evidence to improve and compare prompt versions.
- `skills/build-verdict-dataset/SKILL.md` — workflow for building `verdict_quality_dataset` from `research_annotation` evidence, refining rows against the rubric, and publishing a new versioned Weave Dataset.

---

## Stack

- Python 3.11+
- Package manager: **`uv`** (do not use pip)
- Framework: `openai-agents` (OpenAI Agents SDK)
- **Observability: `weave` (W&B Weave) — auto-integrated via the OpenAI Agents SDK trace processor**
- Models: `gpt-5.4-mini` for the `ResearcherAgent`
- Search: Serper by default; Perplexity `sonar-pro` via `--search-backend perplexity`; OpenAI hosted `WebSearchTool` via `--search-backend openai` (no extra search key)
- Tests: `pytest`, `pytest-asyncio`
- Env loading: `python-dotenv` from `.env`
  - `OPENAI_API_KEY` (required)
 - `SERPER_API_KEY` (required for the default Serper search; not needed with `--search-backend openai`)
 - `PERPLEXITY_API_KEY` (required only for `--search-backend perplexity`)
  - `WANDB_API_KEY` (required for Weave tracing)
  - `WANDB_ENTITY` (required for Weave tracing)
  - `WANDB_PROJECT` (required for Weave tracing; `.env.example` uses `discovery-forge`)
  - `GITHUB_TOKEN` (optional, raises GitHub API rate limit)
  - `DB_DISCOVERY_FORGE_URL` / `DB_DISCOVERY_FORGE_AUTH_TOKEN` (optional, publish feed to Agentforge Turso; skip when unset)

---

## Commands

Always use `uv` — `pip` is forbidden.

```bash
# Install / sync dependencies
uv sync

# Lint (default E/F rules; fix code, do not loosen config)
uv run ruff check .

# Run the full unit test suite (LLM mocked, free)
uv run pytest tests/ --ignore=tests/e2e

# Run only the e2e smoke test (dry-run, no real LLM calls)
uv run pytest -m expensive tests/e2e/

# Run a single test file or test
uv run pytest tests/unit/test_researcher.py -v
uv run pytest tests/unit/test_researcher.py::test_scope_filter_deep_research_tool_is_rejected -v

# Add a new dependency
uv add <package>

# Run the daily ResearcherAgent loop
uv run python main.py --day 2026-05-19 [--max-tools N --max-cost-usd N --dry-run --rerun --search-backend serper|perplexity|openai --since day|week|month|year|all]

# Preferred feedback-driven improvement path:
# read and follow skills/annotation-improvement/SKILL.md

# Preferred offline-eval improvement path:
# read and follow skills/offline-eval-improvement/SKILL.md

# Run offline evaluation against the published Weave dataset
uv run python evaluate.py --verdict-dataset-key verdict_quality
# or override with: uv run python evaluate.py --verdict-dataset-ref '<verdict-dataset-ref>'
```

---

## Directory Layout

```
main.py                      # daily ResearcherAgent entrypoint
evaluate.py                 # offline eval entrypoint (loads pinned published Weave dataset refs)

src/discovery_forge/
├── __init__.py
├── orchestrator.py         # single-agent loop + cost budget + tracing
├── agents/
│   ├── __init__.py
│   ├── researcher.py       # the single discover+profile ResearcherAgent
│   ├── researcher_tools.py
│   ├── researcher.md       # ResearcherAgent prompt
│   └── researcher_base.md  # baseline prompt used for comparison/reset
├── evaluation/             # offline evaluation runners, scorers, dataset helpers + docs
│   ├── __init__.py
│   ├── verdict.py          # verdict quality eval (run_researcher_evaluation, scorers)
│   ├── datasets.py         # load/publish helpers + YAML evaluation config loader
│   ├── evaluation_config.yaml  # dataset refs + offline-eval improvement defaults
│   └── OFFLINE_EVALUATION.{ko,ja,en}.md  # eval workflow docs (datasets live in Weave)
├── tools/                  # function_tool definitions + helpers
│   ├── __init__.py
│   ├── persistence.py      # save_tool_profile, save_source, load_sources
│   ├── profiles.py         # load_tool_profiles_from_dir (YAML front-matter)
│   ├── github.py           # fetch_github_metadata
│   ├── search.py           # serper / perplexity backends (openai uses WebSearchTool)
│   ├── registry.py         # ToolRegistry (global accumulator)
│   ├── prompts.py          # Weave StringPrompt versioning for researcher.md
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
    weave.init(weave_project_path())  # requires WANDB_ENTITY and WANDB_PROJECT from .env
    set_trace_processors([DiscoveryForgeWeaveTracingProcessor()])

# Tag each per-tool research run via attributes
import weave

async def run_briefing(day_id: str):
    for i in range(max_tools):
        with weave.attributes({
            "day": day_id,
            "stage": "research",
            "iteration": i + 1,
        }):
            await Runner.run(
                researcher_agent,
                ...,
                run_config=RunConfig(
                    workflow_name=f"research_run_{i + 1}",
                    group_id=run_id,
                    trace_metadata={
                        "day": day_id,
                        "run_id": run_id,
                        "stage": "research",
                        "iteration": i + 1,
                    },
                ),
            )
    # after the loop: build_feed_output(...) -> items/* + manifest.json
```

The displayed review unit is the named Agents SDK trace `research_run_{i}` — one run per tool. The orchestrator no longer assigns a search lane; it passes the iteration, exclusion list, and recency hint, while the ResearcherAgent uses the Query Example Pool in `researcher.md` to write its own search queries. Each trace is linked from `_profile_runs.jsonl` by `weave_call_id`, `agent_trace_id`, `workflow_name`, `run_id`, `slug`, `status`, and the researcher prompt hash. Do not add a separate `daily_run` trace unless it carries real diagnostic detail; the daily summary belongs in `run_metadata.json`.

Always pass a named `RunConfig` to `Runner.run()` so Weave shows `research_run_{i}` instead of the SDK default `Agent workflow`. `init_observability()` uses `DiscoveryForgeWeaveTracingProcessor`, which records the Weave call ID for each Agents trace and hides SDK task/turn spans while re-parenting their child tool calls to the nearest visible agent call. A run should read as `research_run_{i} → ResearcherAgent → openai.responses.create/search_web/save_*`.

The ResearcherAgent's visible output is a reviewer-friendly profile review (accepted profile or rejection), built from `save_tool_profile_tool` / `save_rejected_profile_tool` calls.

Feedback-driven improvement is **prompt-only** by default. The skill-guided workflow may edit `src/discovery_forge/agents/researcher.md`; it must not modify Python code, schemas, registry, orchestrator, CLI, or deployment files as part of applying feedback.

The workflow is skill-guided:

- Read and follow `skills/annotation-improvement/SKILL.md`.
- Use live Weave evidence through W&B Skills, plus human annotations, runnable scorer feedback, and the current `researcher.md`.
- Write `src/discovery_forge/agents/improve_history/<day>/plan.md`, edit only `src/discovery_forge/agents/researcher.md`, publish the updated Weave `StringPrompt`, write `src/discovery_forge/agents/improve_history/<day>/applied.md`, and run focused validation.
- For offline evaluation failures, follow `skills/offline-eval-improvement/SKILL.md`; inspect the evaluation parent/child calls, keep datasets and scorers read-only, then rerun the same pinned dataset for comparison.

On every non-dry run, publish the `researcher.md` instruction file as a Weave `StringPrompt` object and construct the agent from the registered prompt content. Record prompt hashes and Weave prompt refs in `run_metadata.json` and trace metadata.

Stage root outputs must be reviewer-friendly for Weave Annotation Queues. `research_run_{i}` should expose `profile_review_markdown`, `verdict`, key metadata, source IDs, and prompt refs. Day-scoped annotations use the queue name `D{YYYYMMDD}_Research` and route to `researcher.md`.

**Tracing your own functions**: decorate plain functions with `@weave.op` to include them in traces.
```python
@weave.op
def score_profile(profile: dict) -> dict:
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

async def test_researcher_filters_out_deep_research():
    with patch("agents.Runner.run") as mock_run:
        mock_run.return_value.final_output = ToolProfile(
            slug="some-deep-research-tool",
            autonomy_level="analyst",  # does not actually run experiments
            ...
        )
        result = await research_candidate(candidate)
        assert result.is_rejected
 assert "deep research" in result.verdict_reason.lower()
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

Keep instructions in `src/discovery_forge/agents/{agent_name}.md`.

Why:
1. Tune prompts without touching code
2. v2 feedback loop only edits these files
3. Version history of how prompts evolved

`load_instructions("researcher")` reads the file and returns a string.

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
- ❌ Do not hardcode an Agent's instructions in code. Always load from `agents/*.md`.
- ❌ Do not call the built-in `WebSearchTool` on a plain ChatCompletions model (Responses API only). It is only wired in for `--search-backend openai`, which assumes a Responses-API model (gpt-4o / gpt-5 family).
- ❌ **Do not call `weave.init()` more than once per process** — exactly one call from the orchestrator entrypoint.
- ❌ **Use `set_trace_processors([DiscoveryForgeWeaveTracingProcessor()])` to *replace*, not add** — never use `add_trace_processor`.
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
- US2: Entry point tests patch `discovery_forge.orchestrator.run_briefing` through `run_research()` and load root scripts such as `main.py`; patching stale CLI module paths silently no-ops the mock.
- US3: `@function_tool` definitions need to capture `output_dir` via a closure inside the agent factory. Passing the path as a tool arg means the model has to know it; the `build_*_agent(output_dir)` pattern with closure binding is the right shape.
- US4: Splitting a pure helper like `is_experiment_automation()` out of the agent module lets you unit-test the scope filter without LLM mocking. Layering rule-based filters under LLM judgement is the key to test-ability.
- US5: WriterAgent's `read_tool_profiles_tool` should strip the `_body` field and return JSON to keep the context window small. Fetch the full body via `get_tool_body_tool(slug)` only when needed — much more token-efficient.
- US7: `CostBudget.add()` calls `check()` internally and raises immediately. To set up an "already over budget" state in tests, set `budget._total` directly and then call `check()` separately — calling `add()` will raise during setup.
- US8: `difflib.unified_diff` lines end with `\n`, so classify regexes need `line.rstrip()` first — otherwise the `^` anchor collides with trailing whitespace and produces false positives.
- US9: `shutil.move(str(src), str(dst))` should pass strings — Python ≤3.11 can fail with `Path` objects directly. Wrapping with `str()` is the safe form.
- Trace redesign: keep `run_briefing()` as the plain orchestrator and use named Agents SDK traces for visible stages. Each tool review should display as `research_run_{i} → ResearcherAgent`; daily rollups stay in `run_metadata.json` unless they need real trace detail.
