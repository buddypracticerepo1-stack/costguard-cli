"""CostGuard API client"""

import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

import requests


@dataclass
class AnalyzeOutcome:
    """Outcome of a single /v1/costguard/analyze call.

    The CostGuard API can return HTTP 200 with results.errors[] populated
    (decision=ERROR), which a naive HTTP-status check treats as success.
    This dataclass surfaces both the transport status and the analysis
    status so callers can exit non-zero on either failure mode.
    """

    http_status: int
    ok: bool                       # True iff HTTP 2xx AND no analysis errors
    total_monthly_usd: float = 0.0
    decision: str = "UNKNOWN"
    errors: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None
    transport_error: Optional[str] = None

    def exit_code(self) -> int:
        """0 = ok, 1 = analysis failed (200 + errors), 2 = transport/server error."""
        if self.ok:
            return 0
        if self.http_status and 200 <= self.http_status < 300:
            return 1
        return 2


@dataclass
class ResourceResult:
    """Single resource cost result"""
    resource_id: str
    resource_type: str
    provider: str
    region: str
    monthly_cost: float
    hourly_cost: float
    success: bool
    error: Optional[str] = None
    warnings: Optional[List[str]] = None


@dataclass
class ProjectResult:
    """Single project analysis result"""
    name: str
    path: str
    status: str
    decision: str
    monthly_cost: float
    hourly_cost: float
    total_resources: int
    priced_resources: int
    failed_resources: int
    warned_resources: int
    resources: List[ResourceResult]
    error: Optional[str] = None


@dataclass
class AnalysisResult:
    """Combined analysis result for all projects"""
    status: str
    total_monthly_cost: float
    total_hourly_cost: float
    projects: List[ProjectResult]
    decision: str  # ALLOW, WARN, DENY
    currency: str = "USD"


class CostGuardClient:
    """Client for CostGuard API"""

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://4tm9xj5nv0.execute-api.us-east-1.amazonaws.com/rnd/v1/costguard/analyze",
        timeout: int = 60
    ):
        self.api_key = api_key
        # User provides the FULL endpoint URL (including the path). The
        # client posts to this URL verbatim — no path appending. Keeps the
        # contract simple: whatever you pass is exactly what gets POSTed.
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def analyze_raw(self, body: Dict[str, Any]) -> AnalyzeOutcome:
        """POST a pre-normalized request body and return a decision-aware outcome.

        Use when the caller has already detected iac_type + normalized iac_plan
        (e.g. via costguard.utils.detect.detect_payload). This method does NOT
        wrap terraform-only assumptions — it sends `body` as-is.

        Crucially, it inspects `results.errors[]` even on HTTP 200 so that the
        server-side "200 + decision=ERROR" envelope can't masquerade as
        success (the issue that hid `'str' object has no attribute 'get'`
        CFN-parser crashes in CI workflows that only checked the HTTP status).
        """
        try:
            r = requests.post(
                self.api_url,
                json=body,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            return AnalyzeOutcome(
                http_status=0, ok=False, transport_error=str(exc)
            )

        try:
            data = r.json() if r.text else None
        except ValueError:
            data = None

        if r.status_code >= 400 or data is None:
            return AnalyzeOutcome(
                http_status=r.status_code,
                ok=False,
                raw_response=data,
                transport_error=(r.text[:500] if data is None else None),
            )

        results = data.get("results", {}) or {}
        errors = results.get("errors", []) or []
        decision = (
            data.get("endpoint_data", {}).get("decision")
            or results.get("decision")
            or "UNKNOWN"
        )
        total = results.get("total_monthly_usd", 0) or 0

        return AnalyzeOutcome(
            http_status=r.status_code,
            ok=(not errors and decision != "ERROR"),
            total_monthly_usd=float(total),
            decision=decision,
            errors=errors,
            raw_response=data,
        )

    def analyze_plan(
        self,
        plan: Dict[str, Any],
        project_name: str = "default",
        project_path: str = ".",
        environment: str = "dev",
        tags: Optional[Dict[str, str]] = None
    ) -> ProjectResult:
        """
        Analyze a single Terraform plan.

        Args:
            plan: Parsed plan.json content
            project_name: Display name for the project
            project_path: Path to the project
            environment: Environment name
            tags: Optional tags

        Returns:
            ProjectResult with cost analysis
        """
        payload = {
            "iac_plan": plan,
            "iac_type": "terraform",
            "budget_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "context": {
                "environment": environment,
                "tags": tags or {}
            },
            "options": {
                "include_calculations": True,
                "skip_budget": True,
                "skip_guardrails": True,
                "skip_narrative": True,
                "auto_approve": False
            }
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=self.timeout
            )

            if response.status_code == 403:
                return ProjectResult(
                    name=project_name,
                    path=project_path,
                    status="error",
                    decision="ERROR",
                    monthly_cost=0,
                    hourly_cost=0,
                    total_resources=0,
                    priced_resources=0,
                    failed_resources=0,
                    warned_resources=0,
                    resources=[],
                    error="Invalid API key"
                )

            if response.status_code != 200:
                return ProjectResult(
                    name=project_name,
                    path=project_path,
                    status="error",
                    decision="ERROR",
                    monthly_cost=0,
                    hourly_cost=0,
                    total_resources=0,
                    priced_resources=0,
                    failed_resources=0,
                    warned_resources=0,
                    resources=[],
                    error=f"API returned HTTP {response.status_code}"
                )

            data = response.json()
            return self._parse_response(data, project_name, project_path)

        except requests.exceptions.Timeout:
            return ProjectResult(
                name=project_name,
                path=project_path,
                status="error",
                decision="ERROR",
                monthly_cost=0,
                hourly_cost=0,
                total_resources=0,
                priced_resources=0,
                failed_resources=0,
                warned_resources=0,
                resources=[],
                error="Request timeout"
            )
        except requests.exceptions.RequestException as e:
            return ProjectResult(
                name=project_name,
                path=project_path,
                status="error",
                decision="ERROR",
                monthly_cost=0,
                hourly_cost=0,
                total_resources=0,
                priced_resources=0,
                failed_resources=0,
                warned_resources=0,
                resources=[],
                error=str(e)
            )

    def _parse_response(
        self,
        data: Dict[str, Any],
        project_name: str,
        project_path: str
    ) -> ProjectResult:
        """Parse API response into ProjectResult"""
        summary = data.get("summary", {})

        resources = []
        for res in data.get("resources", []):
            resources.append(ResourceResult(
                resource_id=res.get("resource_id", ""),
                resource_type=res.get("resource_type", ""),
                provider=res.get("provider", ""),
                region=res.get("region", ""),
                monthly_cost=res.get("monthly_cost", 0),
                hourly_cost=res.get("hourly_cost", 0),
                success=res.get("success", False),
                error=res.get("error", {}).get("message") if res.get("error") else None,
                warnings=[w.get("message") for w in res.get("warnings", [])]
            ))

        return ProjectResult(
            name=project_name,
            path=project_path,
            status=data.get("status", "unknown"),
            decision=data.get("decision", "UNKNOWN"),
            monthly_cost=summary.get("total_monthly_cost", 0),
            hourly_cost=summary.get("total_hourly_cost", 0),
            total_resources=summary.get("total_resources", 0),
            priced_resources=summary.get("priced_resources", 0),
            failed_resources=summary.get("failed_resources", 0),
            warned_resources=summary.get("warned_resources", 0),
            resources=resources
        )

    def analyze_projects(
        self,
        projects: List[Dict[str, Any]]
    ) -> AnalysisResult:
        """
        Analyze multiple projects.

        Args:
            projects: List of dicts with 'name', 'path', and 'plan' keys

        Returns:
            Combined AnalysisResult
        """
        results = []
        total_monthly = 0
        total_hourly = 0
        overall_decision = "ALLOW"

        for project in projects:
            result = self.analyze_plan(
                plan=project["plan"],
                project_name=project.get("name", project["path"]),
                project_path=project["path"]
            )
            results.append(result)

            if result.status != "error":
                total_monthly += result.monthly_cost
                total_hourly += result.hourly_cost

            # Determine overall decision (most restrictive wins)
            if result.decision == "DENY":
                overall_decision = "DENY"
            elif result.decision == "WARN" and overall_decision != "DENY":
                overall_decision = "WARN"

        status = "success" if all(r.status != "error" for r in results) else "partial"

        return AnalysisResult(
            status=status,
            total_monthly_cost=total_monthly,
            total_hourly_cost=total_hourly,
            projects=results,
            decision=overall_decision
        )
