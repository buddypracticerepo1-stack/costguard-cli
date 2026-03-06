"""CostGuard configuration schema using Pydantic"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Single project configuration"""
    path: str = Field(..., description="Path to Terraform directory")
    name: Optional[str] = Field(None, description="Display name")
    terraform_var_files: Optional[List[str]] = Field(None, description="Terraform var files")
    terraform_vars: Optional[Dict[str, str]] = Field(None, description="Inline Terraform variables")
    terraform_workspace: Optional[str] = Field(None, description="Terraform workspace")
    usage_file: Optional[str] = Field(None, description="Path to usage file for usage-based pricing")
    skip: bool = Field(False, description="Skip this project")

    def get_name(self) -> str:
        """Get display name, defaulting to path"""
        return self.name or self.path


class SettingsConfig(BaseModel):
    """Global settings"""
    api_url: str = Field(
        "https://4tm9xj5nv0.execute-api.us-east-1.amazonaws.com/rnd",
        description="CostGuard API URL"
    )
    currency: str = Field("USD", description="Display currency")
    fail_on_deny: bool = Field(True, description="Exit 1 if denied")


class ThresholdsConfig(BaseModel):
    """Cost thresholds"""
    warn_monthly_cost: Optional[float] = Field(None, description="Warn if cost exceeds")
    fail_monthly_cost: Optional[float] = Field(None, description="Fail if cost exceeds")
    warn_cost_increase_percent: Optional[float] = Field(None, description="Warn on % increase")
    fail_cost_increase_percent: Optional[float] = Field(None, description="Fail on % increase")


class AutodetectConfig(BaseModel):
    """Auto-detection settings"""
    enabled: bool = Field(False, description="Enable auto-detection")
    paths: List[str] = Field(default_factory=list, description="Glob patterns")
    exclude: List[str] = Field(default_factory=list, description="Exclude patterns")


class OutputConfig(BaseModel):
    """Output formatting"""
    format: str = Field("table", description="Output format")
    show_resources: bool = Field(True, description="Show resource breakdown")
    show_unchanged: bool = Field(False, description="Show $0 resources")
    group_by: str = Field("project", description="Grouping method")


class CIConfig(BaseModel):
    """CI integration settings"""
    post_comment: bool = Field(True, description="Auto-post PR comment")
    update_existing: bool = Field(True, description="Update existing comment")
    collapse_resources: bool = Field(True, description="Collapsible resources")


class CostGuardConfig(BaseModel):
    """Root configuration"""
    version: int = Field(1, description="Config version")
    projects: List[ProjectConfig] = Field(default_factory=list, description="Projects")
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    autodetect: AutodetectConfig = Field(default_factory=AutodetectConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    ci: CIConfig = Field(default_factory=CIConfig)

    def get_active_projects(self) -> List[ProjectConfig]:
        """Get non-skipped projects"""
        return [p for p in self.projects if not p.skip]
