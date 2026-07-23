from pathlib import Path

import yaml
from pydantic import ValidationError

from cleanroom.models.policy import SanitizationPolicy


class PolicyError(ValueError):
    pass


def load_policy(path: Path) -> SanitizationPolicy:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise PolicyError("policy must be a YAML mapping")
        return SanitizationPolicy.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise PolicyError(f"invalid policy {path}: {exc}") from exc
