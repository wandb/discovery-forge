# Online Annotation Improvement

Use this workflow when improving the pipeline from fresh human annotations attached to live Weave traces.

Local annotation seed files are fixtures and historical reference only. Do not use them as the default source for new feedback.

## 1. Fetch Annotation Evidence

Always fetch current annotation evidence from Weave unless the user explicitly asks to inspect local fixtures.

Default project:

- Entity: `wandb-smle`
- Project: `autoresearch-researcher`
- Important annotation types: `QualityReviewer`, `QualitySelector`, day-scoped research annotations (`D{YYYYMMDD}_Research`), and older scorer annotations when relevant.

### Date Scope

Distinguish two date concepts:

- Annotation date: when human feedback was created (`feedback.created_at`).
- Run day: the daily run that produced the annotated trace (`call.attributes.day` or trace metadata `day`).

For improvement work, default to **run day**. Use annotation date only for incremental cursoring.

Fetch rules:

- Include feedback only when the annotated call belongs to the requested `day`, `run_id`, or `stage` scope.
- Use `feedback.created_at` as a watermark for new or unprocessed annotations.
- Deduplicate by `feedback.id`.
- Do not treat all historical annotations from a shared queue as new evidence.

### Incremental Cursor

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

## 2. Summarize Evidence

Before planning changes, summarize:

- feedback count inspected
- target day or run ID
- affected stages: `research`, `improve`
- repeated failure modes
- representative call IDs or trace names
- whether the evidence points to prompt changes, code changes, or both

Common failure modes:

- Rejected profiler outputs hide the candidate URL or source URLs.
- Survey, awesome-list, resource, or review pages need explicit `survey` / `resource` classification.
- Duplicate or already-known tools reappear because URL aliases are not canonicalized enough.
- General AI-scientist tools are too broad when the user wants coding-agent/model-improvement examples.
- Metadata incompleteness is treated as scope rejection instead of a separate completeness issue.

## 3. Plan Improvements

Create an improvement plan before editing files. Classify each item:

- `prompt-only`: edits only `src/autoresearch_researcher/instructions/researcher.md`
- `schema-review-output`: changes schemas, saved rejected profiles, or Weave review markdown
- `registry-dedup`: changes URL normalization, alias handling, or known-tool filtering
- `researcher-policy`: changes the ResearcherAgent's search, scope decisions, rejection handling, or metadata extraction
- `manual-review`: creates a review queue item rather than encoding uncertain behavior

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
- Do not change evaluation datasets, annotation labels, scorer logic, or evaluation runner code as part of feedback-driven agent improvement. Report those as separate maintenance follow-ups.

## 4. Execute Improvements

Execute approved changes in the smallest safe order:

1. Update or add focused tests or eval fixtures when behavior changes.
2. Apply code changes.
3. Apply prompt changes.
4. Run focused validation.
5. Summarize which annotation failure modes were addressed.

For prompt-only changes:

- Use the existing feedback-improvement design in `src/autoresearch_researcher/tools/improvement.py` when appropriate.
- Edit only instruction markdown under `src/autoresearch_researcher/instructions/`.
- Preserve prompt publishing through Weave `StringPrompt` objects.

For code changes:

- Write or update a focused test first.
- Prefer small schema or review-output changes before larger orchestration changes.
- Keep changes focused on agent behavior or agent-facing review output, not dataset/scorer mechanics.
