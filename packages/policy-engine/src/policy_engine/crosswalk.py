"""Fail-closed YAML loading for the non-authoritative external-framework crosswalk."""

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from governance_schemas import ControlCatalog, ControlCrosswalk
from pydantic import ValidationError


class ControlCrosswalkError(ValueError):
    """Raised when a control crosswalk cannot be loaded or trusted."""


class GovernanceControlCrosswalk:
    """Provide the immutable, non-authoritative control-to-framework crosswalk."""

    def __init__(self, crosswalk: ControlCrosswalk, catalog: ControlCatalog) -> None:
        """Initialize with an already validated crosswalk and the catalog it must match."""
        known_ids = {control.control_id for control in catalog.controls}
        unknown = [
            entry.control_id for entry in crosswalk.entries if entry.control_id not in known_ids
        ]
        if unknown:
            raise ControlCrosswalkError(
                f"Crosswalk references unknown control IDs: {', '.join(unknown)}"
            )
        self._crosswalk = crosswalk

    @property
    def crosswalk(self) -> ControlCrosswalk:
        """Return the immutable versioned crosswalk."""
        return self._crosswalk

    @classmethod
    def from_package(cls, catalog: ControlCatalog) -> "GovernanceControlCrosswalk":
        """Load the baseline crosswalk bundled with the policy-engine package."""
        resource = files("policy_engine").joinpath("control_crosswalk.yaml")
        try:
            content = resource.read_text(encoding="utf-8")
        except OSError as exc:
            raise ControlCrosswalkError("Packaged control crosswalk could not be read") from exc
        return cls.from_yaml(content, catalog)

    @classmethod
    def from_path(
        cls, path: str | Path, catalog: ControlCatalog
    ) -> "GovernanceControlCrosswalk":
        """Load an explicitly configured crosswalk without falling back on failure."""
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            message = f"Configured control crosswalk could not be read: {path}"
            raise ControlCrosswalkError(message) from exc
        return cls.from_yaml(content, catalog)

    @classmethod
    def from_yaml(cls, content: str, catalog: ControlCatalog) -> "GovernanceControlCrosswalk":
        """Parse and validate a YAML crosswalk, rejecting malformed or unknown data."""
        try:
            raw: Any = yaml.safe_load(content)
            crosswalk = ControlCrosswalk.model_validate(raw)
        except (yaml.YAMLError, ValidationError, TypeError) as exc:
            raise ControlCrosswalkError("Control crosswalk validation failed") from exc
        return cls(crosswalk, catalog)
