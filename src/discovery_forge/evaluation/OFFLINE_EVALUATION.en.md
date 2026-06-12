# Offline Evaluation Guide

This document explains how to build, publish, run, and interpret offline evaluations for `ResearcherAgent`.

The hands-on scenario does not start with a complete gold dataset. First, run the daily researcher. Then humans review results in a Weave Annotation Queue. Once enough annotations exist, promote a subset of that review evidence into fixed eval datasets. After prompt or scope-rule changes, rerun the same datasets to check regressions.

## Evaluation Target

**Verdict Quality Eval** checks whether the agent makes the right accept/reject decision when a candidate is already given. The main risk is accepting curated lists, cookbooks, generic frameworks, or memory-only components that should be rejected.

## Dataset Files

The evaluation datasets are managed as **versioned Weave Datasets**.

- `verdict_quality_dataset`

`evaluate.py` loads the pinned published refs from `evaluation/datasets.py` by default, so it evaluates the published versions with no arguments. To create a new version, re-publish reviewed rows with `publish_eval_dataset(...)` and update the refs in `datasets.py`.

## Verdict Quality Eval

Verdict eval asks: should this candidate be accepted or rejected? Each row is a fixed candidate. `ResearcherAgent` receives the candidate name, URL, and description, then makes a scope/profile decision.

Important row fields:

- `id`: eval row id
- `input_tool_name`: candidate name
- `input_candidate_url`: candidate URL
- `input_candidate_description`: candidate description
- `expected_scope_status`: `accepted` or `rejected`
- `expected_issue_category`: expected rejection category, such as `out_of_scope`, `missing_url`, or `duplicate_known_tool`
- `label_reason`: human label rationale
- `annotation_source`: provenance for the Weave annotation that produced the label

The current verdict dataset uses only human annotations from the `research_annotation` queue. Automated scorer feedback is not used as a gold label.

The detailed accept/reject labeling standard, metadata-vs-scope handling, and row input hygiene rules live in [`verdict_dataset_rubric.md`](./verdict_dataset_rubric.md).

Scorer interpretation:

- `verdict_quality_scorer.is_correct`: whether the observed `scope_status` matches `expected_scope_status`.

Decision rule:

- If expected is `accepted` and observed is `accepted`, it is correct.
- If expected is `rejected` and observed is `rejected`, it is correct.
- If expected and observed differ, it is incorrect.

Improvement guidance:

- If `verdict_quality_scorer.is_correct` is low, the accept/reject criteria are unstable. Improve the scope definition, rejection rules for curated lists/cookbooks/generic frameworks, and primary-source requirements.
- This eval does not judge profile metadata, sources, or rejected reason quality. Split that into a separate profile/output quality eval if needed.

Run:

```bash
uv run python evaluate.py --limit 5
```

To publish a new version, use `publish_eval_dataset(rows_path, name="verdict_quality_dataset")` and update `VERDICT_DATASET_REF` in `datasets.py`.

## Recommended Workflow

1. Run a daily briefing.
2. Review `research_run_<i>` traces in the `research_annotation` queue.
3. Build the verdict dataset only from `research_annotation` human labels.
4. Publish datasets to Weave.
5. Rerun the same dataset refs before and after prompt changes.
6. Compare verdict quality in Weave Evaluation.

## Guardrails

- Do not use automated scorer outputs as gold labels.
- Do not mix annotations from outside the `research_annotation` queue into the verdict dataset.
- Do not quietly change datasets or scorers to make a prompt look better.
