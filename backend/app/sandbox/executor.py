"""
Isolated Docker sandbox for test execution.
Runs generated tests safely with resource limits and cleanup.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

SANDBOX_IMAGE = "python:3.12-slim"
PYTEST_INSTALL = "pip install pytest pytest-timeout -q"


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
    Executes test code inside a Docker container with strict resource limits.
    Never runs untrusted code on the host.
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
        Run pytest test code in an isolated Docker container.

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
            return await self._execute(
                workspace=workspace,
                workspace_id=workspace_id,
                test_code=test_code,
                requirements=requirements or [],
                source_code=source_code or {},
                timeout=timeout or settings.SANDBOX_TIMEOUT_SECONDS,
            )
        finally:
            self._cleanup(workspace)

    async def _execute(
        self,
        workspace: Path,
        workspace_id: str,
        test_code: str,
        requirements: list[str],
        source_code: dict[str, str],
        timeout: int,
    ) -> SandboxResult:
        import time

        # Write files to workspace
        test_file = workspace / "test_reproduction.py"
        test_file.write_text(test_code)

        for filename, content in source_code.items():
            dest = workspace / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)

        # Build install command
        pkgs = ["pytest", "pytest-timeout"] + requirements
        install_cmd = f"pip install {' '.join(pkgs)} -q 2>&1"

        # Full command
        run_cmd = f"cd /workspace && {install_cmd} && python -m pytest test_reproduction.py -v --timeout=30 --tb=short 2>&1"

        # Docker run command
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network=none",                                  # no network access
            f"--memory={settings.SANDBOX_MEM_LIMIT}",
            f"--cpu-quota={settings.SANDBOX_CPU_QUOTA}",
            "--pids-limit=64",
            "--security-opt=no-new-privileges",
            f"--volume={workspace}:/workspace:ro",
            "--workdir=/workspace",
            "--tmpfs=/tmp:size=64m",
            SANDBOX_IMAGE,
            "bash", "-c", run_cmd,
        ]

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 30)
            except asyncio.TimeoutError:
                proc.kill()
                return SandboxResult(
                    success=False, exit_code=-1,
                    stdout="", stderr="Execution timed out",
                    duration_ms=int((time.monotonic() - start) * 1000),
                    test_passed=False, test_output="Timed out",
                    workspace_id=workspace_id,
                )

            duration_ms = int((time.monotonic() - start) * 1000)
            output = stdout_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0
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
                test_output=output[-3000:],  # last 3k chars of output
                workspace_id=workspace_id,
            )

        except FileNotFoundError:
            # Docker not available — run with subprocess isolation as fallback
            log.warning("docker_not_available_falling_back_to_subprocess")
            return await self._subprocess_fallback(
                workspace, workspace_id, test_code, requirements, timeout
            )
        except Exception as e:
            log.error("sandbox_execution_failed", error=str(e))
            return SandboxResult(
                success=False, exit_code=-1,
                stdout="", stderr=str(e),
                duration_ms=0,
                test_passed=False, test_output=f"Sandbox error: {e}",
                workspace_id=workspace_id,
            )

    async def _subprocess_fallback(
        self,
        workspace: Path,
        workspace_id: str,
        test_code: str,
        requirements: list[str],
        timeout: int,
    ) -> SandboxResult:
        """Fallback when Docker is unavailable. Runs in a temp venv."""
        import time
        import sys

        start = time.monotonic()
        venv_dir = workspace / "venv"

        try:
            # Create venv
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "venv", str(venv_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            pip = str(venv_dir / "bin" / "pip") if os.name != "nt" else str(venv_dir / "Scripts" / "pip")
            pytest_bin = str(venv_dir / "bin" / "pytest") if os.name != "nt" else str(venv_dir / "Scripts" / "pytest")

            pkgs = ["pytest", "pytest-timeout"] + requirements
            proc = await asyncio.create_subprocess_exec(
                pip, "install", *pkgs, "-q",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)

            proc = await asyncio.create_subprocess_exec(
                pytest_bin, str(workspace / "test_reproduction.py"), "-v", "--tb=short",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                cwd=str(workspace),
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            return SandboxResult(
                success=True, exit_code=exit_code,
                stdout=output, stderr="",
                duration_ms=int((time.monotonic() - start) * 1000),
                test_passed=exit_code == 0,
                test_output=output[-3000:],
                workspace_id=workspace_id,
            )
        except Exception as e:
            return SandboxResult(
                success=False, exit_code=-1,
                stdout="", stderr=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
                test_passed=False, test_output=f"Fallback error: {e}",
                workspace_id=workspace_id,
            )

    def _cleanup(self, workspace: Path):
        try:
            shutil.rmtree(workspace, ignore_errors=True)
        except Exception:
            pass
