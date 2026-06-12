---
name: offline-eval-improvement
description: Guides coding agents through prompt improvement for discovery-forge using W&B Weave offline evaluation results, failed eval rows, and verdict_quality_scorer evidence. Use when the user asks to improve researcher.md from Verdict Quality Eval results, compare offline eval runs, or raise verdict_quality_dataset performance.
---

# Offline Eval Improvement

Use this skill when improving `src/discovery_forge/agents/researcher.md` from Weave Evaluation evidence rather than daily annotation queues.

The coding agent inspects an evaluation run, analyzes failed rows, writes a plan, backs up the current prompt, edits the local prompt, validates the change, reruns the same pinned dataset, and reports the before/after result.

## Before You Start

Read the official W&B Skills guidance for the surfaces involved:

- Install if needed: `npx skills add wandb/skills`
- Local weave skill references when present:
  - `~/.claude/skills/weave/SKILL.md`
  - `~/.claude/skills/weave/references/evaluation.md`
  - `~/.claude/skills/weave/references/datasets.md`
  - `~/.claude/skills/weave/references/prompts.md`
- Upstream source: https://github.com/wandb/skills

Do not use W&B MCP tools in this workflow. Fetch evaluation evidence directly through the Weave Python SDK/trace server API.

## Default Project

- Entity: read from `.env` as `WANDB_ENTITY` (required; use your own W&B entity)
- Project: read from `.env` as `WANDB_PROJECT` (required; `.env.example` uses `discovery-forge`)
- API key: read from `.env` as `WANDB_API_KEY` (required)
- Prompt file: `src/discovery_forge/agents/researcher.md`
- Prompt backups: `src/discovery_forge/agents/researcher_backup_<N>.md`
- Evaluation entrypoint: `uv run python evaluate.py`
- Pinned verdict dataset: `src/discovery_forge/evaluation/datasets.py` `VERDICT_DATASET_REF`
- Improvement history: `src/discovery_forge/agents/improve_history/<YYYY-MM-DD-HHMM-offline-eval>/plan.md` and `src/discovery_forge/agents/improve_history/<YYYY-MM-DD-HHMM-offline-eval>/applied.md`
- Primary metric: `verdict_quality_scorer.is_correct.true_fraction`

## Change Budget

Control how **aggressively** the prompt may change in one iteration.

If the user does not specify otherwise, treat the change budget as **`medium`** — a moderate, focused edit covering one or two related clusters, paired with accept-protection. On a small, partly search-dependent eval, a single tiny edit's effect (~2-3 rows) can sit inside the run-to-run noise band (~±2-3 rows), so `low` steps need multiple-run averaging to read; `high` moves fastest but is harder to trace. `medium` is the default balance. Use `low` for smaller, more traceable steps or `high` for a one-pass rewrite when the user asks.

| Change budget | Edit posture | Scope this iteration |
| --- | --- | --- |
| `low` | Conservative. Prefer a few bullets or a short clarification inside an existing section. | One failure cluster only. |
| `medium` (default) | Moderate. One focused subsection or a small combination of related edits. | Up to two related clusters. |
| `high` | Broad. A full policy block (for example a complete verdict gate) is allowed in one pass. | Multiple clusters together. |

When making a broad edit, pair every new reject rule with an explicit accept-protection clause (for example "missing metadata is a profile limitation, not a scope failure") so that tightening one cluster does not push correctly-accepted rows into false rejects.

### Rules

- At the default `medium` budget, cover one or two related failure clusters in a focused edit; keep every change **policy-level** (artifact types, loop evidence, output discipline), not candidate-specific cheats.
- Pair reject rules with accept-protection so tightening one cluster does not create false rejects elsewhere.
- After each iteration, rerun `evaluate.py`. Because a single run varies by ~±2-3 rows, rerun 2-3 times (or compare per-row stability) before trusting a change. If the metric regresses across runs, revert to the backup and retry.
- Do not hardcode dataset row IDs or candidate names as a lookup table in the prompt.
- At `low`/`medium`, record in `plan.md` what you are **not** changing this iteration so the next pass has a clear queue.

### Prompt-edit guardrails

These keep edits general (no cherry-picking specific candidates) while avoiding the common regression where tightening rejects silently destroys correct accepts:

- Express policy as **distinctions** the candidate either meets or not (artifact type, observable behavior, what it revises). Avoid rules keyed on **evidence completeness** — clauses that say "reject if the loop is missing, implied, weak, unverified, or not fully proven" fire on genuine positives too, because real in-scope systems often have incomplete primary sources. They cause broad false rejects.
- A reject rule should describe **what kind of thing** is out of scope, not **how much proof** you happened to find this session. Missing/limited evidence is a profile limitation to record, not a reject trigger.
- Do not add a clause that contradicts an existing accept-protection clause. If a new sentence and an existing one disagree (e.g. "accept loop runners even with thin metadata" vs "reject if evidence is implied"), the model follows the stricter one and the protection is lost. Resolve the conflict instead of stacking both.
- Every iteration, check **both** error directions on the rerun: count new false rejects (accepted→rejected) as well as fixed false accepts. A change that fixes one cluster but flips several correct accepts is a net regression even if it "sounds stricter".
- Before keeping an edit, ask: would this sentence change the verdict on candidates I did not intend to touch? If yes, it is too broad — narrow it to the targeted artifact type or behavior.

### Failure clusters to cover

A broad (`high`) edit should address these together; smaller budgets take them one at a time:

1. Wrong artifact type (survey, cookbook, guide, list-like sources)
2. Adjacent infrastructure (memory-only, testing gate, repo-automation host, generic framework)
3. Weak-evidence or over-strict edge cases (protect correctly-accepted loop runners)

### Plan `Change Budget` section

Add this block to every `plan.md`:

```markdown
## Change Budget
- Change budget: medium (default) | low | high
- Edit posture: <e.g. broad — full Candidate Verdict Mode with reject rules + accept protection>
- Target cluster this iteration: <one pattern + example candidates>
- Deferred to next iteration: <remaining failure patterns>
```

## Evidence Workflow

1. Identify the target Weave Evaluation run from a Weave link, eval call ID, or the latest `evaluate.py` console output.
2. If no evaluation run exists yet, run the baseline once with the pinned dataset:

   ```bash
   uv run python evaluate.py
   ```

3. Query the parent evaluation call with `CallsFilter(call_ids=[eval_call_id])`.
4. Query child row calls with `CallsFilter(parent_ids=[eval_call_id])`.
5. Pull only the fields needed for diagnosis: row inputs, `expected_scope_status`, output `scope_status`, `verdict_reason`, `final_output`, scorer outputs, call status, and prompt ref/hash metadata when present.
6. Filter to rows where `verdict_quality_scorer.is_correct` is false. Keep a small sample of passing rows only when needed to avoid changing behavior that already works.
7. Group failures into prompt-policy patterns:
   - expected `rejected`, observed `accepted`: scope filter is too permissive.
   - expected `accepted`, observed `rejected`: scope filter is too strict or treats metadata weakness as scope failure.
   - observed `unknown`: agent failed to call either save tool; improve the decision/output discipline.
8. Read the current `researcher.md`.
9. Write `src/discovery_forge/agents/improve_history/<YYYY-MM-DD-HHMM-offline-eval>/plan.md` before editing. Use the local execution start time for the directory name, for example `2026-06-12-1505-offline-eval`. If the file already exists for that improvement loop, update it instead of creating a new call-ID directory.
10. Before editing, preserve the current prompt as `src/discovery_forge/agents/researcher_backup_<N>.md`, where `<N>` is the next available integer starting from `0`.

### Query Evaluation Rows With Weave SDK

Follow W&B Skills guidance and query Weave directly. Do not add discovery-forge helper wrappers for call queries.

```python
import weave
from weave.trace_server.trace_server_interface import CallsFilter, CallsQueryReq

from discovery_forge.observability import weave_project_path

eval_call_id = "<eval-call-id>"

client = weave.init(weave_project_path())

parent = client.server.calls_query(
    CallsQueryReq(
        project_id=client.project_id,
        filter=CallsFilter(call_ids=[eval_call_id]),
        limit=1,
    )
)

children = client.server.calls_query(
    CallsQueryReq(
        project_id=client.project_id,
        filter=CallsFilter(parent_ids=[eval_call_id]),
        limit=100,
    )
)

for call in children.calls:
    output = call.output or {}
    scores = output.get("scores") or output.get("scorer_outputs") or {}
    print(call.id, call.display_name, scores)
```

The exact shape of `call.output` can vary by Weave version. Inspect one child row first, then extract the smallest stable set of fields needed to identify failed verdict rows.

## Plan Format

Use this structure:

```markdown
# Offline Eval Prompt Improvement Plan for <YYYY-MM-DD-HHMM-offline-eval>

## Source
- Weave Evaluation parent call: <eval-call-id or link>
- Dataset ref: <pinned verdict dataset ref>
- Baseline metric: `verdict_quality_scorer.is_correct` = <value>
- Failed rows inspected: <n>
- Current `researcher.md` inspected

## Change Budget
- Change budget: medium
- Edit posture: <how broad the prompt edit will be>
- Clusters covered this iteration: <patterns>
- Deferred to next iteration: <remaining patterns, if any>

## Failure Summary
- <concrete failure pattern with candidate examples>

## Proposed Prompt Change
- <exact behavior change>

## Expected Effect
- <which failure patterns should improve and which passing behavior must stay stable>

## Applied Files
- `src/discovery_forge/agents/researcher.md`

## Out of Scope
- Dataset rows, labels, scorer logic, evaluation runner, registry, schemas, and search backend behavior are not changed.
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

During development, evaluate the local `researcher.md` file directly. Do not pass `--researcher-prompt-ref` and do not publish the prompt between iterations.

For each iteration:

1. Unless the user asks otherwise, use the default change budget `medium`: a focused edit covering one or two related clusters with paired accept-protection.
2. Create the next backup file.
3. Apply the policy-level edit for the targeted clusters.
4. Run focused validation.
5. Run `uv run python evaluate.py` 2-3 times (single-run variance is ~±2-3 rows).
6. Keep the change only if the pinned dataset metric improves across runs without unacceptable row-level regressions.
7. If correctly-accepted rows flipped to rejected, strengthen the accept-protection clause and rerun.

## Validation

Run focused validation:

```bash
uv run pytest tests/unit/test_researcher.py -q
```

Then rerun the same pinned dataset:

```bash
uv run python evaluate.py
```

## Report Back

Report:

- change budget used and edit posture
- targeted failure cluster and deferred patterns
- evaluation run inspected
- dataset ref used
- baseline `verdict_quality_scorer.is_correct`
- number of failed rows inspected
- failure patterns found
- prompt changes made
- both error directions after rerun: false accepts fixed AND any new false rejects introduced
- backup file created
- tests run
- rerun `verdict_quality_scorer.is_correct`
- remaining failed patterns or dataset/scorer maintenance notes
