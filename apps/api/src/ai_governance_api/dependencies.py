"""FastAPI dependency wiring for application services."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from policy_engine import GovernanceControlCatalog, GovernancePolicyEngine
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.adapters import (
    ClamAVScanner,
    MicrosoftGraphCorporateDirectory,
    S3ObjectStorage,
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyEvidenceAudit,
    SqlAlchemyEvidenceStore,
    SqlAlchemyInitiativeControlContextStore,
    SqlAlchemyTransaction,
    YamlDirectoryAuthorizationCatalog,
)
from ai_governance_api.application import (
    ControlCatalogPort,
    CorporateDirectoryIdentityMismatch,
    CorporateDirectoryNotApplicable,
    CorporateDirectoryProfile,
    CorporateDirectoryResponseInvalid,
    CorporateDirectoryUnavailable,
    EvaluateInitiativeControls,
    ListAssessments,
    ListControlCatalog,
    ListEvidence,
    ResolveCorporateDirectory,
    ResolveDirectoryAuthorization,
    SaveAssessment,
    SubmitAssessment,
    UploadEvidence,
)
from ai_governance_api.auth import BEARER_CHALLENGE, BearerCredentials, get_principal
from ai_governance_api.config import Settings, get_settings
from ai_governance_api.database import get_db
from ai_governance_api.domain.directory_authorization import (
    DirectoryAuthorizationCatalog,
    DirectoryAuthorizationError,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.services import InitiativeService, InventoryService, PolicyEvaluator

DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@lru_cache
def get_policy_evaluator() -> PolicyEvaluator:
    """Return the default stateless policy evaluator."""
    return GovernancePolicyEngine()


@lru_cache
def get_control_catalog() -> ControlCatalogPort:
    """Load the packaged or explicitly configured control catalog once per process."""
    path = get_settings().control_catalog_path
    return (
        GovernanceControlCatalog.from_path(path)
        if path
        else GovernanceControlCatalog.from_package()
    )


PolicyEvaluatorDependency = Annotated[PolicyEvaluator, Depends(get_policy_evaluator)]
ControlCatalogDependency = Annotated[ControlCatalogPort, Depends(get_control_catalog)]


@lru_cache
def get_directory_authorization_catalog() -> DirectoryAuthorizationCatalog:
    """Load the packaged or explicitly configured Entra mapping catalog once."""
    path = get_settings().directory_authorization_catalog_path
    return (
        YamlDirectoryAuthorizationCatalog.from_path(path)
        if path
        else YamlDirectoryAuthorizationCatalog.from_package()
    )


DirectoryAuthorizationCatalogDependency = Annotated[
    DirectoryAuthorizationCatalog,
    Depends(get_directory_authorization_catalog),
]


def get_directory_authorization_resolver(
    catalog: DirectoryAuthorizationCatalogDependency,
    settings: SettingsDependency,
) -> ResolveDirectoryAuthorization:
    """Build the stateless capability resolver from immutable deployment policy."""
    return ResolveDirectoryAuthorization(
        catalog,
        guest_approvals_enabled=settings.oidc_guest_approvals_enabled,
    )


DirectoryAuthorizationResolverDependency = Annotated[
    ResolveDirectoryAuthorization,
    Depends(get_directory_authorization_resolver),
]


def get_corporate_directory_resolver(
    settings: SettingsDependency,
) -> ResolveCorporateDirectory | None:
    """Build Graph enrichment only when the deployment enables its OBO boundary."""
    if not settings.microsoft_graph_enabled:
        return None
    return ResolveCorporateDirectory(
        MicrosoftGraphCorporateDirectory(
            tenant_id=settings.oidc_entra_issuer_tenant_id,
            client_id=settings.microsoft_graph_client_id,
            client_secret=settings.microsoft_graph_client_secret,
            timeout_seconds=settings.microsoft_graph_timeout_seconds,
            max_pages=settings.microsoft_graph_max_pages,
            max_retry_after_seconds=settings.microsoft_graph_max_retry_after_seconds,
            max_response_bytes=settings.microsoft_graph_max_response_bytes,
        )
    )


CorporateDirectoryResolverDependency = Annotated[
    ResolveCorporateDirectory | None,
    Depends(get_corporate_directory_resolver),
]


async def get_corporate_directory_profile(
    principal: CurrentPrincipal,
    credentials: BearerCredentials,
    resolver: CorporateDirectoryResolverDependency,
) -> CorporateDirectoryProfile | None:
    """Enrich the current identity while mapping dependency failures safely."""
    if resolver is None:
        return None
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers=BEARER_CHALLENGE,
        )
    try:
        return await resolver.execute(principal, credentials.credentials)
    except CorporateDirectoryUnavailable as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Corporate directory unavailable",
            headers=headers,
        ) from exc
    except (
        CorporateDirectoryIdentityMismatch,
        CorporateDirectoryNotApplicable,
        CorporateDirectoryResponseInvalid,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Corporate directory response could not be trusted",
        ) from exc


CurrentCorporateDirectoryProfile = Annotated[
    CorporateDirectoryProfile | None,
    Depends(get_corporate_directory_profile),
]


async def get_authorized_principal(
    principal: CurrentPrincipal,
    directory_profile: CurrentCorporateDirectoryProfile,
    resolver: DirectoryAuthorizationResolverDependency,
) -> Principal:
    """Resolve catalog-derived capabilities for authorization-sensitive requests."""
    try:
        return resolver.execute(
            principal,
            group_object_ids=(
                directory_profile.group_object_ids
                if directory_profile is not None
                else frozenset()
            ),
        )
    except DirectoryAuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Directory authorization could not be trusted",
        ) from exc


CurrentAuthorizedPrincipal = Annotated[
    Principal,
    Depends(get_authorized_principal),
]


def get_initiative_service(
    session: DatabaseSession,
    policy_evaluator: PolicyEvaluatorDependency,
) -> InitiativeService:
    """Build the request-scoped initiative service."""
    return InitiativeService(session, policy_evaluator)


def get_inventory_service(session: DatabaseSession) -> InventoryService:
    """Build the request-scoped inventory service."""
    return InventoryService(session)


InitiativeServiceDependency = Annotated[InitiativeService, Depends(get_initiative_service)]
InventoryServiceDependency = Annotated[InventoryService, Depends(get_inventory_service)]


def get_save_assessment(session: DatabaseSession) -> SaveAssessment:
    """Build the request-scoped save-assessment use case at the composition root."""
    return SaveAssessment(
        SqlAlchemyAssessmentStore(session),
        SqlAlchemyAssessmentAudit(session),
        SqlAlchemyTransaction(session),
    )


def get_list_assessments(session: DatabaseSession) -> ListAssessments:
    """Build the request-scoped assessment query at the composition root."""
    return ListAssessments(SqlAlchemyAssessmentStore(session))


def get_submit_assessment(session: DatabaseSession) -> SubmitAssessment:
    """Build the request-scoped submit-assessment use case at the composition root."""
    return SubmitAssessment(
        SqlAlchemyAssessmentStore(session),
        SqlAlchemyAssessmentAudit(session),
        SqlAlchemyTransaction(session),
    )


SaveAssessmentDependency = Annotated[SaveAssessment, Depends(get_save_assessment)]
ListAssessmentsDependency = Annotated[ListAssessments, Depends(get_list_assessments)]
SubmitAssessmentDependency = Annotated[SubmitAssessment, Depends(get_submit_assessment)]


def get_list_control_catalog(catalog: ControlCatalogDependency) -> ListControlCatalog:
    """Build the active control-catalog query."""
    return ListControlCatalog(catalog)


def get_evaluate_initiative_controls(
    session: DatabaseSession,
    catalog: ControlCatalogDependency,
) -> EvaluateInitiativeControls:
    """Build the initiative applicability query at the composition root."""
    return EvaluateInitiativeControls(
        SqlAlchemyInitiativeControlContextStore(session),
        catalog,
    )


ListControlCatalogDependency = Annotated[
    ListControlCatalog,
    Depends(get_list_control_catalog),
]
EvaluateInitiativeControlsDependency = Annotated[
    EvaluateInitiativeControls,
    Depends(get_evaluate_initiative_controls),
]


@lru_cache
def get_malware_scanner() -> ClamAVScanner:
    """Build the process-wide mandatory malware scanner adapter."""
    settings = get_settings()
    return ClamAVScanner(
        host=settings.malware_scanner_host,
        port=settings.malware_scanner_port,
        connect_timeout_seconds=settings.malware_scanner_connect_timeout_seconds,
        scan_timeout_seconds=settings.malware_scanner_scan_timeout_seconds,
    )


@lru_cache
def get_object_storage() -> S3ObjectStorage:
    """Build the process-wide S3-compatible evidence storage adapter."""
    settings = get_settings()
    return S3ObjectStorage(
        bucket=settings.object_storage_bucket,
        region=settings.object_storage_region,
        endpoint_url=settings.object_storage_endpoint_url,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        auto_create_bucket=settings.object_storage_auto_create_bucket,
        server_side_encryption=settings.object_storage_server_side_encryption,
        connect_timeout_seconds=settings.object_storage_connect_timeout_seconds,
        read_timeout_seconds=settings.object_storage_read_timeout_seconds,
    )


MalwareScannerDependency = Annotated[ClamAVScanner, Depends(get_malware_scanner)]
ObjectStorageDependency = Annotated[S3ObjectStorage, Depends(get_object_storage)]


def get_upload_evidence(
    session: DatabaseSession,
    scanner: MalwareScannerDependency,
    object_storage: ObjectStorageDependency,
) -> UploadEvidence:
    """Build the secure upload use case at the composition root."""
    settings = get_settings()
    return UploadEvidence(
        SqlAlchemyEvidenceStore(session),
        scanner,
        object_storage,
        SqlAlchemyEvidenceAudit(session),
        SqlAlchemyTransaction(session),
        max_bytes=settings.evidence_max_bytes,
        allowed_content_types=settings.evidence_allowed_content_type_set,
    )


def get_list_evidence(session: DatabaseSession) -> ListEvidence:
    """Build the uploaded evidence metadata query."""
    return ListEvidence(SqlAlchemyEvidenceStore(session))


UploadEvidenceDependency = Annotated[UploadEvidence, Depends(get_upload_evidence)]
ListEvidenceDependency = Annotated[ListEvidence, Depends(get_list_evidence)]
