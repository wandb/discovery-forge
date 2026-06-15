# Skill-Based Prompt Improvement Plan for 2026-06-09

## Source

- Weave `research_run_<i>` traces from the 2026-06-09 daily run, reviewed in the `research_annotation` queue.
- Root call IDs resolved from that run, then queried directly through the Weave Python SDK / trace server API with `include_feedback=True`.
- Human annotations used as the primary quality signal:
  - `wandb.annotation.QualitySelector` (good / bad / neutral)
  - `wandb.annotation.QualityReviewer` (free-text reviewer notes)
- Runnable scorer feedback (`Research-quality-judge-scorer`, `Tool-category-judge`, `Quality-classifiers`) read as supporting evidence only, not as gold labels.
- Current `src/discovery_forge/agents/researcher.md` inspected.

## Feedback Summary

- `bad` annotations cluster on `wrong_accept`: the agent saved non-system artifacts as final findings when the primary source did not show the candidate's own task -> evaluation -> feedback/memory -> improvement loop.
- Reviewer notes repeatedly reject curated/awesome lists, topic/directory pages, memory-only components, context/evaluation infrastructure, and generic agent frameworks that should be used only as leads (for example `awesome-ai-auto-research`, `agentmemory`, `context-engineering-kit`, `GitHub Topics: self-improving`).
- `neutral` annotations mark infrastructure or human-guided candidates accepted with low confidence and weak primary-source loop evidence (for example `EloPhanto`, `opencrabs`).
- `good` annotations confirm that clear closed-loop systems are correctly accepted even with brief descriptions or missing metadata, so loop ownership — not metadata completeness — is the deciding signal.
- The agent does not consistently run targeted follow-up queries to verify evaluator, benchmark, feedback, memory, or improvement-policy mechanics before saving.

## Proposed Prompt Change

- Add an explicit closed-loop evidence gate before accepting a final finding.
- Reject curated/awesome lists, topic/directory pages, and generic memory/runtime, framework, context, or evaluation/optimization infrastructure as final findings unless the source itself demonstrates a reusable closed-loop system.
- Require targeted follow-up verification after broad search, especially for the candidate's docs, repository internals, evaluator, benchmark, memory, feedback, and improvement policy.
- Separate scope verdict from metadata completeness: missing metadata can be recorded in `key_limitations`, but missing loop evidence should block acceptance.
- Require weak or incomplete loop evidence to be rejected or recorded as a limitation rather than turned into confident claims.
- Reinforce the ban on invented URLs, citations, dates, paper IDs, capabilities, and benchmark claims.

## Applied Files

- `src/discovery_forge/agents/researcher.md`
- `src/discovery_forge/agents/improve_history/2026-06-09/applied.md`

## Out of Scope

- No dataset, scorer, annotation, registry, orchestrator, or search backend changes.
- No fallback behavior.
- No changes to daily run outputs.
