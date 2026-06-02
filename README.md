# autoresearch-researcher

A hands-on demo of the **annotation → prompt-improvement** loop on top of W&B Weave.

A single agent runs once a day to survey **autonomous research tools in the experiment-automation space** and emit a structured feed (`items/*.json` + `manifest.json`). Tools accumulate into a global registry, so each run only profiles tools it hasn't seen before. Humans review/annotate the per-tool Weave traces, and that feedback drives edits to one prompt (`researcher.md`).

---

## Overview

One agent does discovery **and** profiling, run sequentially up to `--max-tools` times.

```
Orchestrator (CLI)
  └─ ResearcherAgent (×N)  — find ONE new experiment-automation tool, verify it,
                             and save a canonical profile (or reject it)
                             → _registry/profiles/{slug}.md → items/{slug}.json + manifest.json
```

Each run is told what is already covered (an exclusion list built from the registry + this run's rejections) so the N runs don't converge on the same tools.

**Scope**: only tools that automate the "hypothesis → experiment → result → write" cycle. Deep-research tools (web-search + summarization only), curated lists, and survey pages are rejected by the agent's scope filter.

---

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    autoresearch-researcher                        │
│   CLI: autoresearch-researcher run --day 2026-05-19               │
└─────────────────────────┬─────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator (orchestrator.py)                 │
│  • Sequential loop: run ResearcherAgent up to --max-tools times   │
│  • Loads ToolRegistry from daily_runs/_registry/ once per run     │
│  • Builds a per-run exclusion list (registry + this run's saves)  │
│  • CostBudget: enforces --max-cost-usd, graceful shutdown         │
│  • Weave traces: one stage_research_{i} trace per tool            │
│  • After the loop: build_feed_output → items/* + manifest.json    │
└─────────────────────────┬─────────────────────────────────────────┘
                          ▼
              ┌────────────────────────────┐
              │       ResearcherAgent       │   (one run per tool)
              │                             │
              │ Role: find one new in-scope │
              │ tool, verify it, profile or │
              │ reject it                   │
              │                             │
              │ Tools:                      │
              │  search_web (serper default)│
              │  is_known_tool              │
              │  fetch_github_metadata_tool │
              │  save_source_tool           │
              │  save_tool_profile_tool     │
              │  save_rejected_profile_tool │
              │  report_no_new_tool         │
              │                             │
              │ Scope filter: "does this    │
              │  run experiments?" → reject │
              │  if NO                      │
              │                             │
              │ Model: gpt-5.4-mini         │
              └────────────────────────────┘

Data flow:
──────────────────────────────────────────────────────────────────
daily_runs/_registry/
  tools.jsonl                       ← global tool index (one row per tool)
  profiles/{slug}.md                ← canonical ToolProfile per tool

daily_runs/{day}/
  manifest.json                     ← Agentforge feed manifest
  items/{slug}.json                 ← one structured feed item per accepted profile
  raw/                              ← copy of source artifacts for debugging/sync fallback
  _profile_runs.jsonl               ← slug/status/workflow_name/agent_trace_id/weave_call_id per research trace
  _new_candidates.jsonl             ← tools profiled for the first time today
  _updated_tools.jsonl             ← tools whose stars/last_commit changed
  _rejected_profiles.jsonl          ← out-of-scope tools (with reasons)
  _no_new_tool.jsonl                ← agent's "nothing new left" signals
  feedback_events.jsonl             ← Weave human feedback ingested by call id
  prompt_improvement_notes.md       ← maintainer-facing prompt improvement notes
  run_metadata.json                 ← run_id, prompt hashes/refs, counts, tokens, cost

Weave trace model:
──────────────────────────────────────────────────────────────────
📦 stage_research_1                       ← independent root call for human review
  └─ ResearcherAgent                      ← agent span for the tool investigation
      ├─ openai.responses.create          ← model decides next action
      ├─ search_web                       ← configured search backend tool
      ├─ fetch_github_metadata_tool       ← GitHub metadata lookup
      └─ save_tool_profile_tool           ← accepted profile persistence
📦 stage_research_2                       ← one root call per tool
📦 stage_research_3                       ← rejected tools are reviewable too
...

_profile_runs.jsonl links the day/run_id to each tool's workflow_name, agent_trace_id, and weave_call_id.
```

The scope filter is the most important safety net and the main target of the feedback loop: deep-research tools and curated lists quietly slipping in is the most common failure, and it is exactly what reviewers annotate.

---

## Daily Accumulation Model

```
daily_runs/
├── _registry/                       ← global, persistent across days
│   ├── tools.jsonl                  # cumulative tool index
│   └── profiles/{slug}.md           # canonical profiles
│
├── 2026-05-19/                        ← per-day run + change log
│   ├── run_metadata.json             # run_id, prompt hashes/refs, counts, tokens, cost
│   ├── manifest.json                 # Agentforge feed manifest
│   ├── items/{slug}.json             # structured feed items
│   ├── _profile_runs.jsonl           # per-tool trace links
│   ├── _new_candidates.jsonl         # tools profiled for the first time
│   ├── _updated_tools.jsonl          # tools whose metadata changed
│   ├── _rejected_profiles.jsonl      # out-of-scope tools
│   ├── feedback_events.jsonl         # optional, after feedback ingest
│   └── prompt_improvement_notes.md   # optional, after feedback ingest
│
└── 2026-05-20/
    └── ...
```

Each daily run loads the registry, then loops: every ResearcherAgent run gets the exclusion list and calls `is_known_tool(url)` before committing to a candidate, so already-known tools are skipped (saving search / LLM cost). Accepted profiles are written straight into the registry; metadata changes (stars, last commit) on existing tools are detected and logged to `_updated_tools.jsonl`. Each run is recorded in `_profile_runs.jsonl` with the `run_id`, status, `workflow_name`, `agent_trace_id`, prompt hash, and Weave call ID so a human can review and annotate that tool trace directly. After the loop, the feed builder turns the registry profiles into `items/*.json` + `manifest.json`.

---

## Install

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone <repo>
cd autoresearch-researcher
uv sync
cp .env.example .env
# Fill OPENAI_API_KEY (+ SERPER_API_KEY for the default backend), WANDB_API_KEY in .env
```

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | ✅ | OpenAI model calls (and the `openai` search backend) |
| `SERPER_API_KEY` | default backend | Default ResearcherAgent web search; not needed with `--search-backend openai` |
| `PERPLEXITY_API_KEY` | optional | Alternative `--search-backend perplexity` search backend (sonar-pro) |
| `WANDB_API_KEY` | ✅ | W&B Weave tracing |
| `GITHUB_TOKEN` | optional | Raises GitHub API rate limit |
| `WANDB_ENTITY` | optional | Defaults to `wandb-smle` |
| `WANDB_PROJECT` | optional | Defaults to `autoresearch-researcher` |

For a keys-minimal hands-on run, use `--search-backend openai` (hosted `WebSearchTool`) so only `OPENAI_API_KEY` is required.

---

## Usage

### Run a daily briefing

```bash
uv run autoresearch-researcher run --day 2026-05-19
```

Flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--day` | (required) | ISO day id (e.g. `2026-05-19`) |
| `--max-tools` | 20 | Maximum ResearcherAgent runs (≈ max tools profiled) |
| `--max-cost-usd` | 20.0 | Hard cost ceiling — graceful shutdown on overage |
| `--search-backend` | `serper` | Search backend: `serper`, `perplexity`, or `openai` |
| `--since` | `month` | Restrict search results to this recency window: `day`, `week`, `month`, `year`, or `all` (no date filter). Honored by `serper`/`perplexity`; the `openai` backend can only be nudged via the prompt. |
| `--dry-run` | false | Validate the pipeline with no LLM calls (synthetic profiles) |
| `--rerun` | false | Allow re-running an existing day (auto-backs up the previous folder) |

### Ingest Weave feedback

After annotating per-tool `stage_research_<i>` calls in Weave (e.g. via a `D{YYYYMMDD}_Research` annotation queue):

```bash
uv run autoresearch-researcher feedback ingest --day 2026-05-19
```

Produces `feedback_events.jsonl` and `prompt_improvement_notes.md`. This does not rewrite the prompt automatically; it creates reviewable notes for improving `instructions/researcher.md`.

### Propose prompt improvements

```bash
uv run autoresearch-researcher improve propose --day 2026-05-19
```

Runs the `PromptImprovementProposerAgent`. It reads every free-text feedback event in `feedback_events.jsonl` together with the current contents of `instructions/researcher.md`, then writes a concrete plan to `prompt_improvement_plan.md` (failure modes + exact prompt edits, including diff snippets). The proposer never modifies Python code; anything that requires a code change is listed under "Out of scope (code change required)". Traced in Weave as `improve_propose`.

### Apply prompt improvements

```bash
uv run autoresearch-researcher improve apply --day 2026-05-19
```

Runs the `PromptImprovementApplierAgent`. It reads `prompt_improvement_plan.md` and the current `researcher.md`, then calls `update_researcher_instructions` to rewrite the prompt only if the plan proposes a change. A summary is written to `prompt_improvement_applied.md`. Python code is never touched. Whenever the file is updated, `improve apply` immediately publishes the new content as a Weave `StringPrompt`, so the next daily run picks up the new version automatically. Traced in Weave as `improve_apply`.

### Offline evaluation

```bash
uv run autoresearch-researcher eval run-researcher --dataset-path <dataset.jsonl> --output-dir eval_runs/researcher-<date>
```

Runs a Weave Evaluation of the ResearcherAgent's scope/profile decision against a fixed dataset (`scope_decision_scorer`, `profile_quality_scorer`).

### Prompt versioning

Every non-dry run publishes the instruction file to Weave as `autoresearch-researcher-instructions`. The agent uses the registered Weave prompt content for that run. `run_metadata.json` records both `prompt_hashes` and `prompt_refs`, and each stage trace includes the prompt ref.

### Annotation queue review fields

When adding traces to a Weave Annotation Queue, select the reviewer-friendly output fields from the `stage_research_<i>` root call:

| Stage trace | Recommended output fields |
|-------------|---------------------------|
| `stage_research_<i>` | `profile_review_markdown`, `verdict`, `tool_name`, `primary_url`, `rejection_reason`, `autonomy_level`, `domains`, `key_limitations`, `profile_path`, `prompt_ref` |

These fields let a reviewer judge the run from the queue without expanding the full trace tree.

---

## Tests

```bash
# Unit tests (LLM mocked, free)
uv run pytest tests/unit/

# E2E smoke test (dry-run, no real API calls)
uv run pytest -m expensive tests/e2e/

# Everything (unit)
uv run pytest tests/ --ignore=tests/e2e
```

E2E tests are gated behind `@pytest.mark.expensive` so CI skips them by default.

---

## Cost guardrails

`--max-cost-usd` (default $20) triggers a graceful shutdown when the cumulative API spend exceeds the threshold. Outputs already on disk are kept, and the feed is still built from whatever profiles exist.

---

## Customizing the agent prompt

The agent instructions live as a separate Markdown file under `src/autoresearch_researcher/instructions/`, so you can tune the prompt without touching code.

```
instructions/
├── researcher.md       # scope definition, search strategy, profiling + citation rules
├── prompt_proposer.md  # how the improvement proposer behaves
└── prompt_applier.md   # how the improvement applier rewrites researcher.md
```

---

## Non-goals

- Auto-rewriting prompts without any human annotation step
- GitHub releases / RSS notifications
- HTML / dashboard output
- Fully self-learning agents
