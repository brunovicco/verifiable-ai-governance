"""SQLAlchemy authorization for initiative advisory finding reviews."""

from uuid import UUID

from governance_schemas import GovernanceFindingType
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewDependencyError,
)
from ai_governance_api.models import Initiative


class SqlAlchemyInitiativeFindingReviewAuthorizer:
    """Authorize advisory review for an existing initiative owner or administrator."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the reader without opening a database connection."""
        self._session_factory = session_factory

    async def can_review(
        self,
        *,
        actor_id: str,
        subject_id: str,
        finding_type: GovernanceFindingType,
        is_admin: bool,
    ) -> bool:
        """Resolve minimal initiative ownership and fail closed for every other subject."""
        if (
            not _bounded_identifier(actor_id)
            or _canonical_uuid(subject_id) is None
            or not isinstance(finding_type, GovernanceFindingType)
            or not isinstance(is_admin, bool)
        ):
            return False
        try:
            async with self._session_factory() as session:
                owner_id = await session.scalar(
                    select(Initiative.business_owner_id).where(Initiative.id == subject_id)
                )
        except SQLAlchemyError as exc:
            raise GovernanceFindingReviewDependencyError(
                "Initiative finding review authorization is unavailable"
            ) from exc
        return owner_id is not None and (is_admin or owner_id == actor_id)


def _bounded_identifier(value: str) -> bool:
    """Accept the same bounded printable actor identity required by review access."""
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 200
        and value == value.strip()
        and all(character.isprintable() and not character.isspace() for character in value)
    )


def _canonical_uuid(value: str) -> str | None:
    """Return a canonical non-nil initiative UUID or no subject identity."""
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        return None
    canonical = str(parsed)
    return canonical if parsed.int != 0 and canonical == value else None
