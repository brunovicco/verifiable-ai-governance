"""FastAPI dependency wiring for application services."""

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from policy_engine import (
    GovernanceControlCatalog,
    GovernanceControlCrosswalk,
    GovernancePolicyEngine,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.adapters import (
    ClamAVScanner,
    MicrosoftGraphCorporateDirectory,
    PolicyModelRouterHttpAdapter,
    S3ObjectStorage,
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyDashboardStore,
    SqlAlchemyDirectoryAccessAudit,
    SqlAlchemyDirectoryAccessCacheInvalidation,
    SqlAlchemyDirectoryAccessReader,
    SqlAlchemyDirectoryAccessStore,
    SqlAlchemyDirectoryAccessTransaction,
    SqlAlchemyDirectoryAuthorizationCache,
    SqlAlchemyDirectoryAuthorizationCacheAudit,
    SqlAlchemyDirectoryAuthorizationCacheReader,
    SqlAlchemyDirectoryAuthorizationCacheTransaction,
    SqlAlchemyEvidenceAudit,
    SqlAlchemyEvidenceStore,
    SqlAlchemyIncidentAudit,
    SqlAlchemyIncidentRepository,
    SqlAlchemyInitiativeControlContextStore,
    SqlAlchemyModelRoutingAudit,
    SqlAlchemyModelRoutingDecisionStore,
    SqlAlchemyModelRoutingScopeReader,
    SqlAlchemyTransaction,
    YamlDirectoryAuthorizationCatalog,
)
from ai_governance_api.adapters.runtime_authorization_issuer import (
    build_runtime_authorization_issuer,
)
from ai_governance_api.adapters.runtime_control_persistence import (
    SqlAlchemyRuntimeControlAudit,
    SqlAlchemyRuntimeControlRepository,
    SqlAlchemyRuntimeControlStateReader,
)
from ai_governance_api.adapters.runtime_control_redis import (
    InMemoryRuntimeControlStore,
    UnavailableRuntimeControlStore,
    build_redis_runtime_control_store,
)
from ai_governance_api.adapters.runtime_telemetry_persistence import (
    SqlAlchemyRuntimeTelemetryAudit,
    SqlAlchemyRuntimeTelemetryScopeReader,
    SqlAlchemyRuntimeTelemetryStore,
)
from ai_governance_api.application import (
    BlockDirectoryAccess,
    BuildDashboardSnapshot,
    CacheResolvedDirectoryAuthorization,
    ControlCatalogPort,
    ControlCrosswalkPort,
    CorporateDirectoryIdentityMismatch,
    CorporateDirectoryNotApplicable,
    CorporateDirectoryProfile,
    CorporateDirectoryResponseInvalid,
    CorporateDirectoryUnavailable,
    DirectoryAccessUnavailable,
    DirectoryAuthorizationCacheUnavailable,
    EvaluateInitiativeControls,
    GetControlCrosswalk,
    IncidentService,
    InvalidateDirectoryAuthorization,
    ListAssessments,
    ListControlCatalog,
    ListEvidence,
    ListModelRoutingDecisions,
    PolicyModelRouterPort,
    RequestModelRoutingDecision,
    RequireActiveDirectoryAccess,
    ResolveCorporateDirectory,
    ResolveDirectoryAuthorization,
    RestoreDirectoryAccess,
    ReuseDirectoryAuthorization,
    SaveAssessment,
    SubmitAssessment,
    UploadEvidence,
)
from ai_governance_api.application.runtime_control import (
    RuntimeControlGate,
    RuntimeControlProjectionPort,
    RuntimeControlService,
)
from ai_governance_api.application.runtime_telemetry import (
    IngestRuntimeTelemetry,
    ListRuntimeTelemetryEvents,
)
from ai_governance_api.auth import BEARER_CHALLENGE, BearerCredentials, get_principal
from ai_governance_api.config import AppEnvironment, Settings, get_settings
from ai_governance_api.database import SessionFactory, get_db
from ai_governance_api.domain.directory_authorization import (
    DirectoryAuthorizationCatalog,
    DirectoryAuthorizationError,
)
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheError,
)
from ai_governance_api.domain.identity import (
    DirectoryGroupClaimState,
    DirectoryGroupResolutionSource,
    Principal,
)
from ai_governance_api.services import InitiativeService, InventoryService, PolicyEvaluator

DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedPrincipal = Annotated[Principal, Depends(get_principal)]
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


@lru_cache
def get_control_crosswalk() -> ControlCrosswalkPort:
    """Load the packaged or explicitly configured control crosswalk once per process."""
    path = get_settings().control_crosswalk_path
    catalog = get_control_catalog().catalog
    return (
        GovernanceControlCrosswalk.from_path(path, catalog)
        if path
        else GovernanceControlCrosswalk.from_package(catalog)
    )


PolicyEvaluatorDependency = Annotated[PolicyEvaluator, Depends(get_policy_evaluator)]
ControlCatalogDependency = Annotated[ControlCatalogPort, Depends(get_control_catalog)]
ControlCrosswalkDependency = Annotated[ControlCrosswalkPort, Depends(get_control_crosswalk)]


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


def get_reuse_directory_authorization() -> ReuseDirectoryAuthorization:
    """Build the shared authorization-cache query."""
    return ReuseDirectoryAuthorization(SqlAlchemyDirectoryAuthorizationCacheReader(SessionFactory))


def get_cache_resolved_directory_authorization(
    session: DatabaseSession,
    settings: SettingsDependency,
) -> CacheResolvedDirectoryAuthorization:
    """Build the shared authorization-cache command with deployment TTL."""
    return CacheResolvedDirectoryAuthorization(
        SqlAlchemyDirectoryAuthorizationCache(session),
        SqlAlchemyDirectoryAuthorizationCacheTransaction(session),
        ttl_seconds=settings.directory_authorization_cache_ttl_seconds,
    )


def get_invalidate_directory_authorization(
    session: DatabaseSession,
    settings: SettingsDependency,
) -> InvalidateDirectoryAuthorization:
    """Build the audited administrative invalidation command."""
    return InvalidateDirectoryAuthorization(
        SqlAlchemyDirectoryAuthorizationCache(session),
        SqlAlchemyDirectoryAuthorizationCacheAudit(session),
        SqlAlchemyDirectoryAuthorizationCacheTransaction(session),
        allowed_tenant_ids=settings.oidc_allowed_tenant_id_set,
    )


ReuseDirectoryAuthorizationDependency = Annotated[
    ReuseDirectoryAuthorization,
    Depends(get_reuse_directory_authorization),
]
CacheResolvedDirectoryAuthorizationDependency = Annotated[
    CacheResolvedDirectoryAuthorization,
    Depends(get_cache_resolved_directory_authorization),
]
InvalidateDirectoryAuthorizationDependency = Annotated[
    InvalidateDirectoryAuthorization,
    Depends(get_invalidate_directory_authorization),
]


def get_require_active_directory_access() -> RequireActiveDirectoryAccess:
    """Build the per-request emergency access query with a short DB session."""
    return RequireActiveDirectoryAccess(SqlAlchemyDirectoryAccessReader(SessionFactory))


RequireActiveDirectoryAccessDependency = Annotated[
    RequireActiveDirectoryAccess,
    Depends(get_require_active_directory_access),
]


async def get_active_principal(
    principal: AuthenticatedPrincipal,
    access_query: RequireActiveDirectoryAccessDependency,
) -> Principal:
    """Reject suspended directory identities before any protected route executes."""
    try:
        return await access_query.execute(principal)
    except DirectoryAccessUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Directory access state could not be trusted",
        ) from exc


CurrentPrincipal = Annotated[Principal, Depends(get_active_principal)]


def get_block_directory_access(
    session: DatabaseSession,
    settings: SettingsDependency,
) -> BlockDirectoryAccess:
    """Build the audited emergency block command at the composition root."""
    return BlockDirectoryAccess(
        SqlAlchemyDirectoryAccessStore(session),
        SqlAlchemyDirectoryAccessCacheInvalidation(session),
        SqlAlchemyDirectoryAccessAudit(session),
        SqlAlchemyDirectoryAccessTransaction(session),
        allowed_tenant_ids=settings.oidc_allowed_tenant_id_set,
    )


def get_restore_directory_access(
    session: DatabaseSession,
    settings: SettingsDependency,
) -> RestoreDirectoryAccess:
    """Build the audited access-restoration command at the composition root."""
    return RestoreDirectoryAccess(
        SqlAlchemyDirectoryAccessStore(session),
        SqlAlchemyDirectoryAccessCacheInvalidation(session),
        SqlAlchemyDirectoryAccessAudit(session),
        SqlAlchemyDirectoryAccessTransaction(session),
        allowed_tenant_ids=settings.oidc_allowed_tenant_id_set,
    )


BlockDirectoryAccessDependency = Annotated[
    BlockDirectoryAccess,
    Depends(get_block_directory_access),
]
RestoreDirectoryAccessDependency = Annotated[
    RestoreDirectoryAccess,
    Depends(get_restore_directory_access),
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
            max_attempts=settings.microsoft_graph_max_attempts,
            backoff_base_seconds=settings.microsoft_graph_backoff_base_seconds,
            max_retry_delay_seconds=settings.microsoft_graph_max_retry_delay_seconds,
            max_retry_after_seconds=settings.microsoft_graph_max_retry_after_seconds,
            max_response_bytes=settings.microsoft_graph_max_response_bytes,
        )
    )


CorporateDirectoryResolverDependency = Annotated[
    ResolveCorporateDirectory | None,
    Depends(get_corporate_directory_resolver),
]


@dataclass(slots=True)
class CorporateDirectoryRequestSnapshot:
    """Memoize one Graph result only for the lifetime of an HTTP request."""

    resolved: bool = False
    profile: CorporateDirectoryProfile | None = None


def get_corporate_directory_request_snapshot() -> CorporateDirectoryRequestSnapshot:
    """Create a request-scoped Graph snapshot shared by dependent routes."""
    return CorporateDirectoryRequestSnapshot()


CorporateDirectoryRequestSnapshotDependency = Annotated[
    CorporateDirectoryRequestSnapshot,
    Depends(get_corporate_directory_request_snapshot),
]


async def get_corporate_directory_profile(
    principal: CurrentPrincipal,
    credentials: BearerCredentials,
    resolver: CorporateDirectoryResolverDependency,
    request_snapshot: CorporateDirectoryRequestSnapshotDependency,
) -> CorporateDirectoryProfile | None:
    """Enrich the current identity while mapping dependency failures safely."""
    if resolver is None:
        return None
    return await _resolve_corporate_directory_profile(
        principal,
        credentials,
        resolver,
        request_snapshot,
    )


async def _resolve_corporate_directory_profile(
    principal: Principal,
    credentials: BearerCredentials,
    resolver: ResolveCorporateDirectory,
    request_snapshot: CorporateDirectoryRequestSnapshot,
) -> CorporateDirectoryProfile:
    """Resolve Graph once per request and map all failures to safe HTTP responses."""
    if request_snapshot.resolved and request_snapshot.profile is not None:
        return request_snapshot.profile
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers=BEARER_CHALLENGE,
        )
    try:
        profile = await resolver.execute(principal, credentials.credentials)
        request_snapshot.profile = profile
        request_snapshot.resolved = True
        return profile
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
    credentials: BearerCredentials,
    directory_resolver: CorporateDirectoryResolverDependency,
    request_snapshot: CorporateDirectoryRequestSnapshotDependency,
    resolver: DirectoryAuthorizationResolverDependency,
    cache_query: ReuseDirectoryAuthorizationDependency,
    cache_command: CacheResolvedDirectoryAuthorizationDependency,
    catalog: DirectoryAuthorizationCatalogDependency,
) -> Principal:
    """Resolve catalog-derived capabilities for authorization-sensitive requests."""
    try:
        cached = await cache_query.execute(
            principal,
            catalog_digest=catalog.catalog_digest,
        )
    except (DirectoryAuthorizationCacheError, DirectoryAuthorizationCacheUnavailable) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Directory authorization cache could not be trusted",
        ) from exc
    if cached is not None:
        return cached

    resolution_started_at = datetime.now(UTC)
    directory_profile = (
        await _resolve_corporate_directory_profile(
            principal,
            credentials,
            directory_resolver,
            request_snapshot,
        )
        if directory_resolver is not None
        else None
    )
    if directory_profile is not None:
        group_object_ids = directory_profile.group_object_ids
        group_resolution_source = DirectoryGroupResolutionSource.MICROSOFT_GRAPH
    elif principal.directory_group_claims.state is DirectoryGroupClaimState.COMPLETE:
        group_object_ids = principal.directory_group_claims.object_ids
        group_resolution_source = DirectoryGroupResolutionSource.TOKEN
    elif principal.directory_group_claims.state is DirectoryGroupClaimState.OVERAGE:
        group_object_ids = frozenset()
        group_resolution_source = DirectoryGroupResolutionSource.OVERAGE_UNRESOLVED
    else:
        group_object_ids = frozenset()
        group_resolution_source = DirectoryGroupResolutionSource.NONE
    try:
        authorized = resolver.execute(
            principal,
            group_object_ids=group_object_ids,
            group_resolution_source=group_resolution_source,
        )
        return await cache_command.execute(
            authorized,
            resolved_at=resolution_started_at,
        )
    except (
        DirectoryAuthorizationCacheError,
        DirectoryAuthorizationCacheUnavailable,
        DirectoryAuthorizationError,
    ) as exc:
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


def get_incident_service(session: DatabaseSession) -> IncidentService:
    """Build the request-scoped incident and exception service."""
    return IncidentService(
        SqlAlchemyIncidentRepository(session),
        SqlAlchemyIncidentAudit(session),
        SqlAlchemyTransaction(session),
    )


@lru_cache
def get_runtime_control_projection() -> RuntimeControlProjectionPort:
    """Build the shared runtime projection, using memory only for local/test."""
    settings = get_settings()
    if settings.runtime_control_enabled:
        return build_redis_runtime_control_store(
            redis_url=settings.runtime_control_redis_url,
            key_prefix=settings.runtime_control_redis_key_prefix,
            timeout_seconds=settings.runtime_control_redis_timeout_seconds,
        )
    if settings.app_env in {AppEnvironment.LOCAL, AppEnvironment.TEST}:
        return InMemoryRuntimeControlStore()
    return UnavailableRuntimeControlStore()


def get_runtime_control_service(session: DatabaseSession) -> RuntimeControlService:
    """Build the single write path for emergency kill-switch transitions."""
    return RuntimeControlService(
        SqlAlchemyRuntimeControlRepository(session),
        get_runtime_control_projection(),
        SqlAlchemyRuntimeControlAudit(session),
        SqlAlchemyTransaction(session),
    )


def get_build_dashboard_snapshot(session: DatabaseSession) -> BuildDashboardSnapshot:
    """Build the request-scoped dashboard aggregation use case."""
    return BuildDashboardSnapshot(SqlAlchemyDashboardStore(session))


InitiativeServiceDependency = Annotated[InitiativeService, Depends(get_initiative_service)]
InventoryServiceDependency = Annotated[InventoryService, Depends(get_inventory_service)]
IncidentServiceDependency = Annotated[IncidentService, Depends(get_incident_service)]
RuntimeControlServiceDependency = Annotated[
    RuntimeControlService, Depends(get_runtime_control_service)
]
BuildDashboardSnapshotDependency = Annotated[
    BuildDashboardSnapshot, Depends(get_build_dashboard_snapshot)
]


@lru_cache
def get_policy_model_router() -> PolicyModelRouterHttpAdapter:
    """Build the process configuration for the external routing decision point."""
    settings = get_settings()
    return PolicyModelRouterHttpAdapter(
        base_url=settings.policy_model_router_base_url,
        api_keys=settings.policy_model_router_api_key_map,
        timeout_seconds=settings.policy_model_router_timeout_seconds,
        max_response_bytes=settings.policy_model_router_max_response_bytes,
    )


def get_request_model_routing_decision(
    session: DatabaseSession,
    router: Annotated[PolicyModelRouterPort, Depends(get_policy_model_router)],
) -> RequestModelRoutingDecision:
    """Build routing enforcement without holding a DB session across network I/O."""
    settings = get_settings()
    authorization_issuer = (
        build_runtime_authorization_issuer() if settings.policy_model_router_enabled else None
    )
    return RequestModelRoutingDecision(
        SqlAlchemyModelRoutingScopeReader(SessionFactory),
        router,
        SqlAlchemyModelRoutingDecisionStore(session),
        SqlAlchemyModelRoutingAudit(session),
        SqlAlchemyTransaction(session),
        authorization_issuer=authorization_issuer,
        runtime_control_gate=RuntimeControlGate(
            SqlAlchemyRuntimeControlStateReader(SessionFactory),
            get_runtime_control_projection(),
        ),
    )


def get_list_model_routing_decisions(
    session: DatabaseSession,
) -> ListModelRoutingDecisions:
    """Build the request-scoped routing evidence query."""
    return ListModelRoutingDecisions(
        SqlAlchemyModelRoutingScopeReader(SessionFactory),
        SqlAlchemyModelRoutingDecisionStore(session),
    )


RequestModelRoutingDecisionDependency = Annotated[
    RequestModelRoutingDecision,
    Depends(get_request_model_routing_decision),
]
ListModelRoutingDecisionsDependency = Annotated[
    ListModelRoutingDecisions,
    Depends(get_list_model_routing_decisions),
]


def get_ingest_runtime_telemetry(session: DatabaseSession) -> IngestRuntimeTelemetry:
    """Build the request-scoped sanitized runtime telemetry ingestion use case."""
    return IngestRuntimeTelemetry(
        SqlAlchemyRuntimeTelemetryScopeReader(SessionFactory),
        SqlAlchemyRuntimeTelemetryStore(session),
        SqlAlchemyRuntimeTelemetryAudit(session),
        SqlAlchemyTransaction(session),
    )


def get_list_runtime_telemetry_events(
    session: DatabaseSession,
    settings: SettingsDependency,
) -> ListRuntimeTelemetryEvents:
    """Build the bounded runtime telemetry query."""
    return ListRuntimeTelemetryEvents(
        SqlAlchemyRuntimeTelemetryScopeReader(SessionFactory),
        SqlAlchemyRuntimeTelemetryStore(session),
        limit=settings.runtime_telemetry_list_limit,
    )


IngestRuntimeTelemetryDependency = Annotated[
    IngestRuntimeTelemetry,
    Depends(get_ingest_runtime_telemetry),
]
ListRuntimeTelemetryEventsDependency = Annotated[
    ListRuntimeTelemetryEvents,
    Depends(get_list_runtime_telemetry_events),
]


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


def get_control_crosswalk_query(crosswalk: ControlCrosswalkDependency) -> GetControlCrosswalk:
    """Build the active control-crosswalk query."""
    return GetControlCrosswalk(crosswalk)


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
GetControlCrosswalkDependency = Annotated[
    GetControlCrosswalk,
    Depends(get_control_crosswalk_query),
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
