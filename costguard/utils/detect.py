"""Auto-detect IaC type and normalize input for CostGuard API.

The CostGuard API requires iac_type to be one of {"terraform", "cloudformation"}
and iac_plan to be a JSON-serializable dict. Users may have:
  - A terraform `plan.json` (from `terraform show -json`)
  - A CloudFormation template (YAML or JSON)
  - A CloudFormation describe-change-set output (JSON)

This module detects the type from content and returns a normalized payload
ready to POST. It never sends a YAML string as iac_plan — that crashes the
CFN parser server-side with `'str' object has no attribute 'get'`.
"""

import json
from pathlib import Path
from typing import Any, Dict

import yaml


VALID_IAC_TYPES = {"terraform", "cloudformation"}


def _is_terraform_plan(body: Dict[str, Any]) -> bool:
    """A terraform plan JSON has at least one of these top-level keys."""
    return any(
        k in body
        for k in ("format_version", "terraform_version", "resource_changes", "planned_values")
    )


def _is_cfn_template(body: Dict[str, Any]) -> bool:
    """A CFN template has Resources at the top level (and usually AWSTemplateFormatVersion)."""
    return "AWSTemplateFormatVersion" in body or "Resources" in body


def _is_cfn_changeset(body: Dict[str, Any]) -> bool:
    """A `describe-change-set` output has Changes[] and ChangeSetName."""
    return "Changes" in body and ("ChangeSetName" in body or "ChangeSetId" in body)


def detect_payload(path: str) -> Dict[str, Any]:
    """Read a file from `path` and return a normalized CostGuard request payload.

    The returned dict has at least:
      - iac_type: "terraform" | "cloudformation"
      - iac_plan: dict (never a YAML string — always parsed)
      - iac_format: "plan" | "template" | "changeset" (CFN sub-shape)

    Raises ValueError if the file content doesn't look like a supported IaC plan.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")

    # Try JSON first (terraform plans and CFN changesets are JSON).
    # Fall back to YAML for CFN templates.
    body: Any
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        try:
            body = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ValueError(f"{path} is neither valid JSON nor valid YAML: {e}") from e

    if not isinstance(body, dict):
        raise ValueError(f"{path} parsed to {type(body).__name__}, expected a dict")

    if _is_terraform_plan(body):
        return {"iac_type": "terraform", "iac_format": "plan", "iac_plan": body}

    if _is_cfn_changeset(body):
        # CG's CFN parser looks for "Changes" directly on iac_plan, not
        # inside a nested wrapper. Send the describe-change-set output as
        # iac_plan verbatim. (Requires `aws cloudformation describe-change-set
        # --include-property-values` so AfterContext.Properties is present.)
        return {
            "iac_type": "cloudformation",
            "iac_format": "changeset",
            "iac_plan": body,
        }

    if _is_cfn_template(body):
        return {"iac_type": "cloudformation", "iac_format": "template", "iac_plan": body}

    raise ValueError(
        f"Could not detect IaC type for {path}. Expected one of: "
        "terraform plan JSON (has format_version/resource_changes), "
        "CloudFormation template (has Resources/AWSTemplateFormatVersion), or "
        "CloudFormation describe-change-set output (has Changes and ChangeSetName)."
    )
