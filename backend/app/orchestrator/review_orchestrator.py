"""
Review Orchestrator — coordinates the full review pipeline:
  Index → Plan → Investigate → Generate Tests → Execute → Self-Review → Publish
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.github.client import GitHubClient
from app.intelligence.repo_context import build_repo_context
from app.agents.bug_agent import BugAgent
from app.agents.security_agent import SecurityAgent
from app.agents.performance_agent import PerformanceAgent
from app.agents.test_agent import TestAgent
from app.agents.self_review_agent import SelfReviewAgent
from app.sandbox.executor import SandboxExecutor
from app.llm.client import LLMClient
from app.models.review import Review, ReviewStatus
from app.models.finding import Finding, EvidenceLevel, Severity
from app.models.timeline import TimelineEvent
from app.publisher.github_publisher import GitHubPublisher

log = structlog.get_logger(__name__)


class ReviewOrchestrator:
    def __init__(self, db: AsyncSession, installation_id: int):
        self.db = db
        self.installation_id = installation_id
        self.client = GitHubClient(installation_id)
        self.llm = LLMClient()
        self.sandbox = SandboxExecutor()

    async def run(self, review: Review):
        """Main entry point. Runs the full investigation pipeline."""
        log.info("review_started", review_id=str(review.id), pr=review.pr_number)

        try:
            await self._update_status(review, ReviewStatus.indexing)
            await self._add_timeline(review, "pr_received", "orchestrator",
                                      f"PR #{review.pr_number} received — starting analysis")

            # 1. Build repository context
            owner, repo = review.repository.full_name.split("/")
            ctx = await build_repo_context(
                self.client, owner, repo, review.pr_number,
                review.base_sha, review.head_sha,
            )
            await self._add_timeline(review, "repository_indexed", "orchestrator",
                                      f"Repository indexed — {len(ctx.file_asts)} files parsed, "
                                      f"{len(ctx.changed_files)} changed files")

            review.files_analyzed = len(ctx.changed_files)
            review.functions_impacted = sum(len(v) for v in ctx.impact_map.values())
            review.impact_map = {k: v for k, v in list(ctx.impact_map.items())[:50]}
            await self.db.flush()

            # 2. Impact analysis
            await self._add_timeline(review, "impact_analysis_completed", "orchestrator",
                                      f"Impact analysis done — {review.functions_impacted} functions potentially affected")
            await self._update_status(review, ReviewStatus.investigating)

            # 3. Run specialized agents in parallel
            raw_findings = await self._run_investigation_agents(review, ctx)

            await self._add_timeline(review, "investigation_complete", "orchestrator",
                                      f"Investigation complete — {len(raw_findings)} candidate findings")

            # 4. Generate and execute reproduction tests
            verified_findings = await self._verify_findings(review, ctx, raw_findings)

            # 5. Self-review
            await self._update_status(review, ReviewStatus.self_review)
            await self._add_timeline(review, "self_review_started", "self_review_agent",
                                      "Running quality gate on findings")
            self_reviewer = SelfReviewAgent(str(review.id), self.llm)
            final_findings = await self_reviewer.review_findings(verified_findings)

            discarded_count = len(verified_findings) - len(final_findings)
            await self._add_timeline(review, "self_review_complete", "self_review_agent",
                                      f"Quality gate passed — {len(final_findings)} findings kept, "
                                      f"{discarded_count} discarded")

            # 6. Persist findings to database
            await self._persist_findings(review, final_findings, verified_findings)

            # 7. Publish to GitHub
            await self._update_status(review, ReviewStatus.publishing)
            publisher = GitHubPublisher(self.client, owner, repo)
            await publisher.publish(review, final_findings)

            await self._add_timeline(review, "review_published", "orchestrator",
                                      f"Review published to GitHub — {len(final_findings)} findings")

            # 8. Final stats
            review.status = ReviewStatus.completed
            review.completed_at = datetime.now(timezone.utc)
            review.findings_verified = len(final_findings)
            review.findings_discarded = len(raw_findings) - len(final_findings)
            if final_findings:
                review.confidence = sum(f.get("confidence", 0.5) for f in final_findings) / len(final_findings)
            await self.db.flush()

            log.info("review_completed", review_id=str(review.id), findings=len(final_findings))

        except Exception as e:
            log.error("review_failed", review_id=str(review.id), error=str(e))
            review.status = ReviewStatus.failed
            review.error_message = str(e)[:1024]
            await self.db.flush()
            raise

    async def _run_investigation_agents(self, review: Review, ctx) -> list[dict]:
        """Run Bug, Security, and Performance agents in parallel."""
        owner, repo = review.repository.full_name.split("/")

        async def run_bug():
            await self._add_timeline(review, "bug_investigation_started", "bug_agent",
                                      "Investigating logic errors and type issues")
            agent = BugAgent(str(review.id), self.llm, ctx, self.client)
            findings = await agent.investigate()
            await self._add_timeline(review, "bug_investigation_complete", "bug_agent",
                                      f"Bug agent found {len(findings)} candidate issues")
            return findings

        async def run_security():
            await self._add_timeline(review, "security_investigation_started", "security_agent",
                                      "Analyzing data flows for security vulnerabilities")
            agent = SecurityAgent(str(review.id), self.llm, ctx, self.client)
            findings = await agent.investigate()
            await self._add_timeline(review, "security_investigation_complete", "security_agent",
                                      f"Security agent found {len(findings)} candidate issues")
            return findings

        async def run_performance():
            await self._add_timeline(review, "performance_investigation_started", "performance_agent",
                                      "Analyzing for N+1 queries and algorithmic complexity")
            agent = PerformanceAgent(str(review.id), self.llm, ctx, self.client)
            findings = await agent.investigate()
            await self._add_timeline(review, "performance_investigation_complete", "performance_agent",
                                      f"Performance agent found {len(findings)} candidate issues")
            return findings

        results = await asyncio.gather(
            run_bug(), run_security(), run_performance(),
            return_exceptions=True,
        )

        all_findings = []
        for result in results:
            if isinstance(result, list):
                all_findings.extend(result)
            elif isinstance(result, Exception):
                log.warning("agent_failed", error=str(result))

        return all_findings

    async def _verify_findings(self, review: Review, ctx, raw_findings: list[dict]) -> list[dict]:
        """Generate tests and execute them to upgrade evidence levels."""
        await self._update_status(review, ReviewStatus.verifying)
        verified = []

        # Only attempt reproduction for high-confidence findings
        reproducible = [f for f in raw_findings if f.get("confidence", 0) >= 0.7]
        non_reproducible = [f for f in raw_findings if f.get("confidence", 0) < 0.7]

        for finding in non_reproducible:
            finding["evidence_level"] = EvidenceLevel.potential.value
            verified.append(finding)

        for finding in reproducible:
            finding["evidence_level"] = EvidenceLevel.evidence_backed.value

            # Try to generate and run a reproduction test
            try:
                test_agent = TestAgent(str(review.id), self.llm, ctx, self.client)
                test_data = await test_agent.generate_test(finding)

                if test_data and test_data.get("test_code"):
                    review.tests_generated += 1
                    await self._add_timeline(
                        review, "test_generated", "test_agent",
                        f"Generated reproduction test for: {finding.get('title', 'finding')}"
                    )

                    # Get source files needed for the test
                    source_files = {}
                    file_path = finding.get("file_path")
                    if file_path:
                        cf = next((f for f in ctx.changed_files if f.filename == file_path), None)
                        if cf and cf.raw_content:
                            source_files[file_path] = cf.raw_content

                    result = await self.sandbox.run_test(
                        test_code=test_data["test_code"],
                        requirements=test_data.get("setup_requirements", []),
                        source_code=source_files,
                    )
                    review.tests_executed += 1

                    finding["tests_generated"] = [test_data]
                    finding["tests_executed"] = [{
                        "passed": result.test_passed,
                        "output": result.test_output,
                        "duration_ms": result.duration_ms,
                        "exit_code": result.exit_code,
                    }]

                    # A test that FAILS on buggy code confirms the finding
                    if not result.test_passed and test_data.get("should_fail_on_buggy_code", True):
                        finding["evidence_level"] = EvidenceLevel.reproduced.value
                        finding["reproduction_status"] = "confirmed"
                        finding["confidence"] = min(finding.get("confidence", 0.7) + 0.15, 0.99)
                        await self._add_timeline(
                            review, "issue_reproduced", "test_agent",
                            f"REPRODUCED: {finding.get('title', 'finding')} — test failed as expected"
                        )
                    else:
                        finding["reproduction_status"] = "not_reproduced"
                        await self._add_timeline(
                            review, "test_executed", "test_agent",
                            f"Test executed for '{finding.get('title', '')}' — could not reproduce"
                        )

            except Exception as e:
                log.warning("test_generation_failed", finding=finding.get("title"), error=str(e))
                finding["reproduction_status"] = "error"

            verified.append(finding)

        await self.db.flush()
        return verified

    async def _persist_findings(self, review: Review, final_findings: list[dict], all_findings: list[dict]):
        """Save findings to the database."""
        for f in final_findings:
            severity_val = f.get("severity", "medium")
            try:
                severity = Severity(severity_val)
            except ValueError:
                severity = Severity.medium

            evidence_val = f.get("evidence_level", "evidence_backed")
            try:
                evidence_level = EvidenceLevel(evidence_val)
            except ValueError:
                evidence_level = EvidenceLevel.evidence_backed

            finding = Finding(
                review_id=review.id,
                category=f.get("category", "bug"),
                severity=severity,
                evidence_level=evidence_level,
                confidence=f.get("confidence", 0.5),
                title=f.get("title", "Untitled")[:512],
                description=f.get("description", ""),
                hypothesis=f.get("hypothesis", ""),
                file_path=f.get("file_path"),
                line_start=f.get("line_start"),
                line_end=f.get("line_end"),
                function_name=f.get("function_name"),
                evidence=f.get("evidence", []),
                impact_analysis=f.get("impact_analysis"),
                tests_generated=f.get("tests_generated", []),
                tests_executed=f.get("tests_executed", []),
                reproduction_status=f.get("reproduction_status", "not_attempted"),
                recommended_fix=f.get("recommended_fix"),
                verification_status=f.get("verification_status", "not_attempted"),
                self_review_notes=f.get("self_review_notes"),
            )
            self.db.add(finding)

        # Mark discarded findings
        discarded = [f for f in all_findings if f not in final_findings]
        for f in discarded:
            finding = Finding(
                review_id=review.id,
                category=f.get("category", "bug"),
                severity=Severity.low,
                evidence_level=EvidenceLevel.discarded,
                confidence=f.get("confidence", 0.0),
                title=f.get("title", "Discarded")[:512],
                description=f.get("description", ""),
                hypothesis=f.get("hypothesis", ""),
                file_path=f.get("file_path"),
                evidence=f.get("evidence", []),
                discarded_reason="Did not pass self-review quality gate",
            )
            self.db.add(finding)

        await self.db.flush()

    async def _update_status(self, review: Review, status: ReviewStatus):
        review.status = status
        if status == ReviewStatus.investigating:
            review.started_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def _add_timeline(
        self, review: Review, event_type: str, actor: str, message: str, details: dict | None = None
    ):
        event = TimelineEvent(
            review_id=review.id,
            event_type=event_type,
            actor=actor,
            message=message,
            details=details,
        )
        self.db.add(event)
        await self.db.flush()

        # Publish real-time event via Redis
        try:
            from app.core.redis import publish_event
            import json as _json
            payload = _json.dumps({
                "review_id": str(review.id),
                "event_type": event_type,
                "actor": actor,
                "message": message,
            })
            await publish_event(f"review:{review.id}:timeline", payload)
        except Exception:
            pass
