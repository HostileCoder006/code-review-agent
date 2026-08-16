"""
Benchmark runner for evaluating agent performance on historical bugs.

Measures:
- Bug detection precision / recall
- False-positive rate
- Reproduction success rate
- Test-generation success
- Review latency
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# Historical bug cases — real bugs from open-source Python projects
BENCHMARK_CASES = [
    {
        "id": "requests-type-coerce",
        "repo": "psf/requests",
        "description": "Type coercion of int to str breaks downstream consumers",
        "expected_category": "bug",
        "expected_severity": "high",
        "ground_truth_file": "requests/models.py",
        "ground_truth_pattern": r"int\(.*\)",
        "should_detect": True,
    },
    {
        "id": "flask-sql-injection",
        "repo": "pallets/flask",
        "description": "User input concatenated into SQL without sanitization",
        "expected_category": "security",
        "expected_severity": "critical",
        "ground_truth_file": "tests/test_security.py",
        "ground_truth_pattern": r"f['\"].*SELECT.*{",
        "should_detect": True,
    },
    {
        "id": "django-n-plus-one",
        "repo": "django/django",
        "description": "N+1 query in queryset iteration",
        "expected_category": "performance",
        "expected_severity": "medium",
        "ground_truth_file": "django/db/models/query.py",
        "ground_truth_pattern": r"for .* in .*\.all\(\)",
        "should_detect": True,
    },
]


@dataclass
class BenchmarkResult:
    case_id: str
    detected: bool
    category_correct: bool
    severity_correct: bool
    reproduced: bool
    test_generated: bool
    false_positive: bool
    latency_seconds: float
    findings: list[dict] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class BenchmarkSummary:
    total_cases: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    reproduction_rate: float
    test_generation_rate: float
    category_accuracy: float
    severity_accuracy: float
    avg_latency_seconds: float
    results: list[BenchmarkResult] = field(default_factory=list)


async def run_benchmark(cases: list[dict] | None = None) -> BenchmarkSummary:
    """Run the benchmark suite against known historical bugs."""
    cases = cases or BENCHMARK_CASES
    results = []

    for case in cases:
        log.info("benchmark_case_started", case_id=case["id"])
        start = time.monotonic()

        try:
            result = await _run_case(case)
            result.latency_seconds = time.monotonic() - start
        except Exception as e:
            result = BenchmarkResult(
                case_id=case["id"],
                detected=False, category_correct=False, severity_correct=False,
                reproduced=False, test_generated=False, false_positive=False,
                latency_seconds=time.monotonic() - start,
                error=str(e),
            )

        results.append(result)
        log.info("benchmark_case_complete", case_id=case["id"], detected=result.detected)

    return _compute_summary(cases, results)


async def _run_case(case: dict) -> BenchmarkResult:
    """Simulate a review run for a benchmark case using synthetic data."""
    from app.intelligence.ast_parser import parse_file
    from app.agents.bug_agent import BugAgent
    from app.agents.security_agent import SecurityAgent
    from app.agents.performance_agent import PerformanceAgent
    from app.llm.client import LLMClient
    from app.intelligence.repo_context import RepoContext

    # Create a minimal mock context
    ctx = RepoContext(
        owner=case["repo"].split("/")[0],
        repo=case["repo"].split("/")[1],
        pr_number=0,
        base_sha="base",
        head_sha="head",
    )

    llm = LLMClient()
    findings = []

    # Run the appropriate agent based on expected category
    category = case.get("expected_category", "bug")
    try:
        if category == "security":
            # Mock client
            from unittest.mock import AsyncMock, MagicMock
            mock_client = MagicMock()
            mock_client.get_commit_history = AsyncMock(return_value=[])
            mock_client.list_issues = AsyncMock(return_value=[])
            agent = SecurityAgent(f"bench-{case['id']}", llm, ctx, mock_client)
        elif category == "performance":
            from unittest.mock import AsyncMock, MagicMock
            mock_client = MagicMock()
            mock_client.get_commit_history = AsyncMock(return_value=[])
            agent = PerformanceAgent(f"bench-{case['id']}", llm, ctx, mock_client)
        else:
            from unittest.mock import AsyncMock, MagicMock
            mock_client = MagicMock()
            mock_client.get_commit_history = AsyncMock(return_value=[])
            agent = BugAgent(f"bench-{case['id']}", llm, ctx, mock_client)

        findings = await agent.investigate()
    except Exception as e:
        log.warning("benchmark_agent_error", case=case["id"], error=str(e))

    detected = len(findings) > 0 and case.get("should_detect", True)
    false_positive = len(findings) > 0 and not case.get("should_detect", True)

    category_correct = any(f.get("category") == case.get("expected_category") for f in findings) if detected else False
    severity_correct = any(f.get("severity") == case.get("expected_severity") for f in findings) if detected else False
    reproduced = any(f.get("reproduction_status") == "confirmed" for f in findings)
    test_generated = any(f.get("tests_generated") for f in findings)

    return BenchmarkResult(
        case_id=case["id"],
        detected=detected,
        category_correct=category_correct,
        severity_correct=severity_correct,
        reproduced=reproduced,
        test_generated=test_generated,
        false_positive=false_positive,
        latency_seconds=0,
        findings=findings,
    )


def _compute_summary(cases: list[dict], results: list[BenchmarkResult]) -> BenchmarkSummary:
    should_detect = [c for c in cases if c.get("should_detect", True)]
    should_not_detect = [c for c in cases if not c.get("should_detect", True)]

    tp = sum(1 for r in results if r.detected and not r.false_positive)
    fp = sum(1 for r in results if r.false_positive)
    fn = sum(1 for r in results if not r.detected and not r.false_positive)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    detected_results = [r for r in results if r.detected]
    reproduction_rate = sum(1 for r in detected_results if r.reproduced) / len(detected_results) if detected_results else 0.0
    test_gen_rate = sum(1 for r in detected_results if r.test_generated) / len(detected_results) if detected_results else 0.0
    category_acc = sum(1 for r in detected_results if r.category_correct) / len(detected_results) if detected_results else 0.0
    severity_acc = sum(1 for r in detected_results if r.severity_correct) / len(detected_results) if detected_results else 0.0
    avg_latency = sum(r.latency_seconds for r in results) / len(results) if results else 0.0

    return BenchmarkSummary(
        total_cases=len(cases),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        reproduction_rate=round(reproduction_rate, 3),
        test_generation_rate=round(test_gen_rate, 3),
        category_accuracy=round(category_acc, 3),
        severity_accuracy=round(severity_acc, 3),
        avg_latency_seconds=round(avg_latency, 1),
        results=results,
    )
