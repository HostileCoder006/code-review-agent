"""
Tests for the sandbox executor.
"""
import pytest
import pytest_asyncio
from app.sandbox.executor import SandboxExecutor


@pytest.mark.asyncio
async def test_passing_test():
    executor = SandboxExecutor()
    test_code = """
def test_simple_addition():
    assert 1 + 1 == 2
"""
    result = await executor.run_test(test_code)
    assert result.test_passed is True
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_failing_test():
    executor = SandboxExecutor()
    test_code = """
def test_intentional_failure():
    # This test should fail — simulating a bug reproduction
    result = 1 + 1
    assert result == 3, f"Expected 3, got {result}"
"""
    result = await executor.run_test(test_code)
    assert result.test_passed is False


@pytest.mark.asyncio
async def test_with_source_code():
    executor = SandboxExecutor()

    source_code = {
        "mymodule.py": """
def process(value):
    return int(value)  # Bug: converts to int
"""
    }

    test_code = """
import sys
sys.path.insert(0, '.')
from mymodule import process

def test_type_preserved():
    result = process("123")
    # Downstream expects string, but gets int
    assert isinstance(result, str), f"Expected str, got {type(result)}"
"""
    result = await executor.run_test(test_code, source_code=source_code)
    # The test should FAIL because process() returns int, not str
    assert result.test_passed is False  # Confirms the bug


@pytest.mark.asyncio
async def test_cleanup_after_execution():
    """Workspace should be cleaned up after execution."""
    import os
    from pathlib import Path
    from app.core.config import settings

    executor = SandboxExecutor()
    workspace_dir = Path(settings.SANDBOX_WORKSPACE_DIR)
    before = set(workspace_dir.iterdir()) if workspace_dir.exists() else set()

    await executor.run_test("def test_x(): assert True")

    after = set(workspace_dir.iterdir()) if workspace_dir.exists() else set()
    new_dirs = after - before
    assert len(new_dirs) == 0, f"Workspaces not cleaned up: {new_dirs}"
