"""HTTP integration tests for secure evidence upload metadata."""

from io import BytesIO
from typing import BinaryIO

from ai_governance_api.dependencies import get_malware_scanner, get_object_storage
from ai_governance_api.domain.evidence import MalwareScanResult, ScanVerdict, StoredObject
from ai_governance_api.main import app
from httpx import AsyncClient

OWNER_HEADERS = {"X-User-Id": "evidence-owner"}


class CleanScanner:
    """Trusted scanner test adapter."""

    async def scan(self, content: BinaryIO) -> MalwareScanResult:
        assert content.read()
        return MalwareScanResult(ScanVerdict.CLEAN, "test-scanner")


class MemoryObjectStorage:
    """Private in-memory object-storage test adapter."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str,
        size_bytes: int,
        sha256: str,
    ) -> StoredObject:
        del content_type, size_bytes, sha256
        self.objects[key] = content.read()
        return StoredObject("test-evidence", key, f"s3://test-evidence/{key}")

    async def delete(self, stored: StoredObject) -> None:
        self.objects.pop(stored.key, None)


def initiative_payload() -> dict[str, object]:
    """Return a low-risk initiative owned by the test identity."""
    return {
        "name": "Iniciativa com evidência verificável",
        "description": "Mantém artefatos de assurance íntegros e escaneados.",
        "business_area": "Governança",
        "intended_users": "Revisores internos",
        "decision_impact": "informational",
        "data_classification": "internal",
        "autonomy_level": "a0_information",
        "hosting_model": "self_hosted",
    }


async def test_owner_uploads_and_lists_scanned_evidence(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/initiatives",
        json=initiative_payload(),
        headers=OWNER_HEADERS,
    )
    initiative_id = created.json()["id"]
    storage = MemoryObjectStorage()
    app.dependency_overrides[get_malware_scanner] = CleanScanner
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        uploaded = await client.post(
            f"/api/v1/initiatives/{initiative_id}/evidence",
            data={"kind": "security_test"},
            files={"file": ("scan.json", BytesIO(b'{"passed": true}'), "application/json")},
            headers=OWNER_HEADERS,
        )
        listed = await client.get(
            f"/api/v1/initiatives/{initiative_id}/evidence",
            headers=OWNER_HEADERS,
        )
        hidden = await client.get(
            f"/api/v1/initiatives/{initiative_id}/evidence",
            headers={"X-User-Id": "another-user"},
        )
    finally:
        app.dependency_overrides.pop(get_malware_scanner, None)
        app.dependency_overrides.pop(get_object_storage, None)

    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["original_filename"] == "scan.json"
    assert body["scan_status"] == "clean"
    assert len(body["sha256"]) == 64
    assert "storage" not in body
    assert list(storage.objects.values()) == [b'{"passed": true}']
    assert listed.status_code == 200
    assert listed.json() == [body]
    assert hidden.status_code == 403


async def test_upload_rejects_non_owner_and_spoofed_content(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/initiatives",
        json=initiative_payload(),
        headers=OWNER_HEADERS,
    )
    initiative_id = created.json()["id"]
    storage = MemoryObjectStorage()
    app.dependency_overrides[get_malware_scanner] = CleanScanner
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        forbidden = await client.post(
            f"/api/v1/initiatives/{initiative_id}/evidence",
            data={"kind": "other"},
            files={"file": ("report.pdf", b"%PDF-1.7", "application/pdf")},
            headers={"X-User-Id": "not-the-owner"},
        )
        spoofed = await client.post(
            f"/api/v1/initiatives/{initiative_id}/evidence",
            data={"kind": "other"},
            files={"file": ("report.pdf", b"plain text", "application/pdf")},
            headers=OWNER_HEADERS,
        )
    finally:
        app.dependency_overrides.pop(get_malware_scanner, None)
        app.dependency_overrides.pop(get_object_storage, None)

    assert forbidden.status_code == 403
    assert spoofed.status_code == 415
    assert storage.objects == {}


async def test_request_body_limit_runs_before_multipart_parsing(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/initiatives/unknown/evidence",
        content=b"",
        headers={
            **OWNER_HEADERS,
            "Content-Type": "multipart/form-data; boundary=test",
            "Content-Length": str(12 * 1024 * 1024),
        },
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Evidence request exceeds the configured upload limit"}
