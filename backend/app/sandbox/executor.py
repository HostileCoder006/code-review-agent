"""
Sandbox executor — runs generated tests in isolated Python venvs.
Works natively on Windows without Docker.
Each test gets its own throwaway venv that is deleted after execution.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


@dataclass
class SandboxResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    test_passed: bool
    test_output: str
    workspace_id: str


class SandboxExecutor:
    """
    Executes generated test code in an isolated Python venv.
    Each execution gets a fresh throwaway venv and workspace directory
    that is cleaned up after the run.

    No Docker required — works natively on Windows, Linux, and macOS.
    """

    def __init__(self):
        self.workspace_dir = Path(settings.SANDBOX_WORKSPACE_DIR)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    async def run_test(
        self,
        test_code: str,
        requirements: list[str] | None = None,
        source_code: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> SandboxResult:
        """
        Run pytest test code in an isolated venv.

        Args:
            test_code: The pytest test file content
            requirements: Additional pip packages to install
            source_code: Dict of {filename: content} for source files to include
            timeout: Execution timeout in seconds
        """
        workspace_id = str(uuid.uuid4())[:8]
        workspace = self.workspace_dir / workspace_id
        workspace.mkdir(parents=True, exist_ok=True)

        try:
            return await self._execute_in_venv(
                workspace=workspace,
                workspace_id=workspace_id,
                test_code=test_code,
                requirements=requirements or [],
                source_code=source_code or {},
                timeout=timeout or settings.SANDBOX_TIMEOUT_SECONDS,
            )
        finally:
            self._cleanup(workspace)

    async def _execute_in_venv(
        self,
        workspace: Path,
        workspace_id: str,
        test_code: str,
        requirements: list[str],
        source_code: dict[str, str],
        timeout: int,
    ) -> SandboxResult:
        start = time.monotonic()
        venv_dir = workspace / "venv"

        # Write test file
        (workspace / "test_reproduction.py").write_text(test_code, encoding="utf-8")

        # Write any source files needed by the test
        for filename, content in source_code.items():
            dest = workspace / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")

        # Platform-aware paths
        is_windows = os.name == "nt"
        scripts = "Scripts" if is_windows else "bin"
        pip_exe = str(venv_dir / scripts / "pip.exe" if is_windows else venv_dir / scripts / "pip")
        pytest_exe = str(venv_dir / scripts / "pytest.exe" if is_windows else venv_dir / scripts / "pytest")

        try:
            # Step 1: create venv
            venv_proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "venv", str(venv_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(venv_proc.communicate(), timeout=60)

            # Step 2: install dependencies
            pkgs = ["pytest", "pytest-timeout"] + requirements
            pip_proc = await asyncio.create_subprocess_exec(
                pip_exe, "install", *pkgs, "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(pip_proc.communicate(), timeout=120)

            # Step 3: run pytest
            test_proc = await asyncio.create_subprocess_exec(
                pytest_exe,
                "test_reproduction.py",
                "-v", "--tb=short", "--timeout=30", "--no-header",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(workspace),
            )

            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    test_proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                test_proc.kill()
                duration_ms = int((time.monotonic() - start) * 1000)
                log.warning("sandbox_timeout", workspace_id=workspace_id)
                return SandboxResult(
                    success=False, exit_code=-1,
                    stdout="", stderr="Execution timed out",
                    duration_ms=duration_ms,
                    test_passed=False,
                    test_output=f"Test timed out after {timeout}s",
                    workspace_id=workspace_id,
                )

            duration_ms = int((time.monotonic() - start) * 1000)
            output = stdout_bytes.decode("utf-8", errors="replace")
            exit_code = test_proc.returncode or 0
            test_passed = exit_code == 0 and "passed" in output.lower()

            log.info(
                "sandbox_execution_complete",
                workspace_id=workspace_id,
                exit_code=exit_code,
                duration_ms=duration_ms,
                test_passed=test_passed,
            )

            return SandboxResult(
                success=True,
                exit_code=exit_code,
                stdout=output,
                stderr="",
                duration_ms=duration_ms,
                test_passed=test_passed,
                test_output=output[-3000:],
                workspace_id=workspace_id,
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.error("sandbox_execution_failed", error=str(e), workspace_id=workspace_id)
            return SandboxResult(
                success=False, exit_code=-1,
                stdout="", stderr=str(e),
                duration_ms=duration_ms,
                test_passed=False,
                test_output=f"Sandbox error: {e}",
                workspace_id=workspace_id,
            )

    def _cleanup(self, workspace: Path):
        try:
            shutil.rmtree(workspace, ignore_errors=True)
        except Exception:
            pass
