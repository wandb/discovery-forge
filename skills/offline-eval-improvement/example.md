# Example: Offline Eval Prompt Improvement

This example shows the **default `high` change budget**: cover the failure clusters together in one balanced edit, then measure across multiple runs because a single eval run varies by ~±2-3 rows.

## 1. Baseline evaluation (run 2-3 times)

```bash
uv run python evaluate.py
```

Record the eval call ID and `verdict_quality_scorer.is_correct` for each run. Treat the set of runs (not one number) as the baseline, because the same prompt drifts by ~±2-3 rows.

## 2. Query failed rows and check stability

Read official W&B Skills guidance first (`npx skills add wandb/skills`), then query evidence directly through the Weave Python SDK/trace server API.

```bash
uv run python - <<'PY'
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv(".env")
import weave
from weave.trace_server.trace_server_interface import CallsFilter, CallsQueryReq
from discovery_forge.observability import weave_project_path

run_ids = ["<eval-call-id-1>", "<eval-call-id-2>", "<eval-call-id-3>"]
client = weave.init(weave_project_path())
correct = defaultdict(int); exp = {}
for eid in run_ids:
    ch = client.server.calls_query(CallsQueryReq(
        project_id=client.project_id, filter=CallsFilter(parent_ids=[eid]), limit=100))
    for call in ch.calls:
        ex = (call.inputs or {}).get("example")
        row = weave.ref(ex).get() if isinstance(ex, str) else {}
        rid = row.get("id")
        if not rid:
            continue
        exp[rid] = row["expected_scope_status"]
        ok = (call.output or {}).get("scores", {}).get("verdict_quality_scorer", {}).get("is_correct")
        correct[rid] += 1 if ok else 0
n = len(run_ids)
for rid in sorted(exp):
    tag = "STABLE-OK" if correct[rid] == n else ("STABLE-WRONG" if correct[rid] == 0 else "FLAKY")
    print(f"{tag:12} {rid} [{exp[rid]}] correct {correct[rid]}/{n}")
PY
```

This separates the solid core (stable rows) from search-driven noise (flaky rows) and shows which failures are real targets (stable-wrong).

## 3. Apply one broad, balanced edit (`high` budget)

Add a full `Candidate Verdict Mode` that covers the clusters together and pairs reject rules with accept protection:

```markdown
## Change Budget
- Change budget: high
- Edit posture: broad — full Candidate Verdict Mode with reject rules + accept protection
- Clusters covered this iteration: artifact-type (survey/cookbook/guide/list), infrastructure (memory-only, testing gate, repo-automation host, generic framework), weak-evidence edge cases
- Deferred to next iteration: none
```

Prompt move (illustrative):

- Accept-first clause: accept systems that themselves edit/evaluate/iterate on their own artifact; treat missing GitHub metadata/stars/dates as a profile limitation, not a scope failure.
- Reject-by-type list: surveys/lists/guides, GUI/computer-use frameworks, behavior testing/regression gates, repo-automation/GitHub Actions hosts, memory-only stores, generic agent/orchestration frameworks.
- Marketing-language caveat: "self-evolving"/"continuous AI"/"learns from experience" are not enough without a concrete task -> evaluation -> feedback/state -> revision loop.

The accept-protection clause is what prevents correctly-accepted loop runners from flipping to false rejects when the reject rules tighten.

## 4. Validate and rerun (multiple times)

```bash
uv run pytest tests/unit/test_researcher.py -q
uv run python evaluate.py   # run 2-3 times
```

Keep the change only if the metric improves across runs, not on a single lucky run.

## 5. Compare in Weave

Use **Evals → Compare** on the baseline runs and the post-edit runs. A broad edit should move the metric clearly above the ±2-3 noise band; confirm targeted stable-wrong rows flipped to correct and that no correctly-accepted rows became false rejects.

## Smaller, more traceable steps (`low` / `medium`)

When you want the change to be easy to follow row-by-row, use `low` or `medium`: fix one cluster per pass. Expect each step's effect to be small enough that you should average several runs to separate it from variance.

## What not to do

- Do not change dataset rows, labels, or scorers to improve the score.
- Do not trust a single eval run; the same prompt drifts ~±2-3 rows.
- Do not publish `researcher.md` to Weave between iterations unless asked.
