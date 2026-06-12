# Verdict Quality Dataset — v4 (2026-06-12)

Resolves the v3 `needs_review` neutral rows with human-confirmed verdicts.

- Published ref: `weave:///wandb-smle/discovery-forge/object/verdict_quality_dataset:acx7n19ZeYniGNb1XNn4C8O61BcOEp4sdR7qlK7JmS8`
- Source rows: `verdict_quality_dataset_v4_2026-06-12.jsonl`
- Built on v3 (57 rows); only the 7 neutral rows were finalized.

## Neutral verdicts (human-confirmed)
| candidate | v3 (provisional) | v4 (confirmed) | basis |
| --- | --- | --- | --- |
| elophanto | accepted | accepted | modify/measure/keep metric loop; metadata gap is a limitation |
| safla | accepted | accepted | claims task->eval->feedback->improve loop |
| agentic-sprint | accepted | accepted | plan->implement->test->review loop |
| atropos | rejected | rejected | evaluation/RL-environment infrastructure, not its own improvement system |
| claude-scholar | accepted | **rejected** | explicitly semi-automated; needs substantial human guidance |
| cyber-autoagent | accepted | **rejected** | autonomous task execution without a verified eval->improvement loop |
| swarmclaw | accepted | **rejected** | agent-swarm orchestration runtime; no verified self-improvement loop |

Reject rows had their descriptions rewritten to neutral factual statements; `annotation_source` provenance is unchanged on all rows.

## Distribution
- 57 rows: accepted 28 / rejected 29 (v3 was 31 / 26; 3 accepted -> rejected)

## Notes
- Human annotation results (QualitySelector) were not altered; only the eval gold label was finalized per rubric with the user's decisions.
- No `needs_review` rows remain.
