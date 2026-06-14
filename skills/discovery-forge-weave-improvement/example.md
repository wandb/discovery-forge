# Example: Skill-Based Prompt Improvement

This example uses the 2026-06-04 run.

## 1. Gather Root Call IDs

Read:

```bash
daily_runs/2026-06-04/_profile_runs.jsonl
```

Use the `weave_call_id` values for the root traces:

```text
019e92aa-b854-7a6d-be7b-c01ca0913376
019e92ab-0373-72ac-b032-a4f5e80c3f59
019e92ab-39c7-79e5-869e-aec90d403da7
019e92ab-703a-75ea-8783-eae435d687de
019e92ab-b1d4-78ba-bd34-aaf028243993
```

## 2. Query Weave Through the Python SDK

Read official W&B Skills guidance first (`npx skills add wandb/skills`), then query evidence directly through the Weave Python SDK/trace server API. Do not use W&B MCP or discovery-forge call-query helpers.

```bash
uv run python - <<'PY'
import json
from pathlib import Path

import weave
from weave.trace_server.trace_server_interface import CallsFilter, CallsQueryReq

from discovery_forge.observability import weave_project_path

day = "2026-06-04"
day_dir = Path("daily_runs") / day
call_ids = [
    json.loads(line)["weave_call_id"]
    for line in (day_dir / "_profile_runs.jsonl").read_text().splitlines()
    if line.strip() and json.loads(line).get("weave_call_id")
]

client = weave.init(weave_project_path())
response = client.server.calls_query(
    CallsQueryReq(
        project_id=client.project_id,
        filter=CallsFilter(call_ids=call_ids),
        include_feedback=True,
        limit=len(call_ids),
    )
)

for call in response.calls:
    print(call.id, call.display_name, len(call.feedback or []))
PY
```

This uses:

- `CallsQueryReq` with `CallsFilter(call_ids=...)`
- `include_feedback=true` on the call query
- `call.output`, `call.attributes`, `call.summary`, and `call.feedback` from the SDK response

## 3. Interpret Feedback

For 2026-06-04:

- Human reviewers marked OpenEvolve, auto-harness, CORAL, and EvoSkill as `Good`.
- Human reviewers marked SIA as `Neutral`.
- Runnable scorer feedback flagged EvoSkill with `missing_sources` / `unsupported_claims` because the profile contained a placeholder paper URL (`2605.XXXX`).

Conclusion:

- Do not over-reject valid GitHub projects when the improvement loop is visible.
- Do not save placeholder source URLs or fake paper IDs.
- Treat missing `paper_url` as metadata incompleteness, not scope failure, when primary repo/docs evidence proves the improvement loop.

## 4. Apply Prompt Change

Add prompt guidance such as:

```markdown
- Never invent placeholder source URLs. If a paper URL, arXiv ID, docs URL, or project URL is not exactly visible in a primary source, save it as `unknown` or `null` and explain the missing evidence in `key_limitations`.
- A missing or unverified `paper_url` is a metadata limitation, not a scope failure, when the GitHub repo or primary docs directly prove the repeated task -> evaluation -> feedback/memory -> improvement loop.
```

## 5. Validate

```bash
uv run pytest tests/unit/test_researcher.py -q
```

## 6. Publish Prompt

Publish with:

```bash
uv run python - <<'PY'
from discovery_forge.observability import init_observability
from discovery_forge.tools.prompts import publish_instruction_prompts, prompt_hashes, prompt_refs

init_observability(day_id="2026-06-04-skill-improve")
versions = publish_instruction_prompts(max_tools=5)
print(prompt_refs(versions))
print(prompt_hashes(versions))
PY
```
