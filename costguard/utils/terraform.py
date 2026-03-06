"""Terraform plan utilities"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional


def load_plan_json(path: str) -> Dict[str, Any]:
    """
    Load a Terraform plan JSON file.

    Args:
        path: Path to plan.json file or directory containing it

    Returns:
        Parsed plan JSON

    Raises:
        FileNotFoundError: If plan file not found
        json.JSONDecodeError: If file is not valid JSON
    """
    plan_path = Path(path)

    # If path is a directory, look for plan.json
    if plan_path.is_dir():
        plan_path = plan_path / "plan.json"

    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    with open(plan_path) as f:
        return json.load(f)


def find_plan_files(directory: str, recursive: bool = False) -> List[Path]:
    """
    Find all plan.json files in a directory.

    Args:
        directory: Directory to search
        recursive: Search recursively

    Returns:
        List of paths to plan.json files
    """
    base = Path(directory)
    pattern = "**/plan.json" if recursive else "*/plan.json"

    return list(base.glob(pattern))


def get_plan_provider(plan: Dict[str, Any]) -> str:
    """
    Detect the cloud provider from a plan.

    Args:
        plan: Parsed plan JSON

    Returns:
        Provider name (aws, gcp, azure, unknown)
    """
    provider_config = plan.get("configuration", {}).get("provider_config", {})

    if "aws" in provider_config:
        return "aws"
    elif "google" in provider_config:
        return "gcp"
    elif "azurerm" in provider_config:
        return "azure"
    else:
        return "unknown"


def get_plan_resources(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract resource changes from a plan.

    Args:
        plan: Parsed plan JSON

    Returns:
        List of resource change objects
    """
    return plan.get("resource_changes", [])


def count_resources(plan: Dict[str, Any]) -> Dict[str, int]:
    """
    Count resources by action type.

    Args:
        plan: Parsed plan JSON

    Returns:
        Dict with counts: create, update, delete, no-op
    """
    counts = {
        "create": 0,
        "update": 0,
        "delete": 0,
        "no-op": 0,
        "total": 0
    }

    for resource in plan.get("resource_changes", []):
        actions = resource.get("change", {}).get("actions", [])
        counts["total"] += 1

        if "create" in actions:
            counts["create"] += 1
        elif "delete" in actions:
            counts["delete"] += 1
        elif "update" in actions:
            counts["update"] += 1
        else:
            counts["no-op"] += 1

    return counts


def validate_plan(plan: Dict[str, Any]) -> tuple:
    """
    Validate a Terraform plan structure.

    Args:
        plan: Parsed plan JSON

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["format_version", "terraform_version"]

    for field in required_fields:
        if field not in plan:
            return False, f"Missing required field: {field}"

    # Check format version
    format_version = plan.get("format_version", "")
    if not format_version.startswith("1."):
        return False, f"Unsupported format version: {format_version}"

    return True, None
