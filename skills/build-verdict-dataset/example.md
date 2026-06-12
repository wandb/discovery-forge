# Example: Build Verdict Dataset From Annotations

This example builds `verdict_quality_dataset` from `research_annotation` evidence, refines rows against the rubric, and publishes a new versioned Weave Dataset.

## 1. Collect annotated calls

Read official W&B Skills guidance first (`npx skills add wandb/skills`), then query Weave directly.

```bash
uv run python - <<'PY'
import json
from dotenv import load_dotenv
load_dotenv(".env")
import weave
from weave.trace_server.trace_server_interface import CallsFilter, CallsQueryReq
from discovery_forge.observability import weave_project_path

call_ids = ["<research_run_call_id>", "..."]  # or build from daily_runs/<day>/_profile_runs.jsonl
client = weave.init(weave_project_path())
resp = client.server.calls_query(CallsQueryReq(
    project_id=client.project_id,
    filter=CallsFilter(call_ids=call_ids),
    include_feedback=True,
    limit=len(call_ids),
))
for call in resp.calls:
    anns = [f for f in (call.feedback or []) if str(f.get("feedback_type","")).startswith("wandb.annotation")]
    print(call.id, call.display_name)
    for a in anns:
        print("  ", a.get("feedback_type"), a.get("payload"))
PY
```

Inspect one call's `output` first to learn where the candidate name, primary URL, and description live.

## 2. Draft rows from the human verdict

Map each `QualitySelector` to a draft label, then build a row:

```json
{
  "id": "autokernel",
  "input_tool_name": "autokernel",
  "input_candidate_url": "https://github.com/rightnow-ai/autokernel",
  "input_candidate_description": "AutoKernel applies an autonomous agent loop to GPU kernel optimization: it profiles a PyTorch model, edits a kernel file, runs a fixed correctness+performance benchmark, and keeps or reverts each change across many iterations. Autonomy: Scientist Domains: autonomous coding, GPU kernel optimization, experiment automation",
  "expected_scope_status": "accepted",
  "expected_issue_category": null,
  "label_reason": "Primary sources (arXiv + repo README) show an edit -> benchmark -> keep/revert loop. Neutral annotation, verified in scope.",
  "annotation_source": {"queue_name": "research_annotation", "call_id": "019e8880-e12c-7c34-b01c-5c5a2ae1a195", "quality_selector": "Neutral"}
}
```

Mapping: `Good -> accepted`, `Bad -> rejected`. For `Neutral`, ask the user how to handle each one (show the `QualityReviewer` rationale and a recommended verdict); only fall back to a provisional label + `needs_review` if the user defers.

## 3. Refine against the rubric

For each row, decide `keep` / `relabel` / `drop` / `needs_review` using `verdict_dataset_rubric.md`:

- Remove leaked verdicts from descriptions (e.g. a reject row described as if it were the system itself).
- Add neutral artifact-type / loop evidence so the verdict is inferable from the row input.
- Keep metadata gaps out of the scope decision.
- Verify against primary sources before moving a label away from the human verdict; keep `annotation_source` unchanged.

## 4. Write JSONL + audit

- Rows: `src/discovery_forge/evaluation/datasets/verdict_quality_dataset_clean_<YYYY-MM-DD>.jsonl`
- Audit: `src/discovery_forge/evaluation/datasets/verdict_quality_dataset_audit_<YYYY-MM-DD>.md` with the per-row action table and primary sources.

## 5. Publish and pin

```bash
uv run python - <<'PY'
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(".env")
import weave
from discovery_forge.observability import weave_project_path
from discovery_forge.evaluation.datasets import publish_eval_dataset, VERDICT_DATASET_NAME

weave.init(weave_project_path())
print(publish_eval_dataset(
    Path("src/discovery_forge/evaluation/datasets/verdict_quality_dataset_clean_<YYYY-MM-DD>.jsonl"),
    name=VERDICT_DATASET_NAME,
))
PY
```

Update `VERDICT_DATASET_REF` in `src/discovery_forge/evaluation/datasets.py` to the printed digest.

## 6. Validate

```bash
uv run pytest tests/unit/test_eval_datasets.py tests/unit/test_researcher_evaluation.py -q
uv run python evaluate.py
```

Confirm the eval links to `verdict_quality_dataset` and the new ref resolves on the Weave server.

## What not to do

- Do not change the human annotation results; only transform them into rows.
- Do not seed labels from runnable scorer feedback.
- Do not tune labels/descriptions to raise a specific prompt's score.
- Do not invent annotations, call IDs, URLs, or dates.
