# Offline Evaluation Improvement

Use this workflow when improving ResearcherAgent behavior from a Weave Evaluation run rather than newly added annotations. The usual user input is a Weave evaluation link; treat that link as the primary evidence source.

The evaluation targets the ResearcherAgent's scope/profile decision. Do not add or run a separate discovery evaluation; the single agent does discovery + profiling in one run.

The evaluation dataset, audit sidecar, and scorers are **read-only evidence** in this workflow. Do not change dataset rows, labels, dedup logic, scorer logic, or evaluation runner behavior. Improvements must target ResearcherAgent behavior only.

## 1. Start From The Evaluation Link

When the user provides a Weave evaluation URL, inspect that exact evaluation first. Do not rerun the evaluation before understanding the failures.

Default project:

- Entity: `wandb-smle`
- Project: `discovery-forge`

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

The minimal evaluation dataset should contain only scorer/model inputs:

- `input_tool_name`
- `input_candidate_url`
- `input_candidate_description`
- `expected_scope_status`
- `expected_issue_category`

Keep provenance out of the Weave evaluation dataset. Store it in an audit sidecar instead:

- original annotation call IDs
- feedback IDs
- review notes
- original scope status/rejection reason
- dedupe provenance

Do not edit these files during offline improvement. If a row appears wrong, report it as a dataset-maintenance follow-up instead of changing the dataset.

## 3. Inspect Or Rerun The Researcher Evaluation

If no evaluation link is provided, run the evaluation dataset:

```bash
uv run discovery-forge eval run-researcher \
  --dataset-path <dataset.jsonl> \
  --output-dir eval_runs/researcher-<date> \
  --search-backend serper
```

`--dataset-ref <weave-dataset-ref>` may be used instead of `--dataset-path` to reuse a published Weave dataset object.

Evaluation code lives in `src/discovery_forge/tools/evaluation.py`.

Implementation constraints:

- `eval run-researcher` must reuse the supplied Weave dataset object when `--dataset-ref` is provided.
- Local JSONL evaluation may pass plain row lists to `weave.Evaluation`, but should not publish a new dataset unless explicitly requested.
- Keep `weave.init()` centralized through the CLI/orchestrator path.
- Do not modify `src/discovery_forge/tools/evaluation.py` or scorer behavior in this workflow.

## 4. Interpret Evaluation Failures

Primary scorer:

- `verdict_quality_scorer`: checks whether the agent returned `accepted` or `rejected` as expected.

When summarizing results, report:

- evaluation trace URL
- evaluation call id
- dataset ref/version
- total rows evaluated
- `verdict_quality_scorer.is_correct` count/fraction
- examples that failed verdict quality

Failure interpretation rules:

- If `expected_scope_status == rejected` and the agent accepts, this is usually a scope-policy issue.
- If `expected_scope_status == accepted` and the agent rejects due to missing metadata, keep scope verdict separate from metadata completeness.
- If the dataset row looks wrong, report it as a dataset review item. Do not change dataset/audit evidence in this workflow.

### Failure Investigation Checklist

For each failing row, capture:

- row input: `input_tool_name`, `input_candidate_url`, `input_candidate_description`
- expected labels: `expected_scope_status`, `expected_issue_category`
- model output: observed `scope_status`, rejection reason, or saved profile fields
- scorer outputs: which scorer failed and why
- whether failure is due to agent behavior, dataset label, scorer logic, or flaky external search
- relevant audit sidecar row if provenance is needed

Do not infer a different expected label from model output alone. The offline dataset is the regression contract for this workflow. Dataset/scorer issues should be reported, not fixed here.

## 5. Plan Offline Improvements

Create a short plan before edits. Each item should include:

- failing eval row/tool name
- expected vs observed scope status
- relevant scorer failure
- audit-sidecar evidence when needed
- target files
- whether the fix is prompt-only or agent code
- validation command, usually rerunning the same evaluation

Offline improvements may target only:

- `src/discovery_forge/instructions/researcher.md` for prompt/scope wording
- `src/discovery_forge/agents/researcher.py` only when prompt/scorer changes are insufficient

Do not target:

- `src/discovery_forge/tools/evaluation.py`
- local dataset-generation utilities
- Weave dataset versions or scorer definitions

## 6. Execute And Rerun

For offline work:

1. Apply the smallest ResearcherAgent prompt or agent-code change.
2. Run focused unit tests.
3. Rerun the same evaluation dataset.
4. Compare before/after scorer summaries against the user-provided evaluation link.

Do not replace the dataset or adjust scorers to make the score look better. If audit evidence shows a row is mislabeled, duplicated, or malformed, report it as a dataset-maintenance follow-up outside this workflow.

## Validation

Use the smallest meaningful validation:

- `uv run pytest tests/unit/test_researcher.py -v` for ResearcherAgent behavior changes
- `uv run pytest tests/unit/test_profiler_evaluation.py -v` only to confirm the unchanged evaluation runner still works
- `uv run discovery-forge eval run-researcher --dataset-path <dataset.jsonl> --output-dir eval_runs/researcher-<date>` for behavior changes
