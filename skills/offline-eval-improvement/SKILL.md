---
name: offline-eval-improvement
description: Guides coding agents through Discovery Forge prompt improvement from a specified Weave offline evaluation baseline. Use `wandb-primary` to fetch evaluation results, failed eval rows, dataset refs, prompt refs, and scorer evidence, then use this workflow when improving researcher.md from failed evaluation rows, comparing eval runs, or iterating on a fixed dataset.
---

# Offline Eval Improvement

Use this skill when improving `src/discovery_forge/agents/researcher.md` from Weave Evaluation evidence fetched with the `wandb-primary` skill rather than daily annotation queues.

The coding agent starts from explicit experiment inputs, inspects the baseline evaluation run, analyzes failed rows, writes a plan, backs up the starting prompt, edits the local prompt, validates the change, reruns the same dataset, and reports the before/after result for each iteration.

## Before You Start

Follow `AGENTS.md` setup first, then select and use the installed `wandb-primary` skill for Weave evaluation, dataset, trace, and scorer evidence. This skill only defines the Discovery Forge offline-eval improvement workflow.

Fetch all evaluation evidence live from Weave through `wandb-primary` skill guidance, including its Weave SDK / W&B API patterns. Do not use W&B MCP tools, and do not add discovery-forge query wrappers.

## Required Inputs

Ask for or infer these inputs before editing. First check `src/discovery_forge/evaluation/evaluation_config.yaml` and use its `offline_eval_improvement` values when present. If any input is still missing and cannot be inferred from the user's request or latest `evaluate.py` output, stop and ask for it.

- Dataset: a configured dataset key such as `verdict_quality`, or a full published Weave Dataset ref.
- Start prompt: the local prompt file to improve, or a Weave `StringPrompt` ref to inspect as the starting baseline. Default local file is `src/discovery_forge/agents/researcher.md`.
- Baseline evaluation ID: the Weave Evaluation parent call ID or URL that represents the score to beat.
- Max iterations: maximum number of prompt edit + eval cycles to run before reporting back.

Keep these inputs visible in every plan and report so workshop participants can see which dataset, prompt, baseline, and iteration budget they are using.

## Default Project

- Entity: read from `.env` as `WANDB_ENTITY` (required; use your own W&B entity)
- Project: read from `.env` as `WANDB_PROJECT` (required; `.env.example` uses `discovery-forge`)
- API key: read from `.env` as `WANDB_API_KEY` (required)
- Prompt file: `src/discovery_forge/agents/researcher.md`
- Prompt backups: `src/discovery_forge/agents/researcher_backup_<N>.md`
- Evaluation entrypoint: `uv run python evaluate.py`
- Evaluation config: `src/discovery_forge/evaluation/evaluation_config.yaml`
- Improvement history: `src/discovery_forge/agents/improve_history/<YYYY-MM-DD-HHMM-offline-eval>/plan.md` and `src/discovery_forge/agents/improve_history/<YYYY-MM-DD-HHMM-offline-eval>/applied.md`
- Primary metric: `verdict_quality_scorer.is_correct.true_fraction`

## Prompt Edit Scope

Each improvement iteration should make a focused, policy-level prompt edit that covers one or two related failure clusters. Pair every new reject rule with an explicit accept-protection clause (for example "missing metadata is a profile limitation, not a scope failure") so that tightening one cluster does not push correctly-accepted rows into false rejects.

### Rules

- Cover one or two related failure clusters in a focused edit; keep every change **policy-level** (artifact types, loop evidence, output discipline), not candidate-specific cheats.
- Pair reject rules with accept-protection so tightening one cluster does not create false rejects elsewhere.
- After each iteration, rerun `evaluate.py`. Because a single run varies by ~±2-3 rows, rerun 2-3 times (or compare per-row stability) before trusting a change. If the metric regresses across runs, revert to the backup and retry.
- Do not hardcode dataset row IDs or candidate names as a lookup table in the prompt.
- Record in `plan.md` what you are **not** changing this iteration so the next pass has a clear queue.

### Prompt-edit guardrails

These keep edits general (no cherry-picking specific candidates) while avoiding the common regression where tightening rejects silently destroys correct accepts:

- Express policy as **distinctions** the candidate either meets or not (artifact type, observable behavior, what it revises). Avoid rules keyed on **evidence completeness** — clauses that say "reject if the loop is missing, implied, weak, unverified, or not fully proven" fire on genuine positives too, because real in-scope systems often have incomplete primary sources. They cause broad false rejects.
- A reject rule should describe **what kind of thing** is out of scope, not **how much proof** you happened to find this session. Missing/limited evidence is a profile limitation to record, not a reject trigger.
- Do not add a clause that contradicts an existing accept-protection clause. If a new sentence and an existing one disagree (e.g. "accept loop runners even with thin metadata" vs "reject if evidence is implied"), the model follows the stricter one and the protection is lost. Resolve the conflict instead of stacking both.
- Every iteration, check **both** error directions on the rerun: count new false rejects (accepted→rejected) as well as fixed false accepts. A change that fixes one cluster but flips several correct accepts is a net regression even if it "sounds stricter".
- Before keeping an edit, ask: would this sentence change the verdict on candidates I did not intend to touch? If yes, it is too broad — narrow it to the targeted artifact type or behavior.

### Common Failure Clusters

1. Wrong artifact type (survey, cookbook, guide, list-like sources)
2. Adjacent infrastructure (memory-only, testing gate, repo-automation host, generic framework)
3. Weak-evidence or over-strict edge cases (protect correctly-accepted loop runners)

## Evidence Workflow

1. Record the required inputs: dataset, start prompt, baseline evaluation ID, and max iterations.
2. Resolve the dataset:
   - If the user gave a dataset key, read `src/discovery_forge/evaluation/evaluation_config.yaml` and use that key's `ref`.
   - If the config defines `offline_eval_improvement.dataset_key`, use that key unless the user supplied a different one.
   - If the user gave a full Weave Dataset ref, use it directly for this loop.
3. Resolve the start prompt:
   - If the config defines `offline_eval_improvement.start_prompt`, use that path unless the user supplied a different prompt.
   - If the user gave a local path, read that file and treat it as the editable prompt.
   - If the user gave a Weave `StringPrompt` ref, inspect it through `wandb-primary`, then decide with the user whether to copy its content into the local editable prompt.
   - If unspecified, use `src/discovery_forge/agents/researcher.md`.
4. Resolve max iterations from the user's request or `offline_eval_improvement.max_iterations`.
5. Inspect the baseline Weave Evaluation parent call from the given call ID or URL. If `offline_eval_improvement.baseline_evaluation_id` is set, use that as the default baseline.
6. If no baseline evaluation run exists yet, run one with the selected dataset and start prompt, then use that new parent call as the baseline:

   ```bash
   uv run python evaluate.py --verdict-dataset-key '<dataset-key>'
   # or: uv run python evaluate.py --verdict-dataset-ref '<dataset-ref>'
   ```

7. Use the `wandb-primary` skill to inspect the parent evaluation call.
8. Use the `wandb-primary` skill to inspect the child row calls.
9. Pull only the fields needed for diagnosis: row inputs, expected labels, model output, scorer outputs, call status, and prompt ref/hash metadata when present. For the current verdict eval, include `expected_scope_status`, output `scope_status`, `verdict_reason`, `final_output`, and `verdict_quality_scorer.is_correct`.
10. Filter to rows where the primary scorer failed. Keep a small sample of passing rows only when needed to avoid changing behavior that already works.
11. Group failures into prompt-policy patterns. For verdict eval:
   - expected `rejected`, observed `accepted`: scope filter is too permissive.
   - expected `accepted`, observed `rejected`: scope filter is too strict or treats metadata weakness as scope failure.
   - observed `unknown`: agent failed to call either save tool; improve the decision/output discipline.
12. Read the local prompt that will be edited.
13. Write `src/discovery_forge/agents/improve_history/<YYYY-MM-DD-HHMM-offline-eval>/plan.md` before editing. Use the local execution start time for the directory name, for example `2026-06-12-1505-offline-eval`. If the file already exists for that improvement loop, update it instead of creating a new call-ID directory.
14. Before editing, preserve the current prompt as `src/discovery_forge/agents/researcher_backup_<N>.md`, where `<N>` is the next available integer starting from `0`.

### Evaluation Evidence Selection

Use the `wandb-primary` skill to fetch and inspect Weave Evaluation evidence. This skill only defines which Discovery Forge evidence matters:

- Parent evaluation call: the exact eval call ID or link under analysis.
- Child row calls: the dataset-row-level evaluation results under that parent.
- Dataset row inputs: candidate name, candidate URL, description, and `expected_scope_status`.
- Model output: `scope_status`, `verdict_reason`, and `final_output`.
- Scorer output: `verdict_quality_scorer.is_correct` and any supporting scorer detail.
- Prompt metadata: prompt ref/hash when present.

Inspect one child row first to learn the shape, then extract the smallest stable set of fields needed to identify failed verdict rows.

## Plan Format

Use this structure:

```markdown
# Offline Eval Prompt Improvement Plan for <YYYY-MM-DD-HHMM-offline-eval>

## Source
- Dataset: <dataset key or full ref>
- Dataset ref: <resolved published Weave Dataset ref>
- Start prompt: <local path or Weave StringPrompt ref>
- Baseline Weave Evaluation parent call: <eval-call-id or link>
- Baseline metric: `verdict_quality_scorer.is_correct` = <value>
- Max iterations: <n>
- Current iteration: <i>/<n>
- Failed rows inspected: <n>
- Current `researcher.md` inspected

## Prompt Edit Scope
- Target clusters this iteration: <one or two related failure patterns>
- Accept-protection: <passing behavior that must stay stable>
- Deferred patterns: <remaining failure patterns, if any>

## Failure Summary
- <concrete failure pattern with candidate examples>

## Proposed Prompt Change
- <exact behavior change>

## Expected Effect
- <which failure patterns should improve and which passing behavior must stay stable>

## Applied Files
- `src/discovery_forge/agents/researcher.md`

## Out of Scope
- Dataset rows, labels, scorer logic, evaluation runner, registry, schemas, and search backend behavior are not changed during prompt iteration.
```

## Apply Rules

- Prompt-only changes may edit only `src/discovery_forge/agents/researcher.md`.
- This is a development workflow: do not publish `researcher.md` to Weave during improvement iterations unless the user explicitly asks.
- Before each prompt edit, create the next backup file: `researcher_backup_0.md`, then `researcher_backup_1.md`, and so on. Never overwrite an existing backup.
- Do not change evaluation datasets, labels, scorers, or `evaluate.py` to make results look better.
- Do not create fallback behavior.
- Keep scope verdict separate from metadata completeness.
- If primary sources prove the task -> evaluator -> feedback/memory -> improvement loop but metadata is incomplete, record the weakness in `key_limitations` instead of rejecting solely for metadata incompleteness.
- If `expected_scope_status == accepted` and the agent rejects due to missing metadata, treat the prompt as over-strict unless the dataset row appears wrong.
- If `expected_scope_status == rejected` and the agent accepts, treat it as a scope-policy issue unless the dataset row appears wrong.
- If a dataset row, label, or scorer appears wrong, report it as dataset/scorer maintenance rather than editing those artifacts in this workflow.
- Use failed candidate names as policy examples in the plan. Do not hardcode them as required outputs.

After editing, write `src/discovery_forge/agents/improve_history/<YYYY-MM-DD-HHMM-offline-eval>/applied.md`. If the file already exists for that improvement loop, update it with the latest applied summary.

## Local Prompt Iteration

During development, evaluate the local prompt file directly. Do not pass `--researcher-prompt-ref` and do not publish the prompt between iterations unless the user explicitly asks to compare a published prompt ref.

Run no more than the requested max iterations. Stop early if the primary metric improves enough for the user's goal, if the remaining failures are dataset/scorer maintenance issues, or if two consecutive focused edits regress the baseline.

For each iteration:

1. Update `plan.md` with the current iteration number, selected dataset ref, start prompt, baseline eval ID, target cluster, and deferred patterns.
2. Create the next backup file.
3. Make a focused edit covering one or two related clusters with paired accept-protection.
4. Run focused validation.
5. Run the same selected dataset:

   ```bash
   uv run python evaluate.py --verdict-dataset-key '<dataset-key>'
   # or: uv run python evaluate.py --verdict-dataset-ref '<dataset-ref>'
   ```

6. Compare the new run against the baseline evaluation ID and the previous iteration.
7. Keep the change only if the selected dataset metric improves across runs without unacceptable row-level regressions. Because a single run varies by ~±2-3 rows, rerun 2-3 times or compare per-row stability before trusting a borderline change.
8. If correctly-accepted rows flipped to rejected, strengthen the accept-protection clause and rerun within the max-iteration budget.
9. If the metric regresses across runs, revert to the backup and either try the next focused cluster or stop and report the regression.

## Validation

Run focused validation:

```bash
uv run pytest tests/unit/test_researcher.py -q
```

Then rerun the same selected dataset:

```bash
uv run python evaluate.py --verdict-dataset-key '<dataset-key>'
# or: uv run python evaluate.py --verdict-dataset-ref '<dataset-ref>'
```

## Report Back

Report:

- dataset key/ref used
- start prompt path/ref
- baseline evaluation ID
- max iterations requested and iterations completed
- targeted failure cluster and deferred patterns
- baseline `verdict_quality_scorer.is_correct`
- number of failed rows inspected
- failure patterns found
- prompt changes made
- both error directions after rerun: false accepts fixed AND any new false rejects introduced
- backup file created
- tests run
- rerun evaluation ID(s) and `verdict_quality_scorer.is_correct`
- remaining failed patterns or dataset/scorer maintenance notes
