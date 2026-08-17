"""Infrastructure adapters implementing application-owned ports."""

from ai_governance_api.adapters.assessment_persistence import (
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyTransaction,
)
from ai_governance_api.adapters.control_context import SqlAlchemyInitiativeControlContextStore
from ai_governance_api.adapters.dashboard_persistence import SqlAlchemyDashboardStore
from ai_governance_api.adapters.directory_access import (
    SqlAlchemyDirectoryAccessAudit,
    SqlAlchemyDirectoryAccessCacheInvalidation,
    SqlAlchemyDirectoryAccessReader,
    SqlAlchemyDirectoryAccessStore,
    SqlAlchemyDirectoryAccessTransaction,
)
from ai_governance_api.adapters.directory_authorization_cache import (
    SqlAlchemyDirectoryAuthorizationCache,
    SqlAlchemyDirectoryAuthorizationCacheAudit,
    SqlAlchemyDirectoryAuthorizationCacheReader,
    SqlAlchemyDirectoryAuthorizationCacheTransaction,
)
from ai_governance_api.adapters.directory_authorization_catalog import (
    DirectoryAuthorizationCatalogError,
    YamlDirectoryAuthorizationCatalog,
)
from ai_governance_api.adapters.evidence_persistence import (
    SqlAlchemyEvidenceAudit,
    SqlAlchemyEvidenceStore,
)
from ai_governance_api.adapters.governance_intelligence_audit import (
    SqlAlchemyGovernanceIntelligenceAudit,
)
from ai_governance_api.adapters.governance_intelligence_review_authorization import (
    SqlAlchemyInitiativeFindingReviewAuthorizer,
)
from ai_governance_api.adapters.governance_intelligence_review_persistence import (
    SqlAlchemyGovernanceFindingReviewUnitOfWork,
)
from ai_governance_api.adapters.governance_knowledge_evidence import (
    VerifiedEvidenceKnowledgeAdapter,
    governance_reference_for_evidence,
)
from ai_governance_api.adapters.incident_persistence import (
    SqlAlchemyIncidentAudit,
    SqlAlchemyIncidentRepository,
)
from ai_governance_api.adapters.malware import ClamAVScanner
from ai_governance_api.adapters.microsoft_graph import MicrosoftGraphCorporateDirectory
from ai_governance_api.adapters.model_routing_persistence import (
    SqlAlchemyModelRoutingAudit,
    SqlAlchemyModelRoutingDecisionStore,
    SqlAlchemyModelRoutingScopeReader,
)
from ai_governance_api.adapters.object_storage import S3ObjectStorage
from ai_governance_api.adapters.oidc import PyJwtOidcVerifier
from ai_governance_api.adapters.policy_model_router import PolicyModelRouterHttpAdapter

__all__ = [
    "SqlAlchemyAssessmentAudit",
    "SqlAlchemyAssessmentStore",
    "SqlAlchemyDirectoryAccessAudit",
    "SqlAlchemyDirectoryAccessCacheInvalidation",
    "SqlAlchemyDirectoryAccessReader",
    "SqlAlchemyDirectoryAccessStore",
    "SqlAlchemyDirectoryAccessTransaction",
    "SqlAlchemyDirectoryAuthorizationCache",
    "SqlAlchemyDirectoryAuthorizationCacheAudit",
    "SqlAlchemyDirectoryAuthorizationCacheReader",
    "SqlAlchemyDirectoryAuthorizationCacheTransaction",
    "SqlAlchemyDashboardStore",
    "SqlAlchemyEvidenceAudit",
    "SqlAlchemyEvidenceStore",
    "SqlAlchemyGovernanceFindingReviewUnitOfWork",
    "SqlAlchemyGovernanceIntelligenceAudit",
    "SqlAlchemyInitiativeFindingReviewAuthorizer",
    "SqlAlchemyIncidentAudit",
    "SqlAlchemyIncidentRepository",
    "SqlAlchemyInitiativeControlContextStore",
    "SqlAlchemyModelRoutingAudit",
    "SqlAlchemyModelRoutingDecisionStore",
    "SqlAlchemyModelRoutingScopeReader",
    "SqlAlchemyTransaction",
    "ClamAVScanner",
    "DirectoryAuthorizationCatalogError",
    "MicrosoftGraphCorporateDirectory",
    "PolicyModelRouterHttpAdapter",
    "PyJwtOidcVerifier",
    "S3ObjectStorage",
    "VerifiedEvidenceKnowledgeAdapter",
    "YamlDirectoryAuthorizationCatalog",
    "governance_reference_for_evidence",
]
