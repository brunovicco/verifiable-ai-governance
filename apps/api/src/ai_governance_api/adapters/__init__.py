"""Infrastructure adapters implementing application-owned ports."""

from ai_governance_api.adapters.assessment_persistence import (
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyTransaction,
)
from ai_governance_api.adapters.control_context import SqlAlchemyInitiativeControlContextStore
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
    "SqlAlchemyEvidenceAudit",
    "SqlAlchemyEvidenceStore",
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
    "YamlDirectoryAuthorizationCatalog",
]
