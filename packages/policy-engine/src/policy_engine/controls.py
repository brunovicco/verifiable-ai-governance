"""Fail-closed YAML loading and deterministic control applicability evaluation."""

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from governance_schemas import (
    ControlApplicability,
    ControlCatalog,
    ControlContext,
    ControlDefinition,
    ControlEvaluation,
)
from pydantic import ValidationError

EXPECTED_BASELINE_CONTROLS = 25


class ControlCatalogError(ValueError):
    """Raised when a control catalog cannot be loaded or trusted."""


class GovernanceControlCatalog:
    """Provide immutable controls and explain their applicability to initiatives."""

    def __init__(self, catalog: ControlCatalog) -> None:
        """Initialize the evaluator with an already validated catalog."""
        if len(catalog.controls) != EXPECTED_BASELINE_CONTROLS:
            raise ControlCatalogError(
                f"Baseline catalog must contain {EXPECTED_BASELINE_CONTROLS} controls"
            )
        self._catalog = catalog

    @property
    def catalog(self) -> ControlCatalog:
        """Return the immutable versioned catalog."""
        return self._catalog

    @classmethod
    def from_package(cls) -> "GovernanceControlCatalog":
        """Load the baseline catalog bundled with the policy-engine package."""
        resource = files("policy_engine").joinpath("control_catalog.yaml")
        try:
            content = resource.read_text(encoding="utf-8")
        except OSError as exc:
            raise ControlCatalogError("Packaged control catalog could not be read") from exc
        return cls.from_yaml(content)

    @classmethod
    def from_path(cls, path: str | Path) -> "GovernanceControlCatalog":
        """Load an explicitly configured catalog without falling back on failure."""
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            message = f"Configured control catalog could not be read: {path}"
            raise ControlCatalogError(message) from exc
        return cls.from_yaml(content)

    @classmethod
    def from_yaml(cls, content: str) -> "GovernanceControlCatalog":
        """Parse and validate a YAML catalog, rejecting malformed or duplicate data."""
        try:
            raw: Any = yaml.safe_load(content)
            catalog = ControlCatalog.model_validate(raw)
        except (yaml.YAMLError, ValidationError, TypeError) as exc:
            raise ControlCatalogError("Control catalog validation failed") from exc
        return cls(catalog)

    def list_controls(self) -> tuple[ControlDefinition, ...]:
        """Return controls in their stable catalog order."""
        return self._catalog.controls

    def evaluate(self, context: ControlContext) -> tuple[ControlEvaluation, ...]:
        """Evaluate every control without I/O or mutable process state."""
        return tuple(self._evaluate_control(control, context) for control in self._catalog.controls)

    @staticmethod
    def _evaluate_control(
        control: ControlDefinition,
        context: ControlContext,
    ) -> ControlEvaluation:
        rule = control.applicability
        if rule.always:
            return ControlEvaluation(
                control=control,
                applicable=True,
                reasons=("Controle baseline aplicável a toda iniciativa de IA.",),
            )

        clauses = _selector_clauses(rule, context)
        applicable = (
            all(result for result, _, _ in clauses)
            if rule.match == "all"
            else any(result for result, _, _ in clauses)
        )
        if applicable:
            reasons = tuple(matched for result, matched, _ in clauses if result)
        else:
            reasons = tuple(unmet for result, _, unmet in clauses if not result)
        return ControlEvaluation(
            control=control,
            applicable=applicable,
            reasons=reasons or ("Nenhum gatilho de aplicabilidade foi atendido.",),
        )


def _selector_clauses(
    rule: ControlApplicability,
    context: ControlContext,
) -> list[tuple[bool, str, str]]:
    """Build evaluated selector clauses with human-readable matched and unmet reasons."""
    clauses: list[tuple[bool, str, str]] = []
    if rule.risk_tiers:
        matched = context.risk_tier in rule.risk_tiers
        clauses.append(
            (
                matched,
                f"Tier de risco {context.risk_tier.value} exige o controle.",
                "Tier de risco fora do escopo configurado.",
            )
        )
    if rule.flags_any:
        enabled = [flag.value for flag in rule.flags_any if getattr(context, flag.value)]
        clauses.append(
            (
                bool(enabled),
                f"Gatilhos declarados: {', '.join(enabled)}.",
                "Nenhum dos gatilhos booleanos configurados foi declarado.",
            )
        )
    if rule.flags_all:
        missing = [flag.value for flag in rule.flags_all if not getattr(context, flag.value)]
        clauses.append(
            (
                not missing,
                "Todos os gatilhos obrigatórios foram declarados.",
                f"Gatilhos obrigatórios ausentes: {', '.join(missing)}.",
            )
        )
    if rule.decision_impacts:
        matched = context.decision_impact in rule.decision_impacts
        clauses.append(
            (
                matched,
                f"Impacto {context.decision_impact.value} exige o controle.",
                "Impacto da decisão fora do escopo configurado.",
            )
        )
    if rule.data_classifications:
        matched = context.data_classification in rule.data_classifications
        clauses.append(
            (
                matched,
                f"Classificação {context.data_classification.value} exige o controle.",
                "Classificação dos dados fora do escopo configurado.",
            )
        )
    if rule.autonomy_levels:
        matched = context.autonomy_level in rule.autonomy_levels
        clauses.append(
            (
                matched,
                f"Autonomia {context.autonomy_level.value} exige o controle.",
                "Nível de autonomia fora do escopo configurado.",
            )
        )
    if rule.hosting_models:
        matched = context.hosting_model in rule.hosting_models
        clauses.append(
            (
                matched,
                f"Hospedagem {context.hosting_model.value} exige o controle.",
                "Modelo de hospedagem fora do escopo configurado.",
            )
        )
    return clauses
