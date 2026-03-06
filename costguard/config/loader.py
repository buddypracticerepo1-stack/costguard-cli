"""Load and parse costguard.yml configuration"""

import os
import glob
from pathlib import Path
from typing import Optional

import yaml

from .schema import CostGuardConfig, ProjectConfig


DEFAULT_CONFIG_FILES = ["costguard.yml", "costguard.yaml", ".costguard.yml"]


def find_config_file(directory: str = ".") -> Optional[Path]:
    """Find costguard config file in directory"""
    for name in DEFAULT_CONFIG_FILES:
        path = Path(directory) / name
        if path.exists():
            return path
    return None


def load_config(config_path: Optional[str] = None, directory: str = ".") -> CostGuardConfig:
    """
    Load configuration from file or use defaults.

    Args:
        config_path: Explicit path to config file
        directory: Directory to search for config file

    Returns:
        CostGuardConfig object
    """
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
    else:
        path = find_config_file(directory)

    if path:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        config = CostGuardConfig(**data)
    else:
        # No config file, use defaults
        config = CostGuardConfig()

    # Handle auto-detection if enabled
    if config.autodetect.enabled and not config.projects:
        config.projects = autodetect_projects(
            directory,
            config.autodetect.paths,
            config.autodetect.exclude
        )

    return config


def autodetect_projects(
    base_dir: str,
    patterns: list,
    exclude: list
) -> list:
    """
    Auto-detect Terraform projects based on glob patterns.

    Args:
        base_dir: Base directory to search
        patterns: Glob patterns to match
        exclude: Patterns to exclude

    Returns:
        List of ProjectConfig objects
    """
    projects = []
    found_paths = set()

    for pattern in patterns:
        full_pattern = os.path.join(base_dir, pattern)
        for match in glob.glob(full_pattern, recursive=True):
            path = Path(match)

            # Check if it's a directory with .tf files
            if path.is_dir():
                tf_files = list(path.glob("*.tf"))
                if tf_files:
                    rel_path = str(path.relative_to(base_dir))

                    # Check exclusions
                    excluded = False
                    for exc in exclude:
                        if glob.fnmatch.fnmatch(rel_path, exc):
                            excluded = True
                            break

                    if not excluded and rel_path not in found_paths:
                        found_paths.add(rel_path)
                        projects.append(ProjectConfig(
                            path=rel_path,
                            name=rel_path.replace("/", " / ").title()
                        ))

    return projects


def get_api_key() -> Optional[str]:
    """Get API key from environment or config"""
    # Check environment variable first
    api_key = os.environ.get("COSTGUARD_API_KEY")
    if api_key:
        return api_key

    # Check config file in home directory
    config_dir = Path.home() / ".costguard"
    config_file = config_dir / "credentials"

    if config_file.exists():
        with open(config_file) as f:
            for line in f:
                if line.startswith("api_key="):
                    return line.split("=", 1)[1].strip()

    return None


def save_api_key(api_key: str) -> None:
    """Save API key to config file"""
    config_dir = Path.home() / ".costguard"
    config_dir.mkdir(exist_ok=True)

    config_file = config_dir / "credentials"
    with open(config_file, "w") as f:
        f.write(f"api_key={api_key}\n")

    # Set restrictive permissions
    os.chmod(config_file, 0o600)
