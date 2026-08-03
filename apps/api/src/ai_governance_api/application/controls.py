"""Control catalog use cases and the application-owned ports they consume."""

from typing import Protocol

from governance_schemas import (
    ControlCatalog,
    ControlContext,
    ControlCrosswalk,
    ControlDefinition,
    ControlEvaluation,
    InitiativeControlReport,
)

from ai_governance_api.errors import ApplicationError, ErrorKind


class InitiativeControlContextStore(Protocol):
    """Persistence operations required to evaluate initiative controls."""

    async def get(self, initiative_id: str) -> ControlContext | None:
        """Return normalized control facts or ``None`` when absent."""
        ...


class ControlCatalogPort(Protocol):
    """Versioned control catalog operations consumed by application use cases."""

    @property
    def catalog(self) -> ControlCatalog:
        """Return catalog metadata and immutable definitions."""
        ...

    def list_controls(self) -> tuple[ControlDefinition, ...]:
        """Return every control in stable catalog order."""
        ...

    def evaluate(self, context: ControlContext) -> tuple[ControlEvaluation, ...]:
        """Evaluate every control for one normalized context."""
        ...


class ControlCrosswalkPort(Protocol):
    """Versioned, non-authoritative external-framework crosswalk."""

    @property
    def crosswalk(self) -> ControlCrosswalk:
        """Return crosswalk metadata and immutable framework references."""
        ...


class ListControlCatalog:
    """Return the active, versioned control catalog."""

    def __init__(self, catalog: ControlCatalogPort) -> None:
        """Initialize the query with its catalog port."""
        self._catalog = catalog

    def execute(self) -> ControlCatalog:
        """Return the complete active catalog without infrastructure details."""
        return self._catalog.catalog


class GetControlCrosswalk:
    """Return the active, versioned external-framework crosswalk."""

    def __init__(self, crosswalk: ControlCrosswalkPort) -> None:
        """Initialize the query with its crosswalk port."""
        self._crosswalk = crosswalk

    def execute(self) -> ControlCrosswalk:
        """Return the complete active crosswalk without infrastructure details."""
        return self._crosswalk.crosswalk


class EvaluateInitiativeControls:
    """Derive explainable control applicability for one initiative."""

    def __init__(
        self,
        store: InitiativeControlContextStore,
        catalog: ControlCatalogPort,
    ) -> None:
        """Initialize the query with context and catalog ports."""
        self._store = store
        self._catalog = catalog

    async def execute(self, initiative_id: str) -> InitiativeControlReport:
        """Return a versioned report or a stable not-found application error."""
        context = await self._store.get(initiative_id)
        if context is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Initiative not found")
        catalog = self._catalog.catalog
        return InitiativeControlReport(
            initiative_id=initiative_id,
            catalog_id=catalog.catalog_id,
            catalog_version=catalog.version,
            controls=self._catalog.evaluate(context),
        )
