# Skill-Based Prompt Improvement Plan for 2026-06-12

## Source
- Weave traces and feedback queried directly through the Weave Python SDK/API
- 5 human annotations inspected from 2026-06-09 run (call IDs: 019eac82-e1e0, 019eac83-17b9, 019eac84-5fed, 019eac84-9291, 019eac85-1ddd)
- No runnable scorer feedback present on these traces
- Current `researcher.md` inspected (prompt hash: d88e7c3eebab)

## Feedback Summary
- 2/5 rated "good": PraisonAI ("getting lots of attention"), OpenTracy ("looks practical") — both were correctly identified practical, popular projects with real feedback loops.
- 2/5 rated "neutral": ARIS ("Contains some Chinese content"), agentmemory ("interesting") — neither bad nor particularly useful.
- 1/5 rated "bad": EvalView ("reinventing the wheel") — agent accepted a regression testing tool that merely reimplements common evaluation functionality without novel differentiation.

### Concrete Signals
1. **Novelty gap**: EvalView was accepted despite being a straightforward reimplementation of existing evaluation/regression testing (e.g., Weave evaluations, pytest). The agent lacks guidance to assess whether a tool brings novel value vs. reinventing mature functionality.
2. **Language/localization blind spot**: ARIS contains significant Chinese-language content. The agent did not note this as a limitation, even though it affects discoverability and usability.
3. **Snippet-only evidence**: All 5 profiles show "GitHub metadata could not be fetched" and most metadata fields are "unknown." While partly an infrastructure issue, the agent is accepting tools on snippet-level evidence despite the prompt saying "Do not rely on snippet-only evidence."
4. **Positive signal**: The "good" rated traces (PraisonAI, OpenTracy) were correctly scoped — both had real iteration/feedback loops described. This validates the current scope criteria.

## Proposed Prompt Change
1. Add a **novelty/originality filter** to the "What To Look For" section: reject tools that merely reinvent well-known functionality (evaluation dashboards, basic testing frameworks) without meaningful differentiation.
2. Add guidance to note **primary documentation language** in `key_limitations` when it is not English.
3. Strengthen the **snippet-only evidence** guard: if GitHub metadata cannot be fetched and only search snippets are available, require at least one verified primary-source page (README, docs, blog post) before accepting.

## Applied Files
- `src/discovery_forge/agents/researcher.md`

## Out of Scope
- No changes to evaluation datasets, scorers, or Python code
- GitHub metadata fetch infrastructure issues (may need separate investigation)
- No changes to schema, orchestrator, or CLI
