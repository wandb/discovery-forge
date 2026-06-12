# Verdict Quality Dataset — v3 Merged Build (2026-06-12)

Built with `skills/build-verdict-dataset`. **Published** as `verdict_quality_dataset` v3.

- Published ref: `weave:///wandb-smle/discovery-forge/object/verdict_quality_dataset:l7bAmqq5z4QzJjsZGfNgTgdGirUDCxwQ2X8Xebg0y6M`
- `VERDICT_DATASET_REF` updated to this digest.
- Source rows: `verdict_quality_dataset_merged_2026-06-12.jsonl`

## Sources
- v2 published dataset: `weave:///wandb-smle/discovery-forge/object/verdict_quality_dataset:u1iTLYhRMuP46r0aDHevyTYpC2ts7QG5ihPLAPUgYfQ` (30 rows, kept verbatim)
- Current Weave `research_annotation` queue: 37 annotated `research_*` calls (1 `No new finding` skipped → 36 candidate rows)
- Rubric: `src/discovery_forge/evaluation/verdict_dataset_rubric.md`

## Result
- Merged rows: **57** (accepted 31 / rejected 26)
- v2 rows kept: 30 (v2 wins on the 9 overlapping ids; labels already agreed)
- New-only rows added from annotations: 27
- Output: `verdict_quality_dataset_merged_2026-06-12.jsonl`

## Label mapping from annotations
- `QualitySelector=good` → `accepted`
- `QualitySelector=bad` → `rejected` / `out_of_scope`
- `QualitySelector=neutral` → adjudicated per rubric using the `QualityReviewer` rationale (below)
- Human annotation results were not changed; `annotation_source` preserves `queue_name`, `call_id`, `quality_selector`.

## Neutral adjudication (reviewer-based)
| candidate | decision | reason |
| --- | --- | --- |
| long-running-claude-for-scientific-computing | rejected | Anthropic research writeup, not a reusable standalone tool (lead only) |
| automated-weak-to-strong-researcher | rejected | Anthropic blog/writeup, not a reusable tool |
| atropos | rejected | Framework for running/evaluating LLM trajectories — eval/RL-env infrastructure, not its own improvement system |
| elophanto | accepted (needs_review) | modify/measure/keep metric loop; evidence thin |
| safla | accepted (needs_review) | feedback-loop/self-learning claimed; not fully verified |
| agentic-sprint | accepted (needs_review) | spec-driven self-iterative sprint loop; small footprint |
| swarmclaw | accepted (needs_review) | agent-swarm runtime with loops; eval mechanics unverified |
| claude-scholar | accepted (needs_review) | research pipeline but explicitly semi-automated |
| cyber-autoagent | accepted (needs_review) | autonomous iterative pentest; eval/improvement mechanics unclear |

## Input hygiene applied to new rows
- Reject-by-type rows rewritten to neutral factual descriptions (no leaked verdict): awesome lists (`awesome-agent-harness`, `awesome-harness-engineering`, `awesome-ai-agents-tools-resources-and-projects`), cookbook (`build-an-agent-improvement-loop-...-codex`), engineering/blog writeups (`anthropic-multi-agent-research-system`, `long-running-claude-...`, `automated-weak-to-strong-researcher`), memory-only (`agentmemory`), infra (`atropos`), and `aidevops` / `agent-reliability-engineering`.
- Accepted rows keep the neutral "Scope Decision" text plus `Autonomy`/`Domains`.

## Overlap check vs v2 (9 ids)
All 9 overlapping ids had identical labels in the annotation build and v2, so v2 rows were kept unchanged.

## Improvement cycle that validated this version
- Baseline prompt (`researcher_backup_8.md`) on v3: 37/57 = 0.649 (eval `019ebb12-9a03-75ef-b968-0f4c5debeaf3`)
- After high-budget Candidate Verdict Mode: 47/57 = 0.825 (eval `019ebb14-c09f-7fd8-a15e-52d2b9791a96`)
- +10 rows, clearly above the per-run noise band, so v3 was published.

## Open items (still provisional)
- The 7 `needs_review` neutrals remain provisional and were published as-is per user direction: `elophanto`, `claude-scholar`, `cyber-autoagent`, `atropos`, `safla`, `agentic-sprint`, `swarmclaw`. Confirm with a human pass when convenient.
- Optional: primary-source verification pass on new thin-evidence accepted rows.
