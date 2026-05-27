# PRD: autoresearch-researcher Tool Briefing Agent (v1)

## Overview

A multi-agent system that runs once a day to survey **autonomous research tools in the experiment-automation space** and produce a publishable comparison guide (Markdown).

## v1 Goals

- Auto-publish a tool inventory + comparison guide once a day
- A human (the maintainer) reviews each issue and writes a `final.md` + `feedback.md`
- v2 will use that feedback to improve system prompts (out of scope here)

## Scope (the most important part of this project)

### IN: Experiment automation

Systems that automate code-writing, experiment execution, and paper/report generation. They run all or part of the hypothesis → experiment → result → write cycle.

Categories (the agent must discover specific tools — this PRD intentionally avoids seeding tool names):

- End-to-end automated paper generation systems
- ML experiment loop automation tools
- Chemistry / biology lab experiment automation
- Hypothesis generation / exploration agents

### OUT: Explicitly excluded

- Deep-research tools — systems that synthesize web literature without running experiments
- General LLM-based RAG / search assistants
- General coding assistants (Cursor, Copilot, etc.)
- General AI agent frameworks (autoGPT-style)

**Filter rule** (applied by ProfilerAgent itself):
> Does this tool *execute experiments* or *autonomously generate code/papers*? If it only searches, summarizes, or reviews → OUT.

## Input

Day identifier (e.g. `2026-05-28`). Passed via CLI; cron-friendly.

## Output structure

```
daily_runs/
├── _registry/
│   ├── tools.jsonl                  # global tool index
│   ├── profiles/{tool_slug}.md      # canonical per-tool detail cards
│   └── sources.jsonl                # cumulative citation sources
└── 2026-05-19/
    ├── manifest.json                # Agentforge feed manifest
    ├── report.md                    # feed report body (copy of draft.md)
    ├── items/{tool_slug}.json       # structured feed item payloads
    ├── raw/                         # source artifacts copied for debugging/fallback sync
    ├── run_metadata.json            # run_id, prompt hashes, timestamps, tokens, cost, counts
    ├── _candidates.jsonl            # Discovery output
    ├── _profile_runs.jsonl          # per-tool Weave trace links
    ├── _new_candidates.jsonl        # tools first profiled today
    ├── _updated_tools.jsonl         # known tools whose metadata changed
    ├── highlights.md                # daily delta summary
    ├── draft.md                     # main publishable draft
    ├── comparison_table.md          # standalone comparison table
    ├── feedback_events.jsonl        # optional, after Weave feedback ingest
    ├── prompt_improvement_notes.md  # optional, after Weave feedback ingest
    └── (filled in by human)
        ├── final.md                 # human-edited publish version
        ├── feedback.md              # structured feedback
        └── diff.md                  # auto draft vs final diff
```

## Publish format (draft.md)

### Required sections
1. **Header**: day, publish date, # tools covered, # sources
2. **Today's Highlights**: 3–5 new releases or major updates (or "no major updates today")
3. **Use-Case Recommendation Matrix**: "your situation → recommended tool" table
4. **Full Comparison Table**: tool × attribute matrix
5. **Tool Cards**: one paragraph + links per tool
6. **Known Limitations / Reliability Issues**: cross-cutting warnings about the category
7. **References**

### Comparison table columns (minimum)

| Column | Example |
|--------|---------|
| Tool name | (tool name) |
| License | Apache 2.0 / MIT / Commercial / Custom |
| Domain | ML / Chemistry / Biology / General |
| Autonomy level | Tool / Analyst / Scientist (or your own definition + rationale) |
| Interface | CLI / Python lib / Web / API |
| Resource requirements | Single GPU / Multi GPU / Lab equipment / Cloud only |
| GitHub activity | last commit, stars |
| Pricing / TCO note | Free / $X/mo / TCO note |
| Key limitation | one line |

## Architecture: 3 agents

```
Orchestrator (CLI entrypoint)
  │
  ├─→ DiscoveryAgent
  │     input: PRD's IN/OUT scope definition
  │     tools: search_web (SerpAPI default, Perplexity optional), is_known_tool, save_candidate_tool
  │     trace: stage1_discovery
  │     trace output: Markdown table of discovered/rejected candidates
  │     output: _candidates.jsonl
  │
  ├─→ ProfilerAgent (one call per tool)
  │     input: one candidate tool
  │     tools: search_web (SerpAPI default, Perplexity optional), fetch_github_metadata, save_tool_profile
  │     trace: stage2_profile_{slug} → ProfilerAgent
  │     scope filter: self-checks "is this really experiment automation?"
  │     output: _registry/profiles/{slug}.md + _profile_runs.jsonl
  │
  └─→ WriterAgent
        input: all _registry/profiles/{slug}.md + daily delta files
        tools: read_tool_profiles, get_tool_body, read_highlights, save_draft, save_comparison_table
        trace: stage3_writer
        output: draft.md, comparison_table.md
```

No agent-to-agent handoffs — the orchestrator owns flow control. Simpler debugging, single place for cost tracking.

## User Stories

### US1: Project bootstrap
- [x] `uv` + `pyproject.toml`
- [x] Dependencies: `openai-agents`, `weave`, `pytest`, `pytest-asyncio`, `python-dotenv`
- [x] `.env.example` template (`OPENAI_API_KEY`, `WANDB_API_KEY`, `GITHUB_TOKEN` optional)
- [x] `.gitignore` (`.env`, `daily_runs/`, `__pycache__/`, `.venv/`, `wandb/`)
- [x] `tests/` folder with `conftest.py`

### US2: CLI entrypoint
- [x] `autoresearch-researcher run --day 2026-05-19 [--max-tools 12] [--max-cost-usd 20] [--dry-run]`
- [x] Auto-create `daily_runs/{day}/` (abort if it exists without `--rerun`)
- [x] Record start timestamp in `run_metadata.json`
- [x] Record cumulative token / cost / elapsed time on exit

### US3: DiscoveryAgent
- [x] Scope definition lives in `instructions/discovery.md`
- [x] Web searches per category via configurable `search_web` (SerpAPI default, Perplexity optional)
- [x] **Search queries use category / general terms only**, no specific tool-name seeds
- [x] N candidates saved to `_candidates.jsonl` (name, URL, one-line description, discovery category)
- [x] Obvious OUT categories (e.g., deep-research products) excluded on discovery with reason recorded

### US4: ProfilerAgent
- [x] For each candidate, collect:
  - Official page / paper / GitHub URL
  - License (extract from LICENSE file or page)
  - GitHub activity (last commit, stars, open issues) via `fetch_github_metadata`
  - Domain classification (multi-label allowed)
  - Autonomy level (own definition + rationale)
  - Interface / resource requirements
  - Known limitations (prefer primary sources)
- [x] **Self scope filter**: post-collection, verify "does this match the experiment-automation definition?", reject on mismatch
- [x] Output as `_registry/profiles/{slug}.md` (YAML front-matter + body)
- [x] Every factual claim has a registered source (sources.jsonl)

### US5: WriterAgent
- [x] Read all `_registry/profiles/*.md` and synthesize
- [x] Auto-generate the comparison table (every column filled, blanks shown as "unknown")
- [x] Use-case matrix (single GPU / multi-GPU / enterprise / data-private, etc.)
- [x] Identify "today's highlights" (compare with prior run if folder exists, else "first issue")
- [x] Every factual claim cites (`[^N]` + sources.jsonl mapping)
- [x] Tone: informational only, no marketing language

### US6: Citation integrity
- [x] Every citation must use a URL registered in sources.jsonl
- [x] sources.jsonl entry fields: `id, url, title, fetched_at, used_in (list of tool slugs)`
- [x] Auto-check: every `[^N]` reference exists in sources.jsonl
- [x] Auto-check: every URL in sources.jsonl is cited somewhere in the body (orphan-source warning)

### US7: Cost / runtime guardrails + tracing
- [x] `--max-cost-usd 20` (default) triggers a graceful shutdown
  - Outputs from completed stages are preserved
- [x] **W&B Weave tracing** enabled
  - One call to `weave.init(project="autoresearch-researcher")`
  - `set_trace_processors([AutoresearchWeaveTracingProcessor()])` to auto-capture and cleanly parent OpenAI Agents traces
  - Tag each daily run and tool profile call with `day` and `run_id`
  - Each candidate profiling run is an independent `stage2_profile_{slug}` root call for human review
  - Stage 2 trace tree should read as `stage2_profile_{slug} → ProfilerAgent → LLM/tool calls`
  - `_profile_runs.jsonl` links `slug`, `status`, `workflow_name`, `agent_trace_id`, `weave_call_id`, `trace_url`, and prompt hash
- [x] Cumulative token / cost recorded in `run_metadata.json` (Weave dashboard separately, local copy here)
- [x] CLI prints the Weave trace URL (clickable for post-run review)

### US8: Diff infrastructure (feedback loop seed)
- [x] CLI subcommand: `autoresearch-researcher diff --day 2026-05-19`
  - Run after the maintainer writes `final.md`
  - Generates `diff.md` with line-level + semantic diff between `draft.md` and `final.md`
  - Categories: ADD (tool added), FIX (factual edit), REMOVE, REWORD, BALANCE
- [x] Auto-generate `feedback.md` template (form for the human; see below)

### US9: Re-run safety
- [x] `--rerun` allows re-running the same day (previous folder backed up)
- [x] On partial failure, resume from `_candidates.jsonl` starting at ProfilerAgent

### US10: Per-tool feedback ingestion
- [x] CLI subcommand: `autoresearch-researcher feedback ingest --day 2026-05-19`
  - Reads `_profile_runs.jsonl`
  - Fetches Weave feedback for each `weave_call_id`
  - Writes `feedback_events.jsonl`
  - Writes `prompt_improvement_notes.md`
- [x] Prompt versions are tracked via instruction-file hashes in `run_metadata.json` and per-tool profile run rows
- [x] Prompt edits are not applied automatically; the maintainer reviews notes before changing `instructions/*.md`

### US11: Feedback-driven prompt improvement proposal
- [x] CLI subcommand: `autoresearch-researcher improve propose --day 2026-05-19`
  - Runs `PromptImprovementProposerAgent` (gpt-5.4-mini)
  - Reads every free-text event in `feedback_events.jsonl`
  - Reads current contents of `discovery.md`, `profiler.md`, `writer.md`
  - Produces a concrete plan with per-agent failure modes and proposed prompt edits (including diff snippets)
  - Saves the plan to `prompt_improvement_plan.md`
  - Records a Weave `improve_propose` trace with the plan Markdown in the call output
- [x] Proposal scope is prompt-only:
  - `instructions/discovery.md`
  - `instructions/profiler.md`
  - `instructions/writer.md`
- [x] Python code changes, schema changes, deployment changes, and automatic prompt edits are out of scope

### US12: Versioned prompt improvement loop
- [x] CLI subcommand: `autoresearch-researcher improve apply --day 2026-05-19`
  - Runs `PromptImprovementApplierAgent` (gpt-5.4-mini)
  - Reads `prompt_improvement_plan.md` and current instruction contents
  - Calls `update_discovery_instructions` / `update_profiler_instructions` / `update_writer_instructions` only for files the plan flags for change
  - Writes a summary of changed files to `prompt_improvement_applied.md`
  - Whenever any file is updated, immediately publishes the new instructions as Weave `StringPrompt` objects and surfaces the new `prompt_refs` in the trace output (no `--no-publish` opt-out; the pipeline has no manual git-diff review step)
  - Does not edit Python code, schemas, registry, orchestrator, CLI, or deployment files
  - Records a Weave `improve_apply` trace with changed prompt files and new prompt refs in the output
- [x] Every non-dry run publishes instruction files to Weave prompt objects:
  - `autoresearch-discovery-instructions`
  - `autoresearch-profiler-instructions`
  - `autoresearch-writer-instructions`
- [x] Agents use the registered Weave prompt contents during execution
- [x] `run_metadata.json` records `prompt_hashes` and `prompt_refs`

### US13: Annotation Queue review outputs
- [x] `stage1_discovery` root output exposes reviewer fields:
  - `review_markdown`, `candidate_count`, `candidate_names`, `candidate_urls`, `rejected_names`
- [x] `stage2_profile_{slug}` root output exposes reviewer fields:
  - `profile_review_markdown`, `verdict`, `tool_name`, `primary_url`, `rejection_reason`, `autonomy_level`, `domains`, `key_limitations`, `profile_path`, `prompt_ref`
- [x] `stage3_writer` root output exposes reviewer fields:
  - `writer_review_markdown`, `draft_markdown`, `comparison_table_markdown`, `draft_path`, `comparison_table_path`, `tool_count`, `prompt_ref`
- [x] These fields are intended for Weave Annotation Queue display selection

## feedback.md template (auto-generated by US8)

```markdown
# Run {day} Feedback

## Publish decision: ✅ as-is / ⚠️ minor edits / 🔴 major rewrite / ❌ reject

## Quantitative scores (1-5)
- Accuracy:
- Completeness (any missing tools?):
- Table readability:
- Balance (optimistic vs critical sources):
- Recency:

## Edits (structured)
- [ADD]
- [FIX]
- [REMOVE]
- [REWORD]
- [BALANCE]

## System improvement suggestions
- DiscoveryAgent:
- ProfilerAgent:
- WriterAgent:

## Recurring patterns (only issues seen 3+ runs in a row)
```

## Validation (smoke-test level)

Build pass criteria:
- [x] `uv run pytest tests/` passes everything
- [x] Per-agent unit tests (LLM mocked)
- [x] One e2e test: `--max-tools 3 --max-cost-usd 2` dry-run, cost < $2
- [x] e2e output checks:
  - tools/ folder has 3+ tools (only IN-scope ones)
  - comparison_table.md has every column filled (unknown OK)
  - Citation integrity passes
  - No obvious OUT tools (e.g., GPT-Researcher, Perplexity) end up in the result
  - `_profile_runs.jsonl` records one reviewable profiling row per dry-run tool

**Intentionally out of scope to measure**: the "quality" of the publish output. Human review judges that. v1 verifies "the pipeline works".

## Completion criterion

Once every User Story checkbox is ✅, the smoke test fully passes, and one real dry-run produces valid output in `daily_runs/2026-05-19/`:

`<promise>BRIEFING_AGENT_READY</promise>`

## v1 explicit non-goals (deferred to v2+)

- Auto-rewriting prompts from Weave feedback without human review
- Auto-alerts for new releases / updates (RSS, GitHub releases watching)
- HTML / dashboard output
- Multilingual output
- Per-tool stars-over-time graphs
- Fully self-learning agents / RL
