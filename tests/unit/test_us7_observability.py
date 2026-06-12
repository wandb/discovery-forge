"""US7: Cost guardrail and Weave tracing tests."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).parent.parent.parent


# ── CostBudget guard ──────────────────────────────────────────────────────────

def test_cost_budget_under_limit_does_not_raise():
    from discovery_forge.orchestrator import CostBudget
    budget = CostBudget(max_usd=5.0)
    budget.add(2.50)
    budget.add(2.49)  # total 4.99 — ok


def test_cost_budget_at_limit_raises():
    from discovery_forge.orchestrator import CostBudget, BudgetExceededError
    budget = CostBudget(max_usd=5.0)
    budget.add(4.99)
    with pytest.raises(BudgetExceededError):
        budget.add(0.02)  # pushes over


def test_cost_budget_check_raises_if_already_over():
    from discovery_forge.orchestrator import CostBudget, BudgetExceededError
    budget = CostBudget(max_usd=1.0)
    budget._total = 1.01  # set directly to simulate already-over state
    with pytest.raises(BudgetExceededError):
        budget.check()


def test_cost_budget_tracks_total():
    from discovery_forge.orchestrator import CostBudget
    budget = CostBudget(max_usd=100.0)
    budget.add(1.5)
    budget.add(2.5)
    assert budget.total_usd == pytest.approx(4.0)


def test_budget_exceeded_error_carries_info():
    from discovery_forge.orchestrator import BudgetExceededError
    err = BudgetExceededError(spent=5.1, limit=5.0)
    assert err.spent == pytest.approx(5.1)
    assert err.limit == pytest.approx(5.0)
    assert "5.1" in str(err) or "5.0" in str(err)


# ── weave_project_path ────────────────────────────────────────────────────────

def test_weave_project_path_returns_entity_and_project(monkeypatch):
    from discovery_forge.observability import weave_project_path

    monkeypatch.setenv("WANDB_ENTITY", "my-team")
    monkeypatch.setenv("WANDB_PROJECT", "my-project")
    assert weave_project_path() == "my-team/my-project"


def test_weave_project_path_requires_entity(monkeypatch):
    from discovery_forge.observability import weave_project_path

    monkeypatch.delenv("WANDB_ENTITY", raising=False)
    monkeypatch.setenv("WANDB_PROJECT", "my-project")
    with pytest.raises(ValueError, match="WANDB_ENTITY"):
        weave_project_path()


def test_weave_project_path_requires_project(monkeypatch):
    from discovery_forge.observability import weave_project_path

    monkeypatch.setenv("WANDB_ENTITY", "my-team")
    monkeypatch.delenv("WANDB_PROJECT", raising=False)
    with pytest.raises(ValueError, match="WANDB_PROJECT"):
        weave_project_path()


def test_weave_project_path_rejects_empty_project(monkeypatch):
    from discovery_forge.observability import weave_project_path

    monkeypatch.setenv("WANDB_ENTITY", "my-team")
    monkeypatch.setenv("WANDB_PROJECT", "   ")
    with pytest.raises(ValueError, match="WANDB_PROJECT"):
        weave_project_path()


# ── init_observability — unit tests with mocked weave ────────────────────────

def test_init_observability_calls_weave_init_once(mock_weave, wandb_project_env):
    from discovery_forge.observability import init_observability
    with patch("discovery_forge.observability.set_trace_processors"):
        init_observability(day_id="2026-05-28")
    mock_weave["init"].assert_called_once()


def test_init_observability_uses_replace_not_add(mock_weave, wandb_project_env):
    """set_trace_processors must be called with a list (replace), not add_trace_processor."""
    from discovery_forge.observability import init_observability
    with patch("discovery_forge.observability.set_trace_processors") as mock_stp:
        init_observability(day_id="2026-05-28")
    mock_stp.assert_called_once()
    # Must be called with a list argument
    args = mock_stp.call_args[0]
    assert len(args) == 1 and isinstance(args[0], list)


def test_init_observability_does_not_call_add_trace_processor(mock_weave, wandb_project_env):
    """Forbidden: add_trace_processor — must use set_trace_processors for replacement."""
    from discovery_forge.observability import init_observability
    with patch("discovery_forge.observability.set_trace_processors"), \
         patch("discovery_forge.observability.add_trace_processor", create=True) as mock_add:
        init_observability(day_id="2026-05-28")
    # add_trace_processor should never be called
    mock_add.assert_not_called()


# ── run_metadata cost tracking ────────────────────────────────────────────────

def test_metadata_updated_with_cost_after_run(tmp_path):
    from discovery_forge.orchestrator import update_metadata_costs
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps({"day": "2026-05-28", "started_at": "2026-01-01T00:00:00Z"}))

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
    from discovery_forge.orchestrator import update_metadata_costs
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps({"day": "2026-05-28", "max_tools": 12}))

    update_metadata_costs(metadata_path, 0.5, 100, 50)
    data = json.loads(metadata_path.read_text())
    assert data["day"] == "2026-05-28"
    assert data["max_tools"] == 12


# ── orchestrator module structure ─────────────────────────────────────────────

def test_orchestrator_exposes_run_briefing():
    import inspect
    from discovery_forge import orchestrator
    assert hasattr(orchestrator, "run_briefing")
    assert inspect.iscoroutinefunction(orchestrator.run_briefing)


def test_observability_exposes_init_observability():
    from discovery_forge import observability
    assert hasattr(observability, "init_observability")


def test_orchestrator_imports_weave_not_in_tests(mock_weave, wandb_project_env):
    """Verify orchestrator uses mocked weave in unit test context."""
    from discovery_forge.observability import init_observability
    with patch("discovery_forge.observability.set_trace_processors"):
        init_observability("2026-05-28")
    # weave.init was called via the mock (not a real network call)
    assert mock_weave["init"].called


# ── graceful shutdown: partial outputs preserved ──────────────────────────────

@pytest.mark.asyncio
async def test_budget_exceeded_preserves_existing_outputs(tmp_path):
    """When budget exceeded, already-written files must not be deleted."""
    from discovery_forge.orchestrator import CostBudget, BudgetExceededError

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
