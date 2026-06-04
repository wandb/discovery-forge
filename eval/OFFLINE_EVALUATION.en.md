# Offline Evaluation Guide

This document explains how to build, publish, run, and interpret offline evaluations for `ResearcherAgent`.

The hands-on scenario does not start with a complete gold dataset. First, run the daily researcher. Then humans review results in a Weave Annotation Queue. Once enough annotations exist, promote a subset of that review evidence into fixed eval datasets. After prompt or scope-rule changes, rerun the same datasets to check regressions.

## Why There Are Two Evaluations

This project evaluates two separate questions.

**Verdict Quality Eval** checks whether the agent makes the right accept/reject decision when a candidate is already given. The main risk is accepting curated lists, cookbooks, generic frameworks, or memory-only components that should be rejected.

**Discovery Quality Eval** checks whether an accepted finding discovered by the agent is actually a good discovery. This is hard to evaluate with a fixed gold answer because the agent may find a new tool that is better than the tools we already know. For this task, accepted-result quality is more useful than recall.

## Dataset Files

The local datasets live under `eval/`.

- `eval/researcher_verdict_dataset.jsonl`
- `eval/researcher_discovery_precision.jsonl`

The `eval/` directory is ignored by git. For reproducible hands-on runs, publish datasets to Weave and use the versioned refs.

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
uv run discovery-forge eval run-researcher \
  --dataset-ref 'weave:///wandb-smle/discovery-forge/object/researcher_verdict_dataset:<version>' \
  --output-dir eval_runs/verdict \
  --limit 5
```

Publish:

```bash
uv run discovery-forge eval publish-dataset \
  --dataset eval/researcher_verdict_dataset.jsonl \
  --name researcher_verdict_dataset
```

## Discovery Quality Eval

Discovery quality eval asks: is the accepted finding returned for this search brief a good discovery?

`ResearcherAgent` currently returns one item per eval row. To evaluate 100 results, use 100 different search briefs. This dataset does not contain gold tool answers. Instead, it fixes the search task and uses an LLM-as-judge scorer to rate the accepted finding as `good`, `neutral`, or `bad`.

Current topics:

- autonomous coding
- autonomous research
- self-improving agents
- recursive improvement
- evaluation loops
- agent memory
- long-running agent workflows
- self-correction
- autonomous experimentation

`DiscoveryQualityJudge` is responsible only for quality judgment. Whether the agent saved an accepted profile should be read from the predict output's `scope_status`, not from the judge metrics.

- `quality_score`: quality of the accepted finding. `good=1.0`, `neutral=0.5`, `bad=0.0`
- `bad_accept`: whether the accepted finding is bad according to the judge

The row-level `rating`, `reason`, and `failure_modes` are kept for debugging, but the core judge metrics in the summary are `quality_score` and `bad_accept`.

Why strict/lenient metrics are not logged separately:

- Strict success can be computed as `quality_score == 1.0`.
- Lenient success can be computed as `quality_score >= 0.5`.
- Bad accept can also be computed as `quality_score == 0.0`, but it is kept as a separate boolean because it is the most important risk signal.
- If you need acceptance rate, aggregate the predict output's `scope_status`; do not read it from `DiscoveryQualityJudge`.

Improvement guidance:

- If the `scope_status=accepted` rate is low, the agent may be failing to find candidates or rejecting/no-new too often. Inspect search query generation, source selection, and whether the scope filter is too conservative.
- If `quality_score` is low, the agent is accepting weak findings. Improve primary-doc verification, improvement-loop evidence requirements, and metadata extraction.
- If `quality_score` is near `0.5` and `bad_accept` is low, most results are neutral. This usually means evidence is weak or the result is a borderline framework, not a severe scope failure.
- If `bad_accept` is high, fix it first. Curated lists, cookbooks, topic pages, generic frameworks, or memory-only infrastructure are entering the feed as accepted items.

Run:

```bash
uv run discovery-forge eval run-discovery \
  --dataset-ref 'weave:///wandb-smle/discovery-forge/object/researcher_discovery_precision_dataset:<version>' \
  --output-dir eval_runs/discovery \
  --limit 5
```

Publish:

```bash
uv run discovery-forge eval publish-dataset \
  --dataset eval/researcher_discovery_precision.jsonl \
  --name researcher_discovery_precision_dataset
```

## Recommended Workflow

1. Run a daily briefing.
2. Review `research_run_<i>` traces in the `research_annotation` queue.
3. Build the verdict dataset only from `research_annotation` human labels.
4. Keep the discovery dataset as hand-written diverse search briefs.
5. Publish datasets to Weave.
6. Rerun the same dataset refs before and after prompt changes.
7. Compare verdict quality and discovery quality in Weave Evaluation.

## Guardrails

- Do not use automated scorer outputs as gold labels.
- Do not mix annotations from outside the `research_annotation` queue into the verdict dataset.
- Do not put gold tool answers into the discovery dataset.
- Do not quietly change datasets or scorers to make a prompt look better.
