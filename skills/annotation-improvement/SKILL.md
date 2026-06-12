---
name: annotation-improvement
description: Guides coding agents through prompt improvement for discovery-forge using W&B Weave research_run traces, human annotations, runnable feedback, and W&B Skills. Use when the user asks to improve researcher.md from annotation queues, reviewed research traces, or human feedback.
---

# Annotation Improvement

Use this skill when improving `src/discovery_forge/agents/researcher.md` from live Weave annotation evidence with W&B Skills.

The coding agent fetches evidence, writes a plan, edits the prompt, publishes the prompt, and validates the change.

## Before You Start

Follow `AGENTS.md` W&B Skills setup first. Use W&B Skills for Weave trace, feedback, annotation, prompt, and evaluation access; this skill only defines the Discovery Forge prompt-improvement workflow.

Fetch all trace and feedback evidence live from Weave through W&B Skills. Do not use W&B MCP tools, and do not add discovery-forge query wrappers.

## Default Project

- Entity: read from `.env` as `WANDB_ENTITY` (required; use your own W&B entity)
- Project: read from `.env` as `WANDB_PROJECT` (required; `.env.example` uses `discovery-forge`)
- API key: read from `.env` as `WANDB_API_KEY` (required)
- Prompt file: `src/discovery_forge/agents/researcher.md`
- Evidence source: Weave traces and feedback fetched live via W&B Skills
- Improvement history: `src/discovery_forge/agents/improve_history/<day>/plan.md` and `src/discovery_forge/agents/improve_history/<day>/applied.md`
- Root trace unit: one `research_run_<i>` / `openai_agent_trace` call per discovered tool

## Evidence Workflow

1. Identify the target from what the user gives you: explicit Weave call IDs, a Weave Evaluation link / eval call ID, a run day, or a run ID.
2. Use W&B Skills to fetch the target root calls and feedback **from Weave**. If you only have a day or run ID, use W&B Skills to identify the matching root calls for that scope.
3. Include feedback evidence for the same root calls.
4. Read these fields per root call: `id`, `display_name`, `output`, `attributes`, `summary`, `feedback`.
5. Separate feedback into:
   - human annotations: `wandb.annotation.QualitySelector`, `wandb.annotation.QualityReviewer`
   - runnable scorer feedback: `Researcher-quality-check`, `Researcher-category-check`, `Quality-classifiers`
6. Prefer human annotations for final quality judgment, but use runnable scorer feedback for concrete evidence failures such as missing sources, unsupported claims, placeholder URLs, wrong category, or hallucination risk.
7. Read the current `researcher.md`.
8. Write `src/discovery_forge/agents/improve_history/<day>/plan.md` before editing. If the file already exists for that day, overwrite it with the latest plan.

### Evidence Selection

Use W&B Skills to fetch and inspect Weave evidence. This skill only defines which Discovery Forge evidence matters:

- Root trace unit: one root call per discovered tool, display name `research_run_<i>` (or `openai_agent_trace`).
- For explicit Weave call IDs, inspect exactly those calls.
- For a day/run target, inspect the matching `research_run_*` root calls for that scope.
- For an evaluation target, inspect the parent evaluation call and its child rows.
- Read only the evidence needed for analysis: call identity, display name, output, attributes, summary, and feedback.
- Separate human annotations from runnable scorer feedback in the plan.

### Date Scope

- Prefer run day from the Weave call output or attributes over annotation creation date.
- Include feedback only when the annotated call belongs to the requested day, run ID, or stage.
- Deduplicate feedback by feedback ID.
- Do not treat all historical annotations from a shared queue as current evidence.

### Offline Evaluation Evidence

If the user provides a Weave Evaluation link or eval call ID:

1. Inspect that exact evaluation before rerunning anything.
2. Use W&B Skills to inspect the parent evaluation call first.
3. Use W&B Skills to inspect the evaluation child rows.
4. Read only the fields you need first: inputs, output, scorer outputs, display name, status.
5. Limit initial child rows to failed scorer rows or a small sample, then broaden only if needed.

Evaluation datasets, audit sidecars, and scorers are read-only evidence. Do not change dataset rows, labels, dedup logic, scorer logic, or evaluation runner behavior to improve scores.

## Plan Format

Use this structure:

```markdown
# Skill-Based Prompt Improvement Plan for <day>

## Source
- Weave traces and feedback fetched via W&B Skills
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
