# autoresearch-researcher

A multi-agent system that runs once a week to survey **autonomous research tools in the experiment-automation space** and produce a publishable comparison guide (Markdown). Tools are accumulated into a global registry, so each new run only profiles tools you haven't seen before — and emits a "this week's changes" report.

---

## Overview

Three agents run sequentially.

```
Orchestrator (CLI)
  ├─ DiscoveryAgent   — Perplexity-backed search to surface candidate tools     (_candidates.jsonl)
  ├─ ProfilerAgent    — per-tool deep dive + scope filter                        (_registry/profiles/{slug}.md)
  └─ WriterAgent      — comparison table + publishable draft + highlights        (draft.md, comparison_table.md)
```

**Scope**: only tools that automate the "hypothesis → experiment → result → write" cycle. Deep-research tools (web-search + summarization only) are auto-rejected by the ProfilerAgent's scope filter.

---

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    autoresearch-researcher                       │
│                                                                  │
│   CLI: autoresearch-researcher run --week 2026-W19               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator                                  │
│                  (orchestrator.py)                               │
│                                                                  │
│  • Pipeline flow control (Discovery → Profiling → Writing)       │
│  • Loads ToolRegistry from weekly_runs/_registry/ once per run   │
│  • CostBudget: enforces --max-cost-usd, graceful shutdown        │
│  • Weave traces: named stage traces + one profile trace per tool │
│  • run_metadata.json: tokens / cost / elapsed time               │
│  • Resume: skips Discovery if _candidates.jsonl already exists   │
└──────┬───────────────────────┬───────────────────┬──────────────┘
       │                       │                   │
       ▼                       ▼                   ▼
   Stage 1                Stage 2 (×N)         Stage 3
       │                       │                   │
┌──────┴──────┐     ┌──────────┴──────┐   ┌───────┴──────┐
│DiscoveryAgent│     │  ProfilerAgent  │   │ WriterAgent   │
│             │     │  (per candidate)│   │              │
│ Role:        │     │                 │   │ Role:        │
│ Find new    │     │ Role:           │   │ Generate     │
│ tools via   │     │ Deep-dive on    │   │ comparison   │
│ broad web   │     │ one tool +      │   │ table +      │
│ search      │     │ scope-filter    │   │ draft.md     │
│             │     │                 │   │              │
│ Tools:       │     │ Tools:          │   │ Tools:       │
│ search_web  │     │ search_web      │   │ read_tool_   │
│ (Perplexity)│     │ (Perplexity)    │   │ profiles     │
│ is_known_   │     │ fetch_github_   │   │ read_high-   │
│ _tool       │     │ _metadata       │   │ lights       │
│ save_       │     │ save_tool_      │   │ save_draft   │
│ candidate   │     │ _profile        │   │ save_compa-  │
│             │     │                 │   │ rison_table  │
│ Output:      │     │ Scope filter:   │   │              │
│_candidates  │     │ "does this run  │   │ Output:      │
│  .jsonl     │     │  experiments?"  │   │ draft.md     │
│             │     │ → reject if NO  │   │ comparison_  │
│ Model:       │     │                 │   │  table.md    │
│ gpt-5.4-    │     │ Output:         │   │              │
│ mini        │     │ _registry/      │   │ Model:       │
│             │     │ profiles/{slug} │   │ gpt-5.4-mini │
└─────────────┘     │                 │   └──────────────┘
                    │ Model:          │
                    │ gpt-5.4-mini    │
                    └─────────────────┘

Data flow:
──────────────────────────────────────────────────────────────────
weekly_runs/_registry/
  tools.jsonl                       ← global tool index (one row per tool)
  profiles/{slug}.md                ← canonical ToolProfile per tool
  sources.jsonl                     ← cumulative citation sources

weekly_runs/{week}/
  _candidates.jsonl                 ← Discovery output
  _profile_runs.jsonl               ← slug/status/workflow_name/agent_trace_id/weave_call_id per profile trace
  _new_candidates.jsonl             ← tools profiled for the first time this week
  _updated_tools.jsonl              ← tools whose stars/last_commit changed
  feedback_events.jsonl             ← Weave human feedback ingested by call id
  prompt_improvement_notes.md       ← maintainer-facing prompt improvement notes
  highlights.md                     ← auto-generated "what's new" section
  draft.md                          ← main publishable draft
  comparison_table.md               ← standalone table

Weave trace model:
──────────────────────────────────────────────────────────────────
📦 stage1_discovery                       ← DiscoveryAgent SDK workflow
  └─ Output: Markdown table of discovered/rejected candidates for quick review
📦 stage2_profile_tool-a                  ← independent root call for human review
  └─ ProfilerAgent                        ← agent span for the tool investigation
      ├─ openai.responses.create          ← model decides next action
      ├─ search_web                       ← Perplexity-backed search tool
      ├─ fetch_github_metadata_tool       ← GitHub metadata lookup
      └─ save_tool_profile_tool           ← accepted profile persistence
📦 stage2_profile_tool-b                  ← one root call per candidate
📦 stage2_profile_rejected-c              ← rejected tools are reviewable too
📦 stage3_writer                          ← WriterAgent SDK workflow

_profile_runs.jsonl links the week/run_id to each tool's workflow_name, agent_trace_id, and weave_call_id.
```

### Per-agent role summary

| | DiscoveryAgent | ProfilerAgent | WriterAgent |
|---|---|---|---|
| **When** | Stage 1, once | Stage 2, once per candidate | Stage 3, once |
| **Input** | Scope definition | One candidate (name, URL) | All registry profiles |
| **What** | 15+ Perplexity searches to surface candidates | Deep-dive collection + **scope filter** | Compose comparison table + draft |
| **Key check** | First-pass IN/OUT classification | "Does this actually run experiments?" (second-pass verify) | Facts only, no marketing tone |
| **On failure** | Save partial list, halt | Save rejection reason, move on | Compose with whatever is there |

ProfilerAgent's scope filter is the most important safety net: even if Discovery seeds a deep-research tool into the candidate list, ProfilerAgent's second-pass filter will catch it.

---

## Weekly Accumulation Model

```
weekly_runs/
├── _registry/                       ← global, persistent across weeks
│   ├── tools.jsonl                  # cumulative tool index
│   ├── profiles/{slug}.md           # canonical profiles
│   └── sources.jsonl
│
├── 2026-W19/                        ← per-week change log
│   ├── run_metadata.json             # run_id, prompt hashes, counts, tokens, cost
│   ├── _candidates.jsonl             # Discovery output
│   ├── _profile_runs.jsonl          # per-tool trace links
│   ├── _new_candidates.jsonl        # tools profiled for the first time
│   ├── _updated_tools.jsonl         # tools whose metadata changed
│   ├── feedback_events.jsonl        # optional, after feedback ingest
│   ├── prompt_improvement_notes.md  # optional, after feedback ingest
│   ├── highlights.md
│   ├── draft.md
│   └── comparison_table.md
│
└── 2026-W20/
    └── ...
```

Each weekly run starts by loading the registry. DiscoveryAgent calls `is_known_tool(url)` before saving any candidate — already-known tools are skipped, saving Perplexity / LLM cost. ProfilerAgent only profiles new candidates; metadata changes (stars, last commit) on existing tools are detected and logged to `_updated_tools.jsonl`. Each candidate profile attempt is recorded in `_profile_runs.jsonl` with the `run_id`, status, `workflow_name`, `agent_trace_id`, prompt hash, and Weave call ID so a human can review and annotate that tool trace directly. WriterAgent reads all profiles from the registry and the per-week change files.

---

## Install

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone <repo>
cd autoresearch-researcher
uv sync
cp .env.example .env
# Fill OPENAI_API_KEY, PERPLEXITY_API_KEY, WANDB_API_KEY in .env
```

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | ✅ | OpenAI Chat Completions |
| `PERPLEXITY_API_KEY` | ✅ | DiscoveryAgent + ProfilerAgent web search (sonar-pro) |
| `WANDB_API_KEY` | ✅ | W&B Weave tracing |
| `GITHUB_TOKEN` | optional | Raises GitHub API rate limit |
| `WANDB_ENTITY` | optional | Defaults to `wandb-smle` |
| `WANDB_PROJECT` | optional | Defaults to `autoresearch-researcher` |

---

## Usage

### Run a weekly briefing

```bash
uv run autoresearch-researcher run --week 2026-W19
```

Flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--week` | (required) | ISO week id (e.g. `2026-W19`) |
| `--max-tools` | 12 | Maximum candidates ProfilerAgent will process |
| `--max-cost-usd` | 20.0 | Hard cost ceiling — graceful shutdown on overage |
| `--dry-run` | false | Validate the pipeline with no LLM calls |
| `--rerun` | false | Allow re-running an existing week (auto-backs up the previous folder) |

### Generate diff after human review

After you write `final.md`:

```bash
uv run autoresearch-researcher diff --week 2026-W19
```

Produces `diff.md` (changes classified ADD / FIX / REMOVE / REWORD / BALANCE) and a `feedback.md` template.

### Ingest Weave feedback

After annotating per-tool `stage2_profile_<tool>` calls in Weave:

```bash
uv run autoresearch-researcher feedback ingest --week 2026-W19
```

Produces `feedback_events.jsonl` and `prompt_improvement_notes.md`. This does not rewrite prompts automatically; it creates reviewable notes for improving `instructions/*.md`.

---

## Tests

```bash
# Unit tests (LLM mocked, free)
uv run pytest tests/unit/

# E2E smoke test (dry-run, no real API calls)
uv run pytest -m expensive tests/e2e/

# Everything
uv run pytest tests/
```

E2E tests are gated behind `@pytest.mark.expensive` so CI skips them by default.

---

## Cost guardrails & resume

`--max-cost-usd` (default $20) triggers a graceful shutdown when the cumulative API spend exceeds the threshold. Stage outputs already on disk are kept. On the next run, if `_candidates.jsonl` exists, Discovery is skipped and ProfilerAgent resumes from there.

---

## Customizing agent prompts

All agent instructions live as separate Markdown files under `src/autoresearch_researcher/instructions/`. You can tune prompts without touching code.

```
instructions/
├── discovery.md   # scope definition, search strategy
├── profiler.md    # collection fields, scope filter rules
└── writer.md      # publish format, tone guide
```

---

## v1 non-goals (deferred to v2+)

- Auto-rewriting prompts without human review
- GitHub releases / RSS notifications
- HTML / dashboard output
- Fully self-learning agents
