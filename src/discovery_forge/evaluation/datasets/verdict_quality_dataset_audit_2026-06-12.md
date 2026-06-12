# Verdict Quality Dataset Audit (2026-06-12)

## Source
- Previous dataset ref: `weave:///wandb-smle/discovery-forge/object/verdict_quality_dataset:wKeJK7YgjkBBVFE9LOEoMrD0Z7c0ngeCcXgv9qs4k6E`
- Published clean dataset ref: `weave:///wandb-smle/discovery-forge/object/verdict_quality_dataset:wMxZIqDPm5g6TjPuScNBkaaqPSTDZbYX5mfRWAUDHdc`
- Baseline eval call: `019eba70-25e4-7034-9466-c9cd3ad12c0c` (22/30 = 0.7333)
- Latest in-memory adapter eval call: `019ebaa2-8806-7774-a256-f0a493a7e2d5` (22/30 = 0.7333)
- Rubric: `src/discovery_forge/evaluation/verdict_dataset_rubric.md`

## Summary
- Rows reviewed: 30
- Actions: keep=21, relabel=9, drop=0, needs_review=0
- Clean distribution: accepted=14, rejected=16

## Verification
- `VERDICT_DATASET_REF` updated in `src/discovery_forge/evaluation/datasets.py`
- Unit tests: `uv run pytest tests/unit/test_researcher_evaluation.py tests/unit/test_eval_datasets.py -q` (14 passed)
- Clean-dataset baseline eval call: `019ebaaa-18b0-7789-87c8-632a8672e017`
- Clean-dataset baseline metric: `verdict_quality_scorer.is_correct` = 19/30 = 0.6333
- Note: score is not directly comparable to the pre-cleanup 22/30 baseline because labels and one row (`autokernel`) changed.

## Priority boundary rows
### `dexter` — Dexter
- Action: **relabel**
- Notes: URL exists; reject is for weak loop evidence, not missing_url. Aligns with ARES metadata rule.
- Label: `rejected` / `missing_url` -> `rejected` / `out_of_scope`

### `fast-agent` — fast-agent
- Action: **relabel**
- Notes: Removed metadata-missing wording from scope label_reason; kept generic-framework reject.
- Label status unchanged (`rejected`); updated human-readable fields

### `github-agentic-workflows` — GitHub Agentic Workflows
- Action: **relabel**
- Notes: Replaced annotation-only label_reason with scope rationale.
- Label status unchanged (`rejected`); updated human-readable fields

### `ares-agentic-research-and-evaluation-suite` — ARES (Agentic Research and Evaluation Suite)
- Action: **relabel**
- Notes: Clarified metadata-missing is profile limitation, not scope reject.
- Label status unchanged (`accepted`); updated human-readable fields

### `autoresearch-cli` — autoresearch-cli
- Action: **relabel**
- Notes: Clarified why weak long-horizon memory still fits accepted edit/eval loop.
- Label status unchanged (`accepted`); updated human-readable fields

### `autokernel` — autokernel
- Action: **relabel**
- Notes: Sparse/snippet evidence could not verify a built-in loop; aligned with rubric weak-evidence reject.
- Label: `accepted` / `None` -> `rejected` / `out_of_scope`

## All rows
| id | action | expected | issue | notes |
| --- | --- | --- | --- | --- |
| `agent-s` | keep | rejected | out_of_scope | Computer-use framework without built-in improvement loop. |
| `agentevolver` | keep | accepted | None | Self-evolving training framework with evaluation loop. |
| `ai-scientist-v3` | keep | accepted | None | Autonomous research pipeline with experiment execution. |
| `ares-agentic-research-and-evaluation-suite` | relabel | accepted | None | Clarified metadata-missing is profile limitation, not scope reject. |
| `auto-claude-code-research-in-sleep-aris` | keep | accepted | None | Autonomous idea-to-paper research loop. |
| `autocrucible` | keep | accepted | None | Explicit edit-evaluate-iterate platform. |
| `autokernel` | relabel | rejected | out_of_scope | Sparse/snippet evidence could not verify a built-in loop; aligned with rubric weak-evidence reject. |
| `autoresearch-cli` | relabel | accepted | None | Clarified why weak long-horizon memory still fits accepted edit/eval loop. |
| `autoresearch-for-agents` | keep | accepted | None | Adversarial optimization loop over measured outcomes. |
| `autoresearchclaw` | keep | accepted | None | Autonomous research pipeline. |
| `awesome-autoresearch` | relabel | rejected | out_of_scope | Fixed description leakage that described the awesome list as an autonomous research engine. |
| `awesome-code-as-agent-harness-papers` | keep | rejected | out_of_scope | Paper roundup / awesome list. |
| `awesome-memory-for-agents` | keep | rejected | out_of_scope | Curated memory paper list. |
| `continuous-claude` | keep | accepted | None | Iterative CI/PR coding workflow fits loop runner pattern. |
| `dexter` | relabel | rejected | out_of_scope | URL exists; reject is for weak loop evidence, not missing_url. Aligns with ARES metadata rule. |
| `evaluating-ai-agents` | keep | rejected | out_of_scope | Educational course, not an operational loop runner. |
| `evalview` | relabel | rejected | out_of_scope | Removed pagePublishedAt wording from scope label_reason. |
| `evoagentx` | keep | accepted | None | Concrete evolving-agent framework with evaluation loop in primary sources. |
| `evolving-agents-toolkit-eat` | keep | rejected | out_of_scope | High-level orchestration toolkit without demonstrated loop. |
| `fast-agent` | relabel | rejected | out_of_scope | Removed metadata-missing wording from scope label_reason; kept generic-framework reject. |
| `github-agentic-workflows` | relabel | rejected | out_of_scope | Replaced annotation-only label_reason with scope rationale. |
| `github-topics-self-improving` | keep | rejected | out_of_scope | Topic directory page. |
| `hermes-agent` | keep | accepted | None | Built-in learning loop described in primary snippets. |
| `how-to-ralph-wiggum` | keep | rejected | out_of_scope | Workflow guide/repo, not a reusable closed-loop system. |
| `inngest-self-learning-agent` | keep | accepted | None | Autonomous research workflow with execution and analysis loop. |
| `kaizen-agent` | relabel | accepted | None | Separated metadata note from scope decision in label_reason. |
| `llamea` | keep | accepted | None | Evolutionary benchmark loop is explicit. |
| `memos` | keep | rejected | out_of_scope | Memory infrastructure/component without standalone loop. |
| `self-evolving-agents` | keep | rejected | out_of_scope | Survey repository, not a tool. |
| `self-evolving-agents-a-cookbook-for-autonomous-agent-retraining` | keep | rejected | out_of_scope | Cookbook/example page, not a standalone system. |
