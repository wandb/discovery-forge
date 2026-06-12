---
name: build-verdict-dataset
description: Guides coding agents through building the verdict_quality_dataset from W&B Weave research_annotation evidence — querying annotated research_run calls, mapping human QualitySelector verdicts to gold labels, refining row inputs per the rubric, and publishing a new versioned Weave Dataset. Use when the user asks to (re)generate the verdict dataset from annotations, seed a new eval dataset version, or rebuild verdict_quality_dataset.
---

# Build Verdict Dataset

Use this skill to create or refresh `verdict_quality_dataset` from human annotations in Weave, then publish it as a versioned Weave Dataset and pin the ref.

The coding agent queries annotated `research_run_<i>` calls, extracts candidate fields, maps the human verdict to a gold label, refines each row against the rubric, writes a local JSONL plus an audit report, publishes the dataset, and updates `VERDICT_DATASET_REF`.

This skill **does not change the human annotation results themselves**. It only transforms annotation evidence into a clean eval dataset and records provenance.

## Before You Start

Read the official W&B Skills guidance for the surfaces involved:

- Install if needed: `npx skills add wandb/skills`
- Local weave skill references when present:
  - `~/.claude/skills/weave/SKILL.md`
  - `~/.claude/skills/weave/references/feedback.md`
  - `~/.claude/skills/weave/references/datasets.md`
- Upstream source: https://github.com/wandb/skills

Do not use W&B MCP tools in this workflow. Fetch trace and feedback evidence directly through the Weave Python SDK/trace server API.

## Default Project

- Entity: read from `.env` as `WANDB_ENTITY` (required; use your own W&B entity)
- Project: read from `.env` as `WANDB_PROJECT` (required; `.env.example` uses `discovery-forge`)
- API key: read from `.env` as `WANDB_API_KEY` (required)
- Annotation queue: `research_annotation`
- Root trace unit: one `research_run_<i>` / `openai_agent_trace` call per reviewed candidate
- Dataset name: `verdict_quality_dataset`
- Pinned ref: `src/discovery_forge/evaluation/datasets.py` `VERDICT_DATASET_REF`
- Publish helper: `discovery_forge.evaluation.datasets.publish_eval_dataset`
- Labeling standard: `src/discovery_forge/evaluation/verdict_dataset_rubric.md`
- Local outputs: `src/discovery_forge/evaluation/datasets/verdict_quality_dataset_clean_<YYYY-MM-DD>.jsonl` and `verdict_quality_dataset_audit_<YYYY-MM-DD>.md`

## Row Schema

Each dataset row must contain:

- `id`: stable slug for the candidate (kebab-case of the tool name)
- `input_tool_name`: candidate name
- `input_candidate_url`: candidate primary URL
- `input_candidate_description`: neutral candidate description (see hygiene rules)
- `expected_scope_status`: `accepted` or `rejected` (the only field the scorer reads)
- `expected_issue_category`: for rejects, one of `out_of_scope`, `missing_url`, `duplicate_known_tool`; otherwise `null`
- `label_reason`: human-readable rationale (not scored)
- `annotation_source`: `{queue_name, call_id, quality_selector}` provenance — copy verbatim from the source annotation, never invent or alter

## Workflow

1. Identify the source scope: a day, a set of `research_run` call IDs, or "all reviewed items in `research_annotation`". Prefer an explicit run day or call-ID list over "every historical annotation".
2. Initialize Weave and query the annotated root calls with `include_feedback=True`.
3. For each call, separate human annotations (`wandb.annotation.QualitySelector`, `wandb.annotation.QualityReviewer`) from runnable scorer feedback. Use only `research_annotation` human annotations as the verdict seed; do not seed labels from runnable scorers.
4. Inspect one call first to learn the exact `output` shape, then extract the candidate name, primary URL, and a pre-verdict description plus the human reviewer's rationale.
5. Map the human `QualitySelector` to a draft gold label:
   - `Good` -> `accepted`
   - `Bad` -> `rejected`
   - `Neutral` -> **ask the user how to handle it.** Do not silently auto-assign. Present each neutral candidate with its `QualityReviewer` rationale and a recommended verdict (`accepted` with `key_limitations`, `rejected`, or `drop`), then let the user decide per row or give a blanket rule. Only fall back to a provisional label + `needs_review` flag if the user explicitly defers or says to proceed without them.
6. Refine each row against `verdict_dataset_rubric.md` (see Labeling and Hygiene). Record `keep` / `relabel` / `drop` / `needs_review` with a reason.
7. Write the clean JSONL and the audit report.
8. Publish the dataset and update `VERDICT_DATASET_REF`.
9. Validate.

### Query Annotated Calls With Weave SDK

Follow W&B Skills guidance and query Weave directly. Do not add discovery-forge helper wrappers for call queries.

```python
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(".env"))

import weave
from weave.trace_server.trace_server_interface import CallsFilter, CallsQueryReq

from discovery_forge.observability import weave_project_path

call_ids = ["<research_run_call_id>", "..."]  # or build from a day's _profile_runs.jsonl

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
    feedback = (call.summary or {}).get("weave", {}).get("feedback", [])
    annotations = [
        f for f in feedback
        if str(f.get("feedback_type", "")).startswith("wandb.annotation")
    ]
    print(call.id, call.display_name, len(annotations))
    print(call.output)
    for a in annotations:
        print(a.get("feedback_type"), a.get("payload"))
```

Read feedback from `call.summary["weave"]["feedback"]` (not `call.feedback`, which does not exist on `CallSchema`). Keep only annotations whose call belongs to the requested scope, and deduplicate by feedback ID.

## Labeling and Hygiene

Apply `verdict_dataset_rubric.md`. Key rules:

- **Accept** when the candidate itself runs a loop: task -> evaluation -> feedback/state -> revision of its own artifact.
- **Reject** lists/surveys/cookbooks/guides, GUI/computer-use frameworks, testing/evaluation-only gates, repository-automation hosts, memory-only components, generic frameworks, and weak-evidence candidates.
- **Metadata vs scope**: missing stars/license/dates/GitHub fetch is a profile limitation, not a scope reject. Do not encode metadata gaps as `missing_url` when a primary URL exists.
- **Input hygiene**: `input_candidate_description` must be neutral (no leaked verdict) but must carry enough factual evidence to support the verdict from the row input alone. A description with only `Autonomy: X Domains: ...` is too sparse — add the neutral artifact type and, for accepts, the concrete loop, verified against primary sources.
- **Verify with primary sources** before relabeling away from the human verdict. Record the source (repo, paper, docs) in the audit.

## Provenance Rules

- Never change the human annotation result. Copy `quality_selector` and the originating `call_id` verbatim into `annotation_source`.
- When you relabel `expected_scope_status` away from the raw `QualitySelector` mapping, keep the original `annotation_source` and explain the rubric-based reason in the audit. The provenance must still point to the same human annotation.
- Do not invent annotations, call IDs, URLs, or dates.

## Audit Report

Write `verdict_quality_dataset_audit_<YYYY-MM-DD>.md` with:

- Source scope (day / call IDs / queue) and the rubric path
- Row count and accepted/rejected distribution
- Per-row action table: `id | action (keep/relabel/drop/needs_review) | expected | issue | reason`
- Primary sources consulted for any relabel
- The published dataset ref after publishing

## Publish And Pin

```bash
uv run python - <<'PY'
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(".env")
import weave
from discovery_forge.observability import weave_project_path
from discovery_forge.evaluation.datasets import publish_eval_dataset, VERDICT_DATASET_NAME

weave.init(weave_project_path())
result = publish_eval_dataset(
    Path("src/discovery_forge/evaluation/datasets/verdict_quality_dataset_clean_<YYYY-MM-DD>.jsonl"),
    name=VERDICT_DATASET_NAME,
)
print(result)
PY
```

Then update `VERDICT_DATASET_REF` in `src/discovery_forge/evaluation/datasets.py` to the new digest. Preserve older versions; publish a new one rather than overwriting.

## Validation

```bash
uv run pytest tests/unit/test_eval_datasets.py tests/unit/test_researcher_evaluation.py -q
uv run python evaluate.py
```

Confirm the new ref resolves on the Weave server and that the eval links to `verdict_quality_dataset` (not an anonymous `Dataset`).

## Apply Rules

- Build the dataset from `research_annotation` human annotations only; do not seed labels from runnable scorers.
- For `Neutral` annotations, ask the user how to handle each one before finalizing. Do not silently auto-assign neutral verdicts; only use a provisional label with a `needs_review` flag if the user explicitly defers.
- Do not change the human annotation results; only transform and refine into eval rows.
- Do not tune labels or descriptions to make a specific prompt score higher. Refine for correctness and clarity per the rubric, and record every change in the audit.
- Keep the scorer, evaluation runner, and registry unchanged in this workflow.

## Report Back

Report:

- source scope (day / call IDs / queue) and number of annotations used
- row count and accepted/rejected distribution
- rows relabeled or dropped, with rubric reasons and primary sources
- published dataset ref and the updated `VERDICT_DATASET_REF`
- validation results (tests, eval run, ref resolves)
- rows left as `needs_review`
