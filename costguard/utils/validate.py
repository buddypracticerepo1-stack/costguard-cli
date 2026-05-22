"""Local validation of CostGuard request payloads.

Fails loudly with helpful messages when input is wrong, instead of letting
the API return opaque 500s or unhelpful 400s. Mirrors the server-side
validations so users see the error before a network round-trip.
"""

from typing import Any, Dict, Optional

from .detect import VALID_IAC_TYPES


class ValidationError(ValueError):
    """Raised when a payload would be rejected by CostGuard's API."""


def validate_payload(body: Dict[str, Any], region: Optional[str] = None) -> None:
    """Validate a CostGuard request body. Raises ValidationError on first issue.

    Catches the bugs we know cause server-side 500s or silent 200+error envelopes:
      - iac_type missing or unknown
      - iac_plan empty
      - CFN iac_plan sent as a string (would crash the CFN parser)
      - CFN without explicit region (CFN has no per-resource region field)
    """
    iac_type = body.get("iac_type")
    if iac_type not in VALID_IAC_TYPES:
        raise ValidationError(
            f"iac_type={iac_type!r} is not supported. "
            f"Valid values: {sorted(VALID_IAC_TYPES)}. "
            "(For CFN changesets use iac_type='cloudformation' + iac_format='changeset'.)"
        )

    iac_plan = body.get("iac_plan")
    if not iac_plan:
        raise ValidationError("iac_plan is empty — nothing to analyze.")

    if iac_type == "cloudformation" and isinstance(iac_plan, str):
        raise ValidationError(
            "iac_plan is a string but CostGuard's CFN parser expects a dict. "
            "Parse the YAML/JSON locally and send the parsed object."
        )

    if iac_type == "cloudformation" and not region:
        raise ValidationError(
            "--region is required for CloudFormation. "
            "(CFN doesn't carry per-resource region; the server needs it explicitly.)"
        )
