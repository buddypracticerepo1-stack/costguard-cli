"""JSON formatter for CI/CD output"""

import json
from dataclasses import asdict
from typing import Any, Dict

from ..api.client import AnalysisResult


class JsonFormatter:
    """Format results as JSON"""

    def __init__(self, pretty: bool = True):
        self.pretty = pretty

    def format(self, result: AnalysisResult) -> str:
        """Format analysis result as JSON"""
        data = self._to_dict(result)

        if self.pretty:
            return json.dumps(data, indent=2, default=str)
        else:
            return json.dumps(data, default=str)

    def _to_dict(self, result: AnalysisResult) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            "version": "1.0",
            "status": result.status,
            "decision": result.decision,
            "currency": result.currency,
            "summary": {
                "total_monthly_cost": result.total_monthly_cost,
                "total_hourly_cost": result.total_hourly_cost,
                "project_count": len(result.projects)
            },
            "projects": [
                {
                    "name": p.name,
                    "path": p.path,
                    "status": p.status,
                    "decision": p.decision,
                    "monthly_cost": p.monthly_cost,
                    "hourly_cost": p.hourly_cost,
                    "resources": {
                        "total": p.total_resources,
                        "priced": p.priced_resources,
                        "failed": p.failed_resources,
                        "warned": p.warned_resources
                    },
                    "resource_details": [
                        {
                            "id": r.resource_id,
                            "type": r.resource_type,
                            "provider": r.provider,
                            "region": r.region,
                            "monthly_cost": r.monthly_cost,
                            "success": r.success,
                            "error": r.error
                        }
                        for r in p.resources
                    ],
                    "error": p.error
                }
                for p in result.projects
            ]
        }
