# Applied Prompt Improvement — 2026-06-12

## Changes Applied to `src/discovery_forge/agents/researcher.md`

### 1. Novelty/originality filter (line 15)
Added rejection criterion for tools that merely reinvent well-known, mature functionality without meaningful differentiation. Addresses the "reinventing the wheel" feedback on EvalView (QualitySelector: bad).

### 2. Stronger snippet-only evidence guard (line 63)
Strengthened the primary-source verification requirement: if GitHub metadata cannot be fetched and only search snippets are available, the agent must verify at least one primary-source page before accepting. Otherwise, reject and explain. Addresses the pattern where all 5 annotated traces had "GitHub metadata could not be fetched" yet were still accepted.

### 3. Documentation language note (line 80)
Added instruction to note non-English primary documentation language in `key_limitations`. Addresses the "Contains some Chinese content" feedback on ARIS (QualitySelector: neutral).

## Weave Prompt Ref
- Ref: `weave:///agent-lab/autoresearch-researcher-test/object/researcher_instructions:G4PKV4lqZMY1YJXdXrOv8rcppbGJwMuE3BbAuaUGh44`
- Hash: `02e239d4e722`
- Previous hash: `d88e7c3eebab` (2026-06-09 run)

## Validation
- `uv run pytest tests/unit/test_researcher.py -q` — 23 passed
- `uv run ruff check .` — all checks passed
