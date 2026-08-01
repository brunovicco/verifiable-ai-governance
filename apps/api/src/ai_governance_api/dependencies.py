"""FastAPI dependency wiring for application services."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from policy_engine import GovernanceControlCatalog, GovernancePolicyEngine
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.adapters import (
    ClamAVScanner,
    S3ObjectStorage,
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyEvidenceAudit,
    SqlAlchemyEvidenceStore,
    SqlAlchemyInitiativeControlContextStore,
    SqlAlchemyTransaction,
)
from ai_governance_api.application import (
    ControlCatalogPort,
    EvaluateInitiativeControls,
    ListAssessments,
    ListControlCatalog,
    ListEvidence,
    SaveAssessment,
    SubmitAssessment,
    UploadEvidence,
)
from ai_governance_api.auth import get_principal
from ai_governance_api.config import get_settings
from ai_governance_api.database import get_db
from ai_governance_api.domain.identity import Principal
from ai_governance_api.services import InitiativeService, InventoryService, PolicyEvaluator

DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


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
