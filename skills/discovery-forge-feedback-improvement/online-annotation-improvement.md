# Online Annotation Improvement

Use this workflow when improving the pipeline from fresh human annotations attached to live Weave traces.

Local annotation seed files are fixtures and historical reference only. Do not use them as the default source for new feedback.

## 1. Fetch Annotation Evidence

Always fetch current annotation evidence from Weave unless the user explicitly asks to inspect local fixtures.

Default project:

- Entity: `wandb-smle`
- Project: `discovery-forge`
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

### Conversational Review Evidence

Human review evidence is not limited to Weave feedback rows. If the user gives feedback in chat while reviewing traces, feed items, or generated artifacts, treat it as evidence too.

Examples:

- "X should also be listed"
- "Search for X"
- "This cookbook should be excluded"
- "Awesome repos should be leads, not saved directly"
- "This field is missing or wrong"
- "The summary should sound like this example"

When the user gives direct candidate or query feedback:

- Preserve the exact candidate names, URLs, and phrases in the improvement plan.
- Add a concrete prompt or query-pool change that would help the ResearcherAgent rediscover similar systems.
- Do not only generalize the feedback into broad policy language.
- Do not hardcode the candidate as a required output; use it as a query example, representative missed candidate, or source-priority hint.

Common failure modes:

- Rejected profiler outputs hide the candidate URL or source URLs.
- Survey, awesome-list, resource, or review pages need explicit `survey` / `resource` classification.
- Duplicate or already-known tools reappear because URL aliases are not canonicalized enough.
- General AI-scientist tools are too broad when the user wants coding-agent/model-improvement examples.
- Metadata incompleteness is treated as scope rejection instead of a separate completeness issue.
- Missed candidate / search coverage gaps: feedback phrases like "should also be listed", "missed X", "why not include X", "search for X", or a concrete project URL/name indicate that the ResearcherAgent failed to search broadly enough. Extract the named candidates, source URLs, and suggested query angles separately from item-specific quality critique.

## 3. Plan Improvements

Create an improvement plan before editing files. Classify each item:

- `prompt-only`: edits only `src/discovery_forge/instructions/researcher.md`
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
- If feedback includes explicit instructions like "include/list/search for X" or "exclude Y", the plan must contain a direct corresponding action item. It may also include a generalized rule, but it must not drop the concrete example.
- If a single feedback note contains both item-quality feedback and "should also include/list/search for X", split it into two plan items: one item-specific quality issue and one search coverage / missed-candidate issue.
- For missed-candidate feedback, include the exact project names/URLs in the plan and add or revise Query Example Pool entries so future runs can rediscover similar systems.
- Prompt-only changes may only edit `src/discovery_forge/instructions/*.md`.
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

- Use the existing feedback-improvement design in `src/discovery_forge/tools/improvement.py` when appropriate.
- Edit only instruction markdown under `src/discovery_forge/instructions/`.
- Preserve prompt publishing through Weave `StringPrompt` objects.

For code changes:

- Write or update a focused test first.
- Prefer small schema or review-output changes before larger orchestration changes.
- Keep changes focused on agent behavior or agent-facing review output, not dataset/scorer mechanics.
