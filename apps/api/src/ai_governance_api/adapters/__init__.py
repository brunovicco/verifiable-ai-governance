"""Infrastructure adapters implementing application-owned ports."""

from ai_governance_api.adapters.assessment_persistence import (
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyTransaction,
)
from ai_governance_api.adapters.control_context import SqlAlchemyInitiativeControlContextStore
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
from ai_governance_api.adapters.object_storage import S3ObjectStorage
from ai_governance_api.adapters.oidc import PyJwtOidcVerifier

__all__ = [
    "SqlAlchemyAssessmentAudit",
    "SqlAlchemyAssessmentStore",
    "SqlAlchemyDirectoryAuthorizationCache",
    "SqlAlchemyDirectoryAuthorizationCacheAudit",
    "SqlAlchemyDirectoryAuthorizationCacheReader",
    "SqlAlchemyDirectoryAuthorizationCacheTransaction",
    "SqlAlchemyEvidenceAudit",
    "SqlAlchemyEvidenceStore",
    "SqlAlchemyInitiativeControlContextStore",
    "SqlAlchemyTransaction",
    "ClamAVScanner",
    "DirectoryAuthorizationCatalogError",
    "MicrosoftGraphCorporateDirectory",
    "PyJwtOidcVerifier",
    "S3ObjectStorage",
    "YamlDirectoryAuthorizationCatalog",
]
