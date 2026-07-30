from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import Scenario


def default_scenario_dir() -> Path:
    """Resolve the scenario directory.

    Honors `VOICE_EVAL_SCENARIO_DIR` first. Falls back to the repository
    scenario directory for editable installs, then to scenarios bundled
    inside the installed package. The final current-working-directory
    fallback remains useful for ad-hoc source deployments.
    """
    env_dir = os.getenv("VOICE_EVAL_SCENARIO_DIR")
    if env_dir:
        return Path(env_dir)

    repo_relative = Path(__file__).resolve().parents[2] / "scenarios"
    if repo_relative.is_dir():
        return repo_relative

    packaged = Path(__file__).resolve().parent / "scenario_data"
    if packaged.is_dir():
        return packaged

    return Path.cwd() / "scenarios"


def load_scenario(name: str, directory: Path | None = None) -> Scenario:
    directory = directory or default_scenario_dir()
    path = directory / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Scenario not found: {name}")
    return Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def list_scenarios(directory: Path | None = None) -> list[str]:
    directory = directory or default_scenario_dir()
    return sorted(path.stem for path in directory.glob("*.yaml"))
