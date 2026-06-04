"""US1: Project bootstrap validation tests."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def test_pyproject_toml_exists():
    assert (ROOT / "pyproject.toml").exists()


def test_pyproject_has_required_dependencies():
    content = (ROOT / "pyproject.toml").read_text()
    for dep in ["openai-agents", "weave", "pytest", "pytest-asyncio", "python-dotenv"]:
        assert dep in content, f"Missing dependency: {dep}"


def test_env_example_exists():
    assert (ROOT / ".env.example").exists()


def test_env_example_has_required_keys():
    content = (ROOT / ".env.example").read_text()
    assert "OPENAI_API_KEY" in content
    assert "WANDB_API_KEY" in content
    assert "GITHUB_TOKEN" in content


def test_gitignore_has_required_entries():
    content = (ROOT / ".gitignore").read_text()
    for entry in [".env", "daily_runs/", "__pycache__/", ".venv/", "wandb/"]:
        assert entry in content, f"Missing .gitignore entry: {entry}"


def test_tests_conftest_exists():
    assert (ROOT / "tests" / "conftest.py").exists()


def test_src_package_structure():
    src = ROOT / "src" / "discovery_forge"
    assert src.exists()
    assert (src / "__init__.py").exists()
    assert (src / "agents").exists()
    assert (src / "instructions").exists()
    assert (src / "tools").exists()
    assert (src / "schemas").exists()
