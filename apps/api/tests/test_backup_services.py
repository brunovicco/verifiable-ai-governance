import hashlib
from pathlib import Path
from typing import Any

from ai_governance_api.adapters.backup_services import DockerComposePostgres, S3EvidenceBackup
from ai_governance_api.domain.backups import EvidenceArtifact, FileArtifact
from botocore.exceptions import ClientError


class MissingBucketPaginator:
    def paginate(self, **kwargs: object) -> list[dict[str, object]]:
        raise ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "missing"}},
            "ListObjectsV2",
        )


class MissingBucketClient:
    def get_paginator(self, name: str) -> MissingBucketPaginator:
        assert name == "list_objects_v2"
        return MissingBucketPaginator()


class InMemoryBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def iter_chunks(self, chunk_size: int) -> list[bytes]:
        return [
            self.content[index : index + chunk_size]
            for index in range(0, len(self.content), chunk_size)
        ]

    def close(self) -> None:
        self.closed = True


class InMemoryPaginator:
    def __init__(self, client: "InMemoryS3Client") -> None:
        self.client = client

    def paginate(self, *, Bucket: str) -> list[dict[str, object]]:
        if Bucket not in self.client.buckets:
            raise ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "missing"}},
                "ListObjectsV2",
            )
        return [{"Contents": [{"Key": key} for key in sorted(self.client.buckets[Bucket])]}]


class InMemoryS3Client:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {
            "governance-evidence": {"evidence/initiative/artifact": b"scanned evidence content"}
        }

    def get_paginator(self, name: str) -> InMemoryPaginator:
        assert name == "list_objects_v2"
        return InMemoryPaginator(self)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, InMemoryBody]:
        return {"Body": InMemoryBody(self.buckets[Bucket][Key])}

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "missing"}},
                "HeadBucket",
            )

    def create_bucket(self, *, Bucket: str, **kwargs: object) -> None:
        assert Bucket not in self.buckets
        self.buckets[Bucket] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: Any) -> None:
        self.buckets[Bucket][Key] = Body.read()

    def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
        for item in Delete["Objects"]:
            self.buckets[Bucket].pop(item["Key"])

    def delete_bucket(self, *, Bucket: str) -> None:
        assert not self.buckets[Bucket]
        del self.buckets[Bucket]


def evidence_adapter(client: Any) -> S3EvidenceBackup:
    return S3EvidenceBackup(
        endpoint_url="http://object-storage.test",
        region="us-east-1",
        source_bucket="governance-evidence",
        access_key="test",
        secret_key="test",
        client=client,
    )


def test_absent_source_bucket_is_an_empty_inventory() -> None:
    assert evidence_adapter(MissingBucketClient()).list_keys() == ()


def test_database_adapter_rejects_unbounded_command_timeout() -> None:
    try:
        DockerComposePostgres(
            source_database="ai_governance",
            database_user="governance",
            command_timeout_seconds=0,
        )
    except ValueError as exc:
        assert "timeout" in str(exc)
    else:
        raise AssertionError("Unbounded PostgreSQL timeout was accepted")


def test_s3_adapter_exports_restores_verifies_and_cleans_content(tmp_path: Path) -> None:
    client = InMemoryS3Client()
    adapter = evidence_adapter(client)
    key = "evidence/initiative/artifact"
    destination = tmp_path / "artifact.bin"

    assert adapter.list_keys() == (key,)
    adapter.download(key, destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    artifact = EvidenceArtifact(
        key=key,
        file=FileArtifact(
            relative_path="evidence/artifact.bin",
            sha256=digest,
            size_bytes=destination.stat().st_size,
        ),
    )

    restored = adapter.restore_to_new_bucket(
        ((artifact, destination),),
        "governance-restore-test",
    )

    assert restored == 1
    assert client.buckets["governance-restore-test"][key] == destination.read_bytes()
    adapter.delete_bucket("governance-restore-test")
    assert "governance-restore-test" not in client.buckets
