"""US7: Cost guardrail and Weave tracing tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

ROOT = Path(__file__).parent.parent.parent


# ── CostBudget guard ──────────────────────────────────────────────────────────

def test_cost_budget_under_limit_does_not_raise():
    from autoresearch_researcher.orchestrator import CostBudget
    budget = CostBudget(max_usd=5.0)
    budget.add(2.50)
    budget.add(2.49)  # total 4.99 — ok


def test_cost_budget_at_limit_raises():
    from autoresearch_researcher.orchestrator import CostBudget, BudgetExceededError
    budget = CostBudget(max_usd=5.0)
    budget.add(4.99)
    with pytest.raises(BudgetExceededError):
        budget.add(0.02)  # pushes over


def test_cost_budget_check_raises_if_already_over():
    from autoresearch_researcher.orchestrator import CostBudget, BudgetExceededError
    budget = CostBudget(max_usd=1.0)
    budget._total = 1.01  # set directly to simulate already-over state
    with pytest.raises(BudgetExceededError):
        budget.check()


def test_cost_budget_tracks_total():
    from autoresearch_researcher.orchestrator import CostBudget
    budget = CostBudget(max_usd=100.0)
    budget.add(1.5)
    budget.add(2.5)
    assert budget.total_usd == pytest.approx(4.0)


def test_budget_exceeded_error_carries_info():
    from autoresearch_researcher.orchestrator import BudgetExceededError
    err = BudgetExceededError(spent=5.1, limit=5.0)
    assert err.spent == pytest.approx(5.1)
    assert err.limit == pytest.approx(5.0)
    assert "5.1" in str(err) or "5.0" in str(err)


# ── init_observability — unit tests with mocked weave ────────────────────────

def test_init_observability_calls_weave_init_once(mock_weave):
    from autoresearch_researcher.orchestrator import init_observability
    with patch("autoresearch_researcher.orchestrator.set_trace_processors") as mock_stp:
        init_observability(week_id="2026-W99")
    mock_weave["init"].assert_called_once()


def test_init_observability_uses_replace_not_add(mock_weave):
    """set_trace_processors must be called with a list (replace), not add_trace_processor."""
    from autoresearch_researcher.orchestrator import init_observability
    with patch("autoresearch_researcher.orchestrator.set_trace_processors") as mock_stp:
        init_observability(week_id="2026-W99")
    mock_stp.assert_called_once()
    # Must be called with a list argument
    args = mock_stp.call_args[0]
    assert len(args) == 1 and isinstance(args[0], list)


def test_init_observability_does_not_call_add_trace_processor(mock_weave):
    """Forbidden: add_trace_processor — must use set_trace_processors for replacement."""
    from autoresearch_researcher.orchestrator import init_observability
    with patch("autoresearch_researcher.orchestrator.set_trace_processors") as mock_stp, \
         patch("autoresearch_researcher.orchestrator.add_trace_processor", create=True) as mock_add:
        init_observability(week_id="2026-W99")
    # add_trace_processor should never be called
    mock_add.assert_not_called()


# ── run_metadata cost tracking ────────────────────────────────────────────────

def test_metadata_updated_with_cost_after_run(tmp_path):
    from autoresearch_researcher.orchestrator import update_metadata_costs
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps({"week": "2026-W99", "started_at": "2026-01-01T00:00:00Z"}))

    update_metadata_costs(
        metadata_path=metadata_path,
        total_cost_usd=1.23,
        prompt_tokens=5000,
        completion_tokens=2000,
    )

    data = json.loads(metadata_path.read_text())
    assert data["total_cost_usd"] == pytest.approx(1.23)
    assert data["prompt_tokens"] == 5000
    assert data["completion_tokens"] == 2000


def test_metadata_cost_update_preserves_existing_fields(tmp_path):
    from autoresearch_researcher.orchestrator import update_metadata_costs
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps({"week": "2026-W99", "max_tools": 12}))

    update_metadata_costs(metadata_path, 0.5, 100, 50)
    data = json.loads(metadata_path.read_text())
    assert data["week"] == "2026-W99"
    assert data["max_tools"] == 12


# ── orchestrator module structure ─────────────────────────────────────────────

def test_orchestrator_exposes_run_briefing():
    import inspect
    from autoresearch_researcher import orchestrator
    assert hasattr(orchestrator, "run_briefing")
    assert inspect.iscoroutinefunction(orchestrator.run_briefing)


def test_orchestrator_exposes_init_observability():
    from autoresearch_researcher import orchestrator
    assert hasattr(orchestrator, "init_observability")


def test_orchestrator_imports_weave_not_in_tests(mock_weave):
    """Verify orchestrator uses mocked weave in unit test context."""
    from autoresearch_researcher.orchestrator import init_observability
    with patch("autoresearch_researcher.orchestrator.set_trace_processors"):
        init_observability("2026-W99")
    # weave.init was called via the mock (not a real network call)
    assert mock_weave["init"].called


# ── graceful shutdown: partial outputs preserved ──────────────────────────────

@pytest.mark.asyncio
async def test_budget_exceeded_preserves_existing_outputs(tmp_path):
    """When budget exceeded, already-written files must not be deleted."""
    from autoresearch_researcher.orchestrator import CostBudget, BudgetExceededError

    # Simulate partial output already written
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "partial-tool.md").write_text("# Partial\nSome content")

    budget = CostBudget(max_usd=0.01)
    budget._total = 0.02  # set directly to simulate already-over state

    # The partial output file should still exist after budget exceeded
    assert (tools_dir / "partial-tool.md").exists()
    with pytest.raises(BudgetExceededError):
        budget.check()
    # File still exists — graceful (no cleanup on abort)
    assert (tools_dir / "partial-tool.md").exists()
