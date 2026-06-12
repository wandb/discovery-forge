# Verdict Quality Dataset Audit v2 (2026-06-12)

Second reliability pass focused on rows whose label or input could not be judged from the row input alone, verified against primary sources.

## Source
- Previous dataset ref: `weave:///wandb-smle/discovery-forge/object/verdict_quality_dataset:wMxZIqDPm5g6TjPuScNBkaaqPSTDZbYX5mfRWAUDHdc`
- Published v2 dataset ref: `weave:///wandb-smle/discovery-forge/object/verdict_quality_dataset:u1iTLYhRMuP46r0aDHevyTYpC2ts7QG5ihPLAPUgYfQ`
- Rubric: `src/discovery_forge/evaluation/verdict_dataset_rubric.md`
- Clean rows: `verdict_quality_dataset_clean_2026-06-12-v2.jsonl`

## Root-cause finding
Several rows had `input_candidate_description` values that did not carry enough neutral evidence to support the verdict (e.g. `Autonomy: Scientist Domains: ...` only). Accepted and rejected rows with such sparse inputs are indistinguishable from the row input, so the agent must rely on live search, which adds run-to-run variance and caps achievable accuracy. This pass corrects the clearest cases against primary sources.

## Changes
- Actions: relabel=1, input-hygiene=1, needs_review=1, keep=27
- Distribution: accepted=15, rejected=15

### `autokernel` — relabel `rejected` -> `accepted`
- Prior v1 cleanup flipped this to `rejected` for "sparse/unverified evidence".
- Primary sources reviewed: arXiv `2603.21331`, repo README (`rightnow-ai/autokernel`), MarkTechPost, Medium.
- All show a concrete loop: profile model -> edit single `kernel.py` -> fixed 5-stage correctness + performance benchmark -> keep/revert via git -> repeat 300-400 experiments.
- This satisfies the rubric accept loop (task, evaluation, feedback/state, improvement action). The recurring "false accept" was actually the correct verdict.
- Input description rewritten to neutrally state the loop so the verdict is inferable from the row.

### `self-evolving-agents` — keep `rejected`, neutralize input
- Primary source: arXiv `2507.21046`, repo `CharlesQ9/Self-Evolving-Agents` is a survey/paper-collection repo with a taxonomy, not a runnable system.
- Label `rejected` / `out_of_scope` is correct, but the v1 input read like an accept.
- Input rewritten to factually describe it as a survey repository (same precedent as the v1 `awesome-autoresearch` fix).

### `dexter` — needs_review (no label change)
- Autonomous deep-research agent; primary-source evidence for a built-in improvement loop is thin from available sources.
- Kept `rejected` but flagged `needs_review` in `label_reason` for a future primary-source pass.

## Verification
- `VERDICT_DATASET_REF` updated in `src/discovery_forge/evaluation/datasets.py`
- Unit tests: `uv run pytest tests/unit/test_researcher_evaluation.py tests/unit/test_eval_datasets.py -q` (14 passed)
- v2 eval call (iter4 prompt): `019ebae6-ff0c-741a-81a5-256e6f83ba58`
- v2 metric: `verdict_quality_scorer.is_correct` = 23/30 = 0.7667
- `autokernel` and `self-evolving-agents` are now stably correct on v2.
- Remaining failures are all reject-rows accepted as in-scope (`agent-s`, `dexter`, `evalview`, `evolving-agents-toolkit-eat`, `fast-agent`, `github-agentic-workflows`, `memos`) — a prompt over-permissiveness issue plus run variance, not a dataset-label issue.

## Notes
- No labels were changed to raise the score; `autokernel` was corrected on primary-source evidence and happens to align with what the agent already produced.
- The v1 ref is preserved; v2 is a new published version.
