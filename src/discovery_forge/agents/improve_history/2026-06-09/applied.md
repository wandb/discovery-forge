# Skill-Based Prompt Improvement Applied for 2026-06-09

## Source Inspected

- Weave `research_run_<i>` traces from the 2026-06-09 daily run, reviewed in the `research_annotation` queue.
- Root call feedback queried directly through the Weave Python SDK / trace server API with `include_feedback=True`.
- Human annotations used as the primary quality signal:
  - `wandb.annotation.QualitySelector` (good / bad / neutral)
  - `wandb.annotation.QualityReviewer` (reviewer notes)
- Runnable scorer feedback (`Research-quality-judge-scorer`, `Tool-category-judge`, `Quality-classifiers`) read as supporting evidence only.

## Feedback Signals Used

- `bad` annotations where accepted candidates lacked inspectable primary evidence of a task -> evaluation -> feedback/memory -> improvement loop.
- Reviewer notes rejecting curated/awesome lists, topic/directory pages, memory-only components, context/evaluation infrastructure, and generic agent frameworks as standalone findings.
- `neutral` annotations on infrastructure or human-guided candidates accepted with weak loop evidence.
- `good` annotations confirming brief-but-real closed-loop systems are correct accepts, keeping scope verdict separate from metadata completeness.

## Prompt Changes Applied

- Added an explicit closed-loop accept gate that lists three required loop elements before a finding is saved:
  - performed task or workflow
  - evaluator, benchmark, verifier, test, reward, or other success signal
  - preserved feedback, memory, traces, state, or results across attempts
- Kept the concrete improvement action / next-run behavior change as an explicit understanding question and as an acceptance check in "How To Work", so weak loops without it are not accepted.
- Added final-finding rejection guidance for curated/awesome lists, GitHub topic/directory pages, and coding-agent memory/runtime layers, enterprise agent frameworks, context-engineering kits, and evaluation/optimization platforms without their own visible loop; treat such sources as leads.
- Required targeted follow-up searches for candidate-specific docs, repository internals, evaluator, benchmark, memory, feedback, and improvement policy before saving.
- Clarified that weak, metadata-only, suspicious, or inconsistent loop evidence should be rejected or recorded in `key_limitations`, not turned into a confident acceptance, and that orchestration/memory/evaluation/testing/context/optimization infrastructure is a lead unless its own loop is shown.
- Clarified that metadata completeness and scope verdict are separate.
- Reinforced that the agent must not invent URLs, paper IDs, citations, dates, capabilities, benchmark claims, evaluator details, or policy-update mechanics.

## Prompt Version

- Local content hash: `4ecae102c1c5` (sha256 of `researcher.md`, first 12 chars).
- Not published to Weave from this hands-on branch. Publish during the exercise with `publish_instruction_prompts(...)` and record the printed `researcher_instructions` ref and hash here.

## Validation

- `uv run pytest tests/unit/test_researcher.py -q`: 23 passed.
- IDE diagnostics checked for edited files: no linter errors found.

## Out of Scope

- No dataset, scorer, annotation, registry, orchestrator, search backend, or fallback changes.
- No changes to daily run outputs.
