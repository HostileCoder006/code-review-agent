"""
Publishes review findings back to GitHub as PR review comments and check runs.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.github.client import GitHubClient
from app.models.review import Review
from app.models.finding import EvidenceLevel

log = structlog.get_logger(__name__)

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}

EVIDENCE_LABEL = {
    "potential": "⚠️ Potential",
    "evidence_backed": "📎 Evidence-backed",
    "reproduced": "🔬 Reproduced",
    "fixed_and_verified": "✅ Fixed & Verified",
}


class GitHubPublisher:
    def __init__(self, client: GitHubClient, owner: str, repo: str):
        self.client = client
        self.owner = owner
        self.repo = repo

    async def publish(self, review: Review, findings: list[dict]):
        """Post inline review comments and a summary check run."""
        if not findings:
            await self._post_clean_review(review)
            await self._update_check_run(review, findings)
            return

        inline_comments = self._build_inline_comments(findings)
        summary = self._build_summary(review, findings)

        try:
            await self.client.create_review(
                self.owner, self.repo, review.pr_number,
                body=summary,
                event="COMMENT",
                comments=inline_comments,
            )
            log.info("github_review_posted", pr=review.pr_number, comments=len(inline_comments))
        except Exception as e:
            log.error("github_review_failed", error=str(e))
            # Try posting without inline comments as fallback
            try:
                await self.client.create_review(
                    self.owner, self.repo, review.pr_number,
                    body=summary, event="COMMENT", comments=[],
                )
            except Exception as e2:
                log.error("github_review_fallback_failed", error=str(e2))

        await self._update_check_run(review, findings)

    def _build_inline_comments(self, findings: list[dict]) -> list[dict]:
        comments = []
        for f in findings:
            if not f.get("file_path") or not f.get("line_start"):
                continue

            body = self._format_finding_comment(f)
            comments.append({
                "path": f["file_path"],
                "line": f["line_start"],
                "side": "RIGHT",
                "body": body,
            })
        return comments

    def _format_finding_comment(self, f: dict) -> str:
        severity = f.get("severity", "medium")
        emoji = SEVERITY_EMOJI.get(severity, "⚪")
        evidence_level = f.get("evidence_level", "potential")
        evidence_label = EVIDENCE_LABEL.get(evidence_level, evidence_level)
        confidence = int(f.get("confidence", 0.5) * 100)

        lines = [
            f"### {emoji} {severity.upper()} — {f.get('title', 'Finding')}",
            f"**Evidence level:** {evidence_label} | **Confidence:** {confidence}%",
            "",
            f.get("description", ""),
            "",
        ]

        if f.get("evidence"):
            lines.append("**Evidence:**")
            for ev in f["evidence"][:5]:
                lines.append(f"- {ev}")
            lines.append("")

        if f.get("reproduction_status") == "confirmed":
            test_result = (f.get("tests_executed") or [{}])[0]
            lines.extend([
                "**🔬 Reproduced:** A generated test confirmed this issue.",
                f"```",
                (test_result.get("output") or "")[:500],
                "```",
                "",
            ])

        if f.get("recommended_fix"):
            lines.extend([
                "**Suggested fix:**",
                f.get("recommended_fix", ""),
                "",
            ])

        return "\n".join(lines)

    def _build_summary(self, review: Review, findings: list[dict]) -> str:
        severity_counts: dict[str, int] = {}
        for f in findings:
            s = f.get("severity", "medium")
            severity_counts[s] = severity_counts.get(s, 0) + 1

        reproduced = sum(1 for f in findings if f.get("reproduction_status") == "confirmed")

        lines = [
            "## 🤖 Autonomous Code Review",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Files analyzed | {review.files_analyzed} |",
            f"| Functions impacted | {review.functions_impacted} |",
            f"| Tests generated | {review.tests_generated} |",
            f"| Tests executed | {review.tests_executed} |",
            f"| 🔴 Critical | {severity_counts.get('critical', 0)} |",
            f"| 🟠 High | {severity_counts.get('high', 0)} |",
            f"| 🟡 Medium | {severity_counts.get('medium', 0)} |",
            f"| 🔵 Low | {severity_counts.get('low', 0)} |",
            f"| Reproduced findings | {reproduced} |",
            f"| Confidence | {int(review.confidence * 100)}% |",
            "",
            "---",
            "",
            "### Findings",
        ]

        for f in findings:
            severity = f.get("severity", "medium")
            emoji = SEVERITY_EMOJI.get(severity, "⚪")
            evidence_level = f.get("evidence_level", "potential")
            evidence_label = EVIDENCE_LABEL.get(evidence_level, evidence_level)
            file_info = f"{f.get('file_path', '')}:{f.get('line_start', '')}" if f.get("file_path") else "—"
            lines.append(f"- {emoji} **{f.get('title', '')}** `{file_info}` — {evidence_label}")

        lines.extend([
            "",
            "---",
            f"*Unverified candidates discarded: {review.findings_discarded}. "
            "Only evidence-backed findings are shown.*",
        ])

        return "\n".join(lines)

    async def _post_clean_review(self, review: Review):
        body = (
            "## 🤖 Autonomous Code Review\n\n"
            "✅ **No issues found.** The analysis completed without identifying "
            "any confirmed bugs, security vulnerabilities, or performance problems.\n\n"
            f"Files analyzed: {review.files_analyzed} | "
            f"Functions impacted: {review.functions_impacted}"
        )
        try:
            await self.client.create_review(
                self.owner, self.repo, review.pr_number,
                body=body, event="COMMENT", comments=[],
            )
        except Exception as e:
            log.error("clean_review_post_failed", error=str(e))

    async def _update_check_run(self, review: Review, findings: list[dict]):
        if not review.github_check_run_id:
            return

        has_critical_high = any(f.get("severity") in ("critical", "high") for f in findings)
        conclusion = "failure" if has_critical_high else "success"

        severity_counts: dict[str, int] = {}
        for f in findings:
            s = f.get("severity", "medium")
            severity_counts[s] = severity_counts.get(s, 0) + 1

        summary = (
            f"Files: {review.files_analyzed} | "
            f"Critical: {severity_counts.get('critical', 0)} | "
            f"High: {severity_counts.get('high', 0)} | "
            f"Medium: {severity_counts.get('medium', 0)} | "
            f"Low: {severity_counts.get('low', 0)}"
        )

        try:
            await self.client.update_check_run(
                self.owner, self.repo, review.github_check_run_id,
                payload={
                    "status": "completed",
                    "conclusion": conclusion,
                    "output": {
                        "title": f"Autonomous Code Review — {len(findings)} finding(s)",
                        "summary": summary,
                    },
                },
            )
        except Exception as e:
            log.error("check_run_update_failed", error=str(e))
