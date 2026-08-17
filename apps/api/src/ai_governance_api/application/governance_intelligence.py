"""Consumer-owned port for non-authoritative Governance Intelligence analysis."""

from typing import Protocol

from governance_schemas import GovernanceFindingCandidate, GovernanceSourceReference


class GovernanceIntelligencePort(Protocol):
    """Analyze governed subjects and return untrusted advisory candidates only."""

    async def analyze_policy(
        self,
        *,
        subject_id: str,
        sources: tuple[GovernanceSourceReference, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest policy interpretations without deciding policy applicability."""
        ...

    async def identify_risks(
        self,
        *,
        subject_id: str,
        sources: tuple[GovernanceSourceReference, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest risk candidates without assigning a governed risk state."""
        ...

    async def suggest_controls(
        self,
        *,
        subject_id: str,
        sources: tuple[GovernanceSourceReference, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest control candidates without approving or activating controls."""
        ...

    async def analyze_evidence(
        self,
        *,
        subject_id: str,
        sources: tuple[GovernanceSourceReference, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Interpret source references without converting interpretations into evidence."""
        ...

    async def assist_intake(
        self,
        *,
        subject_id: str,
        sources: tuple[GovernanceSourceReference, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest intake data without mutating the governed system of record."""
        ...
