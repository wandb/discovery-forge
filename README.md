# discovery-forge

A hands-on demo of the **annotation → prompt-improvement** loop on top of W&B Weave.

A single agent runs once a day to survey **autonomous research tools in the experiment-automation space** and emit a structured feed (`items/*.json` + `manifest.json`). Tools accumulate into a global registry, so each run only profiles tools it hasn't seen before. Humans review/annotate the per-tool Weave traces, and that feedback drives edits to one prompt (`researcher.md`).

---

## This Is the Hands-On Starting Point

> **For workshop participants:** This repository's `main` branch *is* the hands-on
> starting point. There is no separate setup branch to check out — clone the repo,
> stay on `main`, and follow the steps below.

`discovery-forge` is built to be edited live during the session. You will:

1. Run the daily ResearcherAgent loop and watch the Weave traces it produces.
2. Annotate those `research_run_<i>` traces in Weave.
3. Use the project skills to turn that feedback into a prompt-only change to
   `researcher.md`, then rerun and compare.
4. Close the loop with offline evaluation against a published Weave dataset.

Everything you touch lives in this repo: the agent prompt (`researcher.md`), the
improvement skills (`skills/`).

### Companion Project: AI Engineering Dojo

This hands-on goes together with the **AI Engineering Dojo**:
<https://github.com/wandb/ai_engineering_dojo>.

The AI Engineering Dojo is the learning-content repository for building,
evaluating, monitoring, and continuously improving Auto Research Agents. Its
main learning subject *is* Discovery Forge — the Dojo owns the learning content
structure, domain specification, evaluation/monitoring concepts, and W&B Weave
integration guidance, while this repository is the Discovery Forge codebase that
participants actually run and improve.

In short: read the **AI Engineering Dojo** for the lesson flow, domain spec, and
evaluation design, and use **this repo** as the live ResearcherAgent
implementation you edit during the session.

---

## Overview

One agent does discovery **and** profiling, run sequentially up to `--max-tools` times.

```
main.py
  └─ run_research()
      └─ orchestrator.run_briefing()
          └─ ResearcherAgent (×N)  — find ONE experiment-automation tool,
                                     verify it, and save a canonical profile
                                     (or reject it)
                                     → _registry/profiles/{slug}.md
                                     → items/{slug}.json + manifest.json
```

Each run is told what is already covered (an exclusion list built from the registry + this run's rejections) so the N runs don't converge on the same tools.

**Scope**: only tools that automate the "hypothesis → experiment → result → write" cycle. Deep-research tools (web-search + summarization only), curated lists, and survey pages are rejected by the agent's scope filter.

---

## Agent Architecture

The orchestrator (`orchestrator.py`) loads the tool registry once, then runs the
`ResearcherAgent` sequentially up to `--max-tools` times. Each run gets an
exclusion list (registry + this run's saves) and a recency hint, writes its own
`search_web` queries, verifies a candidate, and either profiles or rejects it.
A `CostBudget` enforces `--max-cost-usd` with graceful shutdown, and after the
loop the feed builder emits `items/*.json` + `manifest.json`.

The `ResearcherAgent` (`gpt-5.4-mini`) has one job: find a new in-scope tool,
verify it, and profile or reject it. Its tools are `search_web`, `is_known_tool`,
`fetch_github_metadata_tool`, `save_source_tool`, `save_tool_profile_tool`,
`save_rejected_profile_tool`, and `report_no_new_tool`. The **scope filter**
("does this tool actually run experiments?") is the most important safety net and
the main target of the feedback loop — deep-research tools and curated lists
slipping in is the most common failure, and exactly what reviewers annotate.

Each run becomes one independent Weave root call, so reviewers can open and
annotate it directly:

```
📦 research_run_1                  ← independent root call for human review
  └─ ResearcherAgent               ← agent span for the tool investigation
      ├─ openai.responses.create   ← model decides next action
      ├─ search_web                ← configured search backend tool
      ├─ fetch_github_metadata_tool
      └─ save_tool_profile_tool    ← accepted profile persistence
📦 research_run_2                  ← one root call per tool (rejected tools too)
```

> For the lesson narrative around this agent (what it does and why), see the AI
> Engineering Dojo `understand-the-agent` chapter.

---

## Daily Accumulation Model

The registry is global and persistent; each day writes its own run folder. Known
tools (`is_known_tool(url)`) are skipped to save search / LLM cost, accepted
profiles go straight into the registry, and metadata changes (stars, last commit)
are logged to `_updated_tools.jsonl`. Every run is recorded in
`_profile_runs.jsonl` with the `run_id`, status, `workflow_name`,
`agent_trace_id`, prompt hash, and `weave_call_id` so a human can review and
annotate that tool's trace directly.

```
daily_runs/
├── _registry/                  ← global, persistent across days
│   ├── tools.jsonl             # cumulative tool index
│   └── profiles/{slug}.md      # canonical ToolProfile per tool
│
└── {day}/                      ← per-day run + change log
    ├── run_metadata.json       # run_id, prompt hashes/refs, counts, tokens, cost
    ├── manifest.json           # Agentforge feed manifest
    ├── items/{slug}.json       # structured feed items
    ├── _profile_runs.jsonl     # per-tool trace links (incl. weave_call_id)
    ├── _new_candidates.jsonl   # tools profiled for the first time
    ├── _updated_tools.jsonl    # tools whose stars/last_commit changed
    └── _rejected_profiles.jsonl# out-of-scope tools (with reasons)
```

The agent writes its own `search_web` queries from the Query Example Pool in
`agents/researcher.md` plus the exclusion list and recency hint, so query
strategy stays prompt-editable. Skill-guided prompt improvement records live
beside the prompt, not under `daily_runs`:
`src/discovery_forge/agents/improve_history/<day>/{plan,applied}.md`.

---

## Install

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

Clone the repo and stay on `main` — that branch is the hands-on starting point.

```bash
git clone <repo>
cd discovery-forge
git checkout main   # the hands-on starting point; no separate setup branch
uv sync
npx skills add wandb/skills # install wandb official skills
cp .env.example .env
# Fill OPENAI_API_KEY, WANDB_API_KEY, WANDB_ENTITY, WANDB_PROJECT
# and SERPER_API_KEY for the default backend.
```

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | ✅ | OpenAI model calls (and the `openai` search backend) |
| `SERPER_API_KEY` | ✅ | Default ResearcherAgent web search　|
| `WANDB_API_KEY` | ✅ | W&B Weave tracing |
| `WANDB_ENTITY` | ✅ | Your W&B entity for Weave traces and eval results |
| `WANDB_PROJECT` | ✅ | W&B project; `.env.example` uses `discovery-forge` for the hands-on |

The minimal `.env.example` contains the required/default hands-on keys. Add optional keys only when using the matching backend or integration.

---

## Usage

### Hands-On Default Flow

Start with the three root entrypoint files. They are intentionally small so a
learner can open each one and follow the flow into `src/discovery_forge/`.

```bash
# 1. Run the daily ResearcherAgent loop
uv run python main.py \
  --day 2026-05-19 \
  --max-tools 5 \
  --max-cost-usd 5 \
  --search-backend serper

# 2. Improve from Weave annotations with the project skill
# read and follow skills/annotation-improvement/SKILL.md

# 3. Run offline eval against the published Weave dataset
uv run python evaluate.py \
  --verdict-dataset-ref '<verdict-dataset-ref>'

# 4. Improve from offline eval failures with the project skill
# read and follow skills/offline-eval-improvement/SKILL.md
```

### Run a daily briefing

```bash
uv run python main.py --day 2026-05-19
```

The default search backend is `serper`. For a keys-minimal hands-on run, pass
`--search-backend openai` explicitly.

Flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--day` | today | ISO day id (e.g. `2026-05-19`) |
| `--output-dir` | `daily_runs` | Base output directory |
| `--max-tools` | 10 | Maximum ResearcherAgent runs (≈ max tools profiled) |
| `--max-cost-usd` | 20.0 | Hard cost ceiling — graceful shutdown on overage |
| `--search-backend` | `serper` | Search backend: `serper`, `perplexity`, or `openai` |
| `--since` | `month` | Restrict search results to this recency window: `day`, `week`, `month`, `year`, or `all` (no date filter). Honored by `serper`/`perplexity`; the `openai` backend can only be nudged via the prompt. |
| `--dry-run` | false | Validate the pipeline with no LLM calls (synthetic profiles) |
| `--rerun` | false | Allow re-running an existing day (auto-backs up the previous folder) |

### Improve From Weave Annotations

After annotating per-tool `research_run_<i>` calls in Weave, run the prompt-only
improvement loop by following the project skill:

```text
skills/annotation-improvement/SKILL.md
```

The skill reads the real trace feedback via the Weave SDK, plans the change,
edits `researcher.md`, writes `improve_history/<day>/{plan,applied}.md`, and
publishes the updated prompt. Datasets and scorers stay read-only evidence — the
loop only edits the prompt. The Dojo `improve-from-annotations` and
`review-and-annotation` chapters cover the queue setup and reviewer fields.

### Offline evaluation

The eval dataset is published to Weave as `verdict_quality_dataset`; `evaluate.py`
loads the pinned ref from `src/discovery_forge/evaluation/evaluation_config.yaml`:

```bash
uv run python evaluate.py                                  # evaluation_config.yaml verdict_quality
uv run python evaluate.py --verdict-dataset-key verdict_quality
uv run python evaluate.py --verdict-dataset-ref '<ref>'    # override
```

To publish a new dataset version, use
`discovery_forge.evaluation.datasets.publish_eval_dataset` and update the
matching ref in `evaluation_config.yaml`. To improve the prompt from failed eval
rows, follow `skills/offline-eval-improvement/SKILL.md` with the dataset, start
prompt, baseline evaluation ID, and max iteration count from the same config.
See the Dojo `build-eval-dataset` chapter for dataset design.

### Prompt versioning

Every non-dry run publishes the instruction file to Weave as
`researcher_instructions`, and the agent uses that registered prompt for the run.
`run_metadata.json` records both `prompt_hashes` and `prompt_refs`, and each
trace includes the prompt ref.

> If you configure Weave monitors/scorers in the UI, use the `Researcher-*`
> names (`Researcher-quality-check`, `Researcher-category-check`,
> `Quality-classifiers`). Older `Profiler-*` feedback is legacy evidence only.

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

> **Cost guardrail:** `--max-cost-usd` (default $20) triggers a graceful shutdown
> when cumulative API spend exceeds the threshold. Outputs already on disk are
> kept and the feed is still built from whatever profiles exist.

---

## Customizing the agent prompt

The agent instructions live as Markdown beside the agent implementation under `src/discovery_forge/agents/`, so you can tune the prompt without touching Python code.

```
agents/
├── researcher.py        # ResearcherAgent construction
├── researcher_tools.py  # ResearcherAgent tool wiring
├── researcher.md        # scope definition, Query Example Pool, profiling + citation rules
└── improve_history/     # dated prompt improvement plans and applied summaries
```

---

## Non-goals

- Auto-rewriting prompts without any human annotation step
- GitHub releases / RSS notifications
- HTML / dashboard output
- Fully self-learning agents
