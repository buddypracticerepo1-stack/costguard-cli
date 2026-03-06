"""GitHub PR comment formatter"""

from typing import List
from ..api.client import AnalysisResult, ProjectResult


class GitHubFormatter:
    """Format results as GitHub PR comment markdown"""

    def __init__(
        self,
        show_resources: bool = True,
        collapse_resources: bool = True,
        show_unchanged: bool = False
    ):
        self.show_resources = show_resources
        self.collapse_resources = collapse_resources
        self.show_unchanged = show_unchanged

    def format(self, result: AnalysisResult) -> str:
        """Format analysis result as GitHub markdown"""
        lines = []

        # Header
        lines.append("## CostGuard Cost Analysis")
        lines.append("")

        # Summary table
        status_icon = self._decision_emoji(result.decision)
        lines.append("| | |")
        lines.append("|---|---|")
        lines.append(f"| **Status** | {status_icon} {result.decision} |")
        lines.append(f"| **Total Monthly Cost** | **${result.total_monthly_cost:,.2f}** {result.currency} |")
        lines.append(f"| **Total Hourly Cost** | ${result.total_hourly_cost:,.4f} {result.currency} |")
        lines.append(f"| **Projects** | {len(result.projects)} |")
        lines.append("")

        # Project breakdown
        if len(result.projects) > 1:
            lines.append("### Cost by Project")
            lines.append("")
            lines.append("| Project | Provider | Monthly Cost | Status |")
            lines.append("|---------|----------|-------------:|--------|")

            for project in result.projects:
                provider = self._detect_provider(project)
                icon = self._decision_emoji(project.decision)
                lines.append(
                    f"| {project.name} | {provider} | "
                    f"${project.monthly_cost:,.2f} | {icon} {project.decision} |"
                )
            lines.append("")

        # Resource details per project
        if self.show_resources:
            for project in result.projects:
                lines.extend(self._format_project_resources(project))

        # Footer
        lines.append("---")
        lines.append("*Powered by [CostGuard](https://skyxops.com) — Cloud Cost Analysis*")

        return "\n".join(lines)

    def _format_project_resources(self, project: ProjectResult) -> List[str]:
        """Format resources for a project"""
        lines = []

        if not project.resources:
            return lines

        # Filter resources if needed
        resources = project.resources
        if not self.show_unchanged:
            resources = [r for r in resources if r.monthly_cost > 0 or not r.success]

        if not resources:
            return lines

        # Header
        header = f"### {project.name} Resources"

        if self.collapse_resources:
            lines.append("<details>")
            lines.append(f"<summary>{header} ({len(resources)} resources)</summary>")
            lines.append("")
        else:
            lines.append(header)
            lines.append("")

        # Resource table
        lines.append("| Resource | Type | Region | Cost/mo | Status |")
        lines.append("|----------|------|--------|--------:|--------|")

        for res in resources:
            # Truncate long IDs
            res_id = res.resource_id
            if len(res_id) > 40:
                res_id = res_id[:37] + "..."

            status_icon = "&#x2705;" if res.success else "&#x274C;"
            status_text = "OK" if res.success else "FAIL"

            lines.append(
                f"| `{res_id}` | `{res.resource_type}` | "
                f"{res.region} | ${res.monthly_cost:,.2f} | "
                f"{status_icon} {status_text} |"
            )

        lines.append("")

        if self.collapse_resources:
            lines.append("</details>")
            lines.append("")

        return lines

    def _decision_emoji(self, decision: str) -> str:
        """Get emoji for decision"""
        emojis = {
            "ALLOW": "&#x2705;",  # Green check
            "WARN": "&#x26A0;&#xFE0F;",  # Warning
            "DENY": "&#x1F6D1;",  # Stop sign
            "ERROR": "&#x274C;"  # Red X
        }
        return emojis.get(decision, "&#x2753;")

    def _detect_provider(self, project: ProjectResult) -> str:
        """Detect provider from resources"""
        if not project.resources:
            return "Unknown"

        providers = set(r.provider for r in project.resources)

        if "aws" in providers:
            return "AWS"
        elif "gcp" in providers:
            return "GCP"
        elif "azure" in providers:
            return "Azure"
        else:
            return "Unknown"
