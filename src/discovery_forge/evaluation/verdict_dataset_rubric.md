# Verdict Quality Dataset Rubric

`verdict_quality_dataset` rows are human-reviewed teaching examples for **scope accept/reject** decisions. The scorer checks only `expected_scope_status` against the agent's observed `scope_status`.

## Scope Question

Given a fixed candidate (name, URL, description), should `ResearcherAgent` **accept** it as an in-scope experiment-automation / self-improving system, or **reject** it as out of scope?

Judge the **candidate itself**, not a better alternative discovered during search.

## Accept (`expected_scope_status = accepted`)

Accept when primary-source evidence shows the candidate **runs** a closed loop:

1. **Task** — the system performs a concrete automated task (research, coding, experiment, optimization, etc.).
2. **Evaluation** — outcomes are measured with tests, metrics, benchmarks, judges, CI results, or another explicit success signal.
3. **Feedback / state** — results, traces, memory, logs, or artifacts are preserved across attempts.
4. **Improvement action** — a later attempt revises code, prompts, policy, configuration, skills, or another artifact based on that feedback.

Examples that fit when the loop is concrete in primary sources:

- autonomous research pipelines that run experiments and revise based on results
- edit → evaluate → iterate runners (for example `autoresearch-cli`, `autocrucible`)
- agent training / evolution frameworks where evaluation and update are built into the system (`AgentEvolver`, `LLaMEA`)
- evaluation-heavy research suites when the candidate itself orchestrates experiment iteration (`ARES`)

Frameworks can be accepted **only when** the candidate's own docs/repo show it implements the loop, not merely enables others to build agents.

## Reject (`expected_scope_status = rejected`)

Reject when the candidate is primarily one of:

- curated list, awesome list, topic/directory page, survey, paper roundup
- cookbook, guide, tutorial, educational course, or example page
- generic agent/workflow framework, GUI/computer-use framework, or orchestration toolkit without a demonstrated built-in loop
- memory-only or evaluation-only infrastructure/component without its own improvement loop
- duplicate of an already-known registry tool (use `duplicate_known_tool`)
- primary evidence too weak to confirm the loop (snippet-only, marketing language, unverified repo)

Use `expected_issue_category` to document the reject bucket:

- `out_of_scope` — wrong artifact type or insufficient loop evidence
- `missing_url` — no confirmable primary URL for the candidate (rare; do not use for metadata gaps when a URL exists)
- `duplicate_known_tool` — already represented in the registry

## Metadata vs Scope

Missing stars, license, `page_published_at`, or failed GitHub metadata fetch are **profile limitations**, not automatic scope rejects.

- If the loop is clear from primary sources, keep `accepted` and note metadata gaps in `label_reason` as limitations.
- If the loop cannot be verified because evidence is snippet-only or primary sources fail, reject with `out_of_scope` (weak evidence), not `missing_url`.

## Row Input Hygiene

- `input_candidate_description` must stay **neutral** and must not leak the gold verdict (for example embedding reject rationale or describing an awesome list as if it were the system itself).
- The description must still carry enough **neutral factual evidence** to support the verdict from the row input alone. A description with only `Autonomy: X Domains: ...` is too sparse: accept and reject rows then look identical, forcing the agent to rely on live search and adding run-to-run variance.
- Describe the candidate's actual artifact type and, for accepted rows, its concrete loop (task, evaluation, feedback/state, improvement action) factually — without stating the verdict.
- `label_reason` is for humans reviewing the dataset; the scorer does not read it.
- `annotation_source` provenance should be preserved when relabeling.

## Audit Actions

When reviewing a published dataset version:

- `keep` — label and inputs already match the rubric
- `relabel` — change `expected_scope_status`, `expected_issue_category`, and/or `label_reason`
- `drop` — remove rows that cannot be made neutral or unambiguous (none required for the 2026-06-12 cleanup)
- `needs_review` — defer when evidence is inconclusive (resolve before publish)
