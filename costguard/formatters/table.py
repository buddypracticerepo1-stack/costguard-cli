"""Table formatter for terminal output"""

from typing import List
from ..api.client import AnalysisResult, ProjectResult


class TableFormatter:
    """Format results as terminal tables"""

    def __init__(self, show_resources: bool = True, show_unchanged: bool = False):
        self.show_resources = show_resources
        self.show_unchanged = show_unchanged

    def format(self, result: AnalysisResult) -> str:
        """Format analysis result as table"""
        lines = []

        # Header
        lines.append("")
        lines.append(self._header("CostGuard Cost Analysis"))
        lines.append("")

        # Summary
        lines.append(f"  Total Monthly Cost: ${result.total_monthly_cost:,.2f}")
        lines.append(f"  Total Hourly Cost:  ${result.total_hourly_cost:,.4f}")
        lines.append(f"  Decision: {self._decision_icon(result.decision)} {result.decision}")
        lines.append("")

        # Projects
        lines.append(self._header("Projects"))
        lines.append("")

        for project in result.projects:
            lines.extend(self._format_project(project))
            lines.append("")

        return "\n".join(lines)

    def _format_project(self, project: ProjectResult) -> List[str]:
        """Format a single project"""
        lines = []

        # Project header
        icon = self._decision_icon(project.decision)
        lines.append(f"  {icon} {project.name}")
        lines.append(f"     Path: {project.path}")
        lines.append(f"     Cost: ${project.monthly_cost:,.2f}/month")
        lines.append(f"     Resources: {project.total_resources} total, "
                    f"{project.priced_resources} priced, "
                    f"{project.failed_resources} failed")

        if project.error:
            lines.append(f"     Error: {project.error}")

        # Resource breakdown
        if self.show_resources and project.resources:
            lines.append("")
            lines.append("     Resources:")
            lines.append("     " + "-" * 70)
            lines.append(f"     {'Resource':<35} {'Type':<20} {'Cost/mo':>12}")
            lines.append("     " + "-" * 70)

            for res in project.resources:
                if not self.show_unchanged and res.monthly_cost == 0:
                    continue

                # Truncate long resource IDs
                res_id = res.resource_id
                if len(res_id) > 33:
                    res_id = res_id[:30] + "..."

                res_type = res.resource_type
                if len(res_type) > 18:
                    res_type = res_type[:15] + "..."

                status = "OK" if res.success else "FAIL"
                icon = "+" if res.success else "x"

                lines.append(
                    f"     {icon} {res_id:<33} {res_type:<20} ${res.monthly_cost:>10,.2f}"
                )

            lines.append("     " + "-" * 70)

        return lines

    def _header(self, text: str) -> str:
        """Create a header line"""
        return f"  === {text} ==="

    def _decision_icon(self, decision: str) -> str:
        """Get icon for decision"""
        icons = {
            "ALLOW": "[OK]",
            "WARN": "[!!]",
            "DENY": "[XX]",
            "ERROR": "[??]"
        }
        return icons.get(decision, "[--]")
