---
name: discovery-forge-weave-improvement
description: Guides coding agents through skill-based prompt improvement for discovery-forge using W&B Weave traces, official W&B Skills guidance, Weave Python SDK/API queries, and human/runnable feedback. Use when the user asks to improve researcher.md from Weave annotations, research_run traces, or a wandb/skills-assisted workflow.
---

# Discovery Forge Weave Improvement

Use this skill when improving `src/discovery_forge/agents/researcher.md` from live Weave evidence with official W&B Skills guidance and direct Weave Python SDK/API queries.

The coding agent fetches evidence, writes a plan, edits the prompt, publishes the prompt, and validates the change.

## Before You Start

Read the official W&B Skills guidance for the surfaces involved:

- Install if needed: `npx skills add wandb/skills`
- Local weave skill references when present:
  - `~/.claude/skills/weave/SKILL.md`
  - `~/.claude/skills/weave/references/feedback.md`
  - `~/.claude/skills/weave/references/prompts.md`
- Upstream source: https://github.com/wandb/skills

Do not use W&B MCP tools in this workflow. Fetch trace and feedback evidence directly through the Weave Python SDK/trace server API.

## Default Project

- Entity: read from `.env` as `WANDB_ENTITY` (required; use your own W&B entity)
- Project: read from `.env` as `WANDB_PROJECT` (required; `.env.example` uses `discovery-forge`)
- API key: read from `.env` as `WANDB_API_KEY` (required)
- Prompt file: `src/discovery_forge/agents/researcher.md`
- Daily trace records: `daily_runs/<day>/_profile_runs.jsonl`
- Improvement history: `src/discovery_forge/agents/improve_history/<day>/plan.md` and `src/discovery_forge/agents/improve_history/<day>/applied.md`
- Root trace unit: one `research_run_<i>` / `openai_agent_trace` call per discovered tool

## Evidence Workflow

1. Identify the target day, run, evaluation, or explicit Weave call IDs.
2. If using a daily run, read `daily_runs/<day>/_profile_runs.jsonl` to get root `weave_call_id` values. If the user provides explicit Weave call IDs or an evaluation call ID, use that target directly.
3. Initialize Weave and query root calls directly through the Python SDK/trace server API.
4. Pull these fields for each root call: `id`, `display_name`, `trace_id`, `output`, `attributes`, `summary`.
5. Pull feedback for the same call IDs with `include_feedback=true` on the call query.
6. Separate feedback into:
   - human annotations: `wandb.annotation.QualitySelector`, `wandb.annotation.QualityReviewer`
   - runnable scorer feedback: `Researcher-quality-check`, `Researcher-category-check`, `Quality-classifiers`
7. Prefer human annotations for final quality judgment, but use runnable scorer feedback for concrete evidence failures such as missing sources, unsupported claims, placeholder URLs, wrong category, or hallucination risk.
8. Read the current `researcher.md`.
9. Write `src/discovery_forge/agents/improve_history/<day>/plan.md` before editing. If the file already exists for that day, overwrite it with the latest plan.

### Query Root Calls With Weave SDK

Follow W&B Skills guidance and query Weave directly. Do not add discovery-forge helper wrappers for call queries.

```python
import json
from pathlib import Path

import weave
from weave.trace_server.trace_server_interface import CallsFilter, CallsQueryReq

from discovery_forge.observability import weave_project_path

day = "<day>"
day_dir = Path("daily_runs") / day
call_ids = [
    json.loads(line)["weave_call_id"]
    for line in (day_dir / "_profile_runs.jsonl").read_text().splitlines()
    if line.strip() and json.loads(line).get("weave_call_id")
]

client = weave.init(weave_project_path())
response = client.server.calls_query(
    CallsQueryReq(
        project_id=client.project_id,
        filter=CallsFilter(call_ids=call_ids),
        include_feedback=True,
        limit=len(call_ids),
    )
)

for call in response.calls:
    print(call.id, call.display_name, len(call.feedback or []))
    print(call.output, call.attributes, call.summary)
```

Use `CallsQueryReq` with `CallsFilter(call_ids=...)` for root traces.
Use `CallsFilter(parent_ids=[eval_call_id])` for evaluation child rows.
Read `call.feedback` from the query response; separate human annotations from runnable scorer rows in your plan.

### Date Scope

- Prefer run day (`output.metadata.day`, `attributes.day`, or `_profile_runs.jsonl.day`) over annotation creation date.
- Include feedback only when the annotated call belongs to the requested day, run ID, or stage.
- Deduplicate feedback by feedback ID.
- Do not treat all historical annotations from a shared queue as current evidence.

### Offline Evaluation Evidence

If the user provides a Weave Evaluation link or eval call ID:

1. Inspect that exact evaluation before rerunning anything.
2. Query the parent evaluation call first with `CallsFilter(call_ids=[eval_call_id])`.
3. Query child rows with `CallsFilter(parent_ids=[eval_call_id])`.
4. Pull only needed columns first: inputs, output, scorer outputs, display name, status.
5. Limit initial child rows to failed scorer rows or a small sample, then broaden only if needed.

Evaluation datasets, audit sidecars, and scorers are read-only evidence. Do not change dataset rows, labels, dedup logic, scorer logic, or evaluation runner behavior to improve scores.

## Plan Format

Use this structure:

```markdown
# Skill-Based Prompt Improvement Plan for <day>

## Source
- Weave traces and feedback queried directly through the Weave Python SDK/API
- Human annotations inspected
- Runnable scorer feedback inspected
- Current `researcher.md` inspected

## Feedback Summary
- <concrete signals and conflicts>

## Proposed Prompt Change
- <exact behavior change>

## Applied Files
- `src/discovery_forge/agents/researcher.md`

## Out of Scope
- <code/dataset/scorer changes not made>
```

## Apply Rules

- Prompt-only changes may edit only `src/discovery_forge/agents/researcher.md`.
- Do not change evaluation datasets or scorers to make results look better.
- Do not create fallback behavior.
- Keep scope verdict separate from metadata completeness.
- If primary sources prove the loop but metadata is incomplete, record the weakness in `key_limitations` instead of rejecting solely for metadata incompleteness.
- Never invent placeholder URLs, paper IDs, arXiv IDs, citations, dates, or docs links. Use `unknown` or `null` when unverified.
- If feedback includes explicit candidate names, URLs, or phrases ("search for X", "missed X", "exclude Y"), preserve the concrete examples in the plan. Use them as query examples or policy examples, not as hardcoded required outputs.
- If `expected_scope_status == accepted` and the agent rejects due to missing metadata, keep scope verdict separate from metadata completeness.
- If `expected_scope_status == rejected` and the agent accepts, treat it as a likely scope-policy issue unless the dataset row itself appears wrong.
- If a dataset row, annotation label, or scorer appears wrong, report it as dataset/scorer maintenance rather than editing those artifacts in this workflow.

After editing, write `src/discovery_forge/agents/improve_history/<day>/applied.md`. If the file already exists for that day, overwrite it with the latest applied summary.

## Publish Prompt

After a prompt edit, publish the updated prompt using the project helper:

```bash
uv run python - <<'PY'
from discovery_forge.observability import init_observability
from discovery_forge.tools.prompts import publish_instruction_prompts, prompt_hashes, prompt_refs

init_observability(day_id="<day>-skill-improve")
versions = publish_instruction_prompts(max_tools=5)
print(prompt_refs(versions))
print(prompt_hashes(versions))
PY
```

Record the prompt ref and prompt hash in `src/discovery_forge/agents/improve_history/<day>/applied.md`.

## Validation

Run focused validation:

```bash
uv run pytest tests/unit/test_researcher.py -q
```

If the change touches code outside `researcher.md`, add or update focused tests and run the relevant unit tests.

## Report Back

Report:

- day/run inspected
- number of root traces queried
- feedback types inspected
- prompt changes made
- Weave prompt ref/hash published
- tests run
- residual risks or items needing manual review
