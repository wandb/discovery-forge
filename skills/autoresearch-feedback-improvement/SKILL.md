---
name: autoresearch-feedback-improvement
description: Guides coding agents through feedback-driven improvement for autoresearch-researcher using either live Weave annotations or offline Weave Evaluation results. Use when improving the single ResearcherAgent prompt or behavior from review evidence; offline evaluation evidence is read-only and should drive agent changes, not dataset or scorer changes.
disable-model-invocation: true
---

# Autoresearch Feedback Improvement

Use this skill when improving the autoresearch pipeline from human review evidence. First choose the workflow, then read the matching reference file.

## Choose The Workflow

- **Online annotation improvement**: use fresh human annotations attached to live Weave calls. Read `online-annotation-improvement.md`.
- **Offline evaluation improvement**: use a Weave evaluation link or `eval run-researcher` results to improve ResearcherAgent behavior. Read `offline-evaluation-improvement.md`.

Do not mix workflows unless the user explicitly asks. Online annotations are review evidence from production-like traces; offline evaluation is regression evidence from a fixed dataset.

## Shared Rules

- Keep `weave.init()` centralized in the orchestrator/CLI path.
- Do not create fallback behavior.
- Keep scope verdict separate from metadata completeness.
- Preserve the single ResearcherAgent pipeline (discover + profile in one agent run per tool) unless the user explicitly asks to redesign it.
- For Weave SDK or evaluation details, consult the official W&B skill/docs before changing code.

## Reporting

When done, report:

- workflow used: online annotation or offline evaluation
- evidence inspected: annotations or evaluation trace/dataset
- improvement plan executed
- prompt changes made
- code changes made
- tests run
- offline eval before/after metrics when applicable
- remaining risks or review queue items
