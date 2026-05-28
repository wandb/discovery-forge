---
name: autoresearch-feedback-improvement
description: Guides coding agents through a three-step workflow for improving autoresearch-researcher from live Weave annotations: fetch annotation evidence, plan prompt/code improvements, and execute validated changes. Use when changing prompts, profiler/discovery behavior, annotation datasets, eval logic, or feedback-driven improvement code.
disable-model-invocation: true
---

# Autoresearch Feedback Improvement

Use this skill when improving the autoresearch pipeline from live Weave annotations. Local annotation seed files are fixtures and historical reference only; do not use them as the default source for new feedback.

## Workflow Overview

1. Fetch annotation evidence from Weave.
2. Plan prompt and code improvements from that evidence.
3. Execute the approved improvements with focused validation.

## 1. Fetch Annotation Evidence

Always fetch current annotation evidence from Weave unless the user explicitly asks to inspect local fixtures.

Default project:

- Entity: `wandb-smle`
- Project: `autoresearch-researcher`
- Important annotation types: `QualityReviewer`, `QualitySelector`, day-scoped discovery/profiler annotations, and older profiler scorer annotations when relevant

### Date Scope

Distinguish two date concepts:

- Annotation date: when the human feedback was created (`feedback.created_at`).
- Run day: the daily run that produced the annotated trace (`call.attributes.day` or trace metadata `day`).

For improvement work, default to **run day**. Use annotation date only for incremental cursoring.

Fetch rule:

- Include feedback only when the annotated call belongs to the requested `day`, `run_id`, or `stage` scope.
- Use `feedback.created_at` as a watermark for new or unprocessed annotations.
- Deduplicate by `feedback.id`.
- Do not treat all historical annotations from a shared queue as new evidence.

### Incremental Annotation Cursor

When annotations are repeatedly added to the same queue, use a cursor state per queue or feedback type:

- `last_ingested_at`
- `seen_feedback_ids`
- optional `last_run_id`
- optional `days_processed`

When fetching:

1. Load the cursor state if one exists.
2. Query Weave feedback newer than the cursor.
3. Resolve each feedback row to its annotated call.
4. Keep only calls matching the requested run day, run ID, or stage.
5. Drop feedback IDs already seen.
6. Update the cursor only after evidence has been summarized or saved.

### Evidence Summary

Before planning changes, summarize:

- feedback count inspected
- target day or run ID
- affected stages: `discovery`, `profiling`, `writing`, `improve`
- repeated failure modes
- representative call IDs or trace names
- whether the evidence points to prompt changes, code changes, or both

Common failure modes in this project:

- Rejected profiler outputs hide the candidate URL or source URLs.
- Survey, awesome-list, resource, or review pages need explicit `survey` / `resource` classification.
- Duplicate or already-known tools reappear because URL aliases are not canonicalized enough.
- General AI-scientist tools are too broad when the user wants coding-agent/model-improvement examples.
- Metadata incompleteness is treated as scope rejection instead of a separate completeness issue.

## 2. Plan Improvements

Create an improvement plan before editing files. The plan can include both prompt and code changes, but each item must be classified.

Improvement categories:

- `prompt-only`: edits only `src/autoresearch_researcher/instructions/*.md`.
- `schema-review-output`: changes schemas, saved rejected profiles, or Weave review markdown.
- `registry-dedup`: changes URL normalization, alias handling, or known-tool filtering.
- `discovery-policy`: changes Discovery search, candidate acceptance, or rejected candidate handling.
- `profiler-policy`: changes Profiler scope decisions, rejection categories, or metadata handling.
- `eval-dataset`: changes annotation seed normalization, golden rows, or scorer inputs.
- `manual-review`: creates a review queue item rather than encoding uncertain behavior.

For each planned item, include:

- evidence: feedback text, call ID, trace name, or queue item
- target files
- expected behavior change
- test plan
- whether it is prompt-only or code-related
- risk level: `low`, `medium`, or `high`

Planning rules:

- If multiple categories apply, keep the implementation scoped to the smallest useful slice.
- Prompt-only changes may only edit `src/autoresearch_researcher/instructions/*.md`.
- Code changes require a focused failing test first.
- Do not create fallback behavior.
- Keep scope verdict separate from metadata completeness.
- Preserve the Discovery -> Profiler -> Writer pipeline unless the user explicitly asks to redesign it.

## 3. Execute Improvements

Execute the approved plan in the smallest safe order:

1. Update or add focused tests or eval fixtures when behavior changes.
2. Apply code changes.
3. Apply prompt changes.
4. Run focused validation.
5. Summarize which annotation failure modes were addressed.

### Prompt Changes

For prompt-only changes:

1. Use the existing feedback-improvement design in `src/autoresearch_researcher/tools/improvement.py` when appropriate.
2. Edit only instruction markdown under `src/autoresearch_researcher/instructions/`.
3. Do not modify Python code, schemas, CLI, registry, or tests unless the plan explicitly includes code changes.
4. Preserve prompt publishing through Weave `StringPrompt` objects.
5. Explain which annotation failure mode the prompt now addresses.

### Code Changes

For code changes:

1. Write or update a focused test first.
2. Preserve the Discovery -> Profiler -> Writer pipeline unless the user explicitly asks to redesign it.
3. Do not create fallback behavior.
4. Keep scope verdict separate from metadata completeness whenever possible.
5. Prefer small schema or review-output changes before larger orchestration changes.

## Weave Guidance

Use W&B/Weave patterns consistently:

- Keep `weave.init()` centralized in the orchestrator entrypoint.
- Keep prompt files versioned as Weave `StringPrompt` objects.
- Use Weave annotations as evaluation evidence, not as raw instructions to blindly apply.
- When querying Weave through MCP, read the tool schema before calling the tool.
- For Weave SDK or evaluation details, consult the official W&B skill or docs before writing code.

## Validation

Run the smallest meaningful validation:

- Unit tests for schema normalization, rejection categories, dedup logic, or scorer behavior.
- Existing prompt-improvement tests for prompt-only changes.
- Dry-run or mocked e2e tests when pipeline artifacts change.

## Final Response Format

When done, report:

- annotation evidence inspected
- improvement plan executed
- prompt changes made
- code changes made
- tests run
- remaining risks or review queue items
