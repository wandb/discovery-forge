# Offline Profiler Evaluation Improvement

Use this workflow when improving ProfilerAgent behavior from a Weave Evaluation run rather than newly added annotations. The usual user input is a Weave evaluation link; treat that link as the primary evidence source.

This workflow is currently **Profiler-only**. Do not add or run Discovery evaluation unless the user explicitly asks for a new Discovery evaluation design.

The evaluation dataset, audit sidecar, and scorers are **read-only evidence** in this workflow. Do not change dataset rows, labels, dedup logic, scorer logic, or evaluation runner behavior. Improvements must target ProfilerAgent behavior only.

## 1. Start From The Evaluation Link

When the user provides a Weave evaluation URL, inspect that exact evaluation first. Do not rerun the evaluation before understanding the failures.

Default project:

- Entity: `wandb-smle`
- Project: `autoresearch-researcher`

Evidence priority:

1. User-provided Weave evaluation link.
2. The evaluation parent call and its summary.
3. Child evaluation rows under that parent call.
4. The dataset object/version used by that evaluation.
5. Local audit sidecar only when the row needs provenance not present in Weave.

Use W&B/Weave MCP tools when available:

- Read the MCP tool schema before calling any tool.
- First query the parent evaluation call from the URL/call id.
- Then query child traces with `parent_ids` set to the evaluation call id.
- Pull only needed columns first: inputs, output, scorer outputs, display name, status.
- Limit initial child rows to failed scorer rows or a small sample, then broaden only if needed.

If the URL points to a child row, resolve its root/parent evaluation first, then inspect siblings only under that evaluation.

## 2. Understand The Read-Only Dataset Contract

Default dataset:

- Dataset object: `profiler-eval-dataset`
- Current dataset ref: `daily_runs/weave-profiler-annotation-eval/profiler_eval_dataset_refs.json`
- Local minimal dataset: `daily_runs/weave-profiler-annotation-eval/profiler_eval_dataset_minimal.jsonl`
- Audit sidecar: `daily_runs/weave-profiler-annotation-eval/profiler_eval_dataset_audit.jsonl`

The minimal profiler dataset should contain only scorer/model inputs:

- `input_tool_name`
- `input_candidate_url`
- `input_candidate_description`
- `expected_scope_status`
- `expected_issue_category`

Keep provenance out of the Weave evaluation dataset. Store it in the audit sidecar instead:

- original annotation call IDs
- feedback IDs
- review notes
- original profiler status/rejection reason
- dedupe provenance

Do not edit these files during offline profiler improvement. If a row appears wrong, report it as a dataset-maintenance follow-up instead of changing the dataset.

## 3. Inspect Or Rerun The Profiler Evaluation

If no evaluation link is provided, run the current profiler dataset:

```bash
uv run autoresearch-researcher eval run-profiler \
  --dataset-ref "$(python - <<'PY'
import json
print(json.load(open('daily_runs/weave-profiler-annotation-eval/profiler_eval_dataset_refs.json'))['profiler-eval-dataset'])
PY
)" \
  --output-dir eval_runs/profiler-<date> \
  --search-backend serper
```

Evaluation code lives in `src/autoresearch_researcher/tools/evaluation.py`.

Implementation constraints:

- `eval run-profiler` must reuse the supplied Weave dataset object when `--dataset-ref` is provided.
- Do not create throwaway dataset objects such as `profiler-eval-run-dataset`.
- Local JSONL evaluation may pass plain row lists to `weave.Evaluation`, but should not publish a new dataset unless explicitly requested.
- Keep `weave.init()` centralized through the CLI/orchestrator path.
- Do not modify `src/autoresearch_researcher/tools/evaluation.py` or scorer behavior in this workflow.

## 4. Interpret Evaluation Failures

Primary scorer:

- `scope_decision_scorer`: checks whether Profiler returned `accepted` or `rejected` as expected.

Secondary scorer:

- `profile_quality_scorer`: checks accepted profile completeness and rejected-profile reason quality.

When summarizing results, report:

- evaluation trace URL
- evaluation call id
- dataset ref/version
- total rows evaluated
- `scope_decision_scorer.passed` count/fraction
- `profile_quality_scorer.passed` count/fraction
- examples that failed scope decision
- examples that passed scope but failed quality

Failure interpretation rules:

- If `expected_scope_status == rejected` and Profiler accepts, this is usually a profiler scope-policy issue.
- If `expected_scope_status == accepted` and Profiler rejects due to missing metadata, keep scope verdict separate from metadata completeness.
- If scope is correct but profile quality fails, improve ProfilerAgent metadata extraction/source behavior rather than changing scorer requirements.
- If the dataset row looks wrong, report it as a dataset review item. Do not change dataset/audit evidence in this workflow.

### Failure Investigation Checklist

For each failing row, capture:

- row input: `input_tool_name`, `input_candidate_url`, `input_candidate_description`
- expected labels: `expected_scope_status`, `expected_issue_category`
- model output: observed `scope_status`, rejection reason, or saved profile fields
- scorer outputs: which scorer failed and why
- whether failure is due to Profiler behavior, dataset label, scorer logic, or flaky external search
- relevant audit sidecar row if provenance is needed

Do not infer a different expected label from model output alone. The offline dataset is the regression contract for this workflow. Dataset/scorer issues should be reported, not fixed here.

## 5. Plan Offline Improvements

Create a short plan before edits. Each item should include:

- failing eval row/tool name
- expected vs observed scope status
- relevant scorer failure
- audit-sidecar evidence when needed
- target files
- whether the fix is prompt-only or profiler-agent code
- validation command, usually rerunning the same profiler evaluation

Offline profiler improvements may target only:

- `src/autoresearch_researcher/instructions/profiler.md` for prompt/scope wording
- `src/autoresearch_researcher/agents/profiler.py` only when prompt/scorer changes are insufficient

Do not target:

- `src/autoresearch_researcher/tools/evaluation.py`
- local `eval/` dataset-generation utilities
- `daily_runs/weave-profiler-annotation-eval/*.jsonl`
- Weave dataset versions or scorer definitions

## 6. Execute And Rerun

For offline profiler work:

1. Apply the smallest ProfilerAgent prompt or agent-code change.
2. Run focused unit tests.
3. Rerun the same `profiler-eval-dataset` evaluation.
4. Compare before/after scorer summaries against the user-provided evaluation link.

Do not replace the dataset or adjust scorers to make the score look better. If audit evidence shows a row is mislabeled, duplicated, or malformed, report it as a dataset-maintenance follow-up outside this workflow.

## Validation

Use the smallest meaningful validation:

- `uv run pytest tests/unit/test_us4_profiler.py -v` for ProfilerAgent behavior changes
- `uv run pytest tests/unit/test_profiler_evaluation.py -v` only to confirm the unchanged evaluation runner still works
- `uv run autoresearch-researcher eval run-profiler --dataset-ref <profiler-eval-dataset-ref> --output-dir eval_runs/profiler-<date>` for behavior changes
