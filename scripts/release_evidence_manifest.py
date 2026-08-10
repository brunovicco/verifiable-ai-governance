"""Build and verify deterministic cross-repository release evidence manifests."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

SCHEMA_VERSION = "1.0"
MANIFEST_KIND = "verifiable-ai-governance/release-evidence-manifest"
CANONICALIZATION = "json-sort-keys-compact-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


class ReleaseManifestError(RuntimeError):
    """Fail-closed release-manifest validation error."""


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    """One repository participating in the ecosystem release manifest."""

    key: str
    repository: str


COMPONENT_SPECS = (
    ComponentSpec("governance", "brunovicco/verifiable-ai-governance"),
    ComponentSpec("policy_model_router", "brunovicco/policy-model-router"),
    ComponentSpec("multi_agent_credit_desk", "brunovicco/multi-agent-credit-desk"),
    ComponentSpec("a2a_otel_kit", "brunovicco/a2a-otel-kit"),
)

EVIDENCE_SPECS = (
    ("p1_7_runtime_telemetry", "artifacts/e2e/p1.7-cross-repo-telemetry-live-report.json"),
    ("p1_8_runtime_assurance", "artifacts/e2e/p1.8-cross-repo-assurance-live-report.json"),
    ("p1_9_governed_actuation", "artifacts/e2e/p1.9-governed-actuation-live-report.json"),
)

GOVERNANCE_PROVENANCE_FILES = (
    ("policy_engine", "packages/policy-engine/src/policy_engine/engine.py"),
    ("control_catalog", "packages/policy-engine/src/policy_engine/control_catalog.yaml"),
    ("control_crosswalk", "packages/policy-engine/src/policy_engine/control_crosswalk.yaml"),
)

_ALLOWED_TOP_LEVEL = {
    "schema_version",
    "kind",
    "canonicalization",
    "release",
    "components",
    "governance_provenance",
    "database",
    "evidence",
    "compatibility",
    "manifest_digest",
}


def canonical_json_bytes(value: object) -> bytes:
    """Return stable UTF-8 JSON bytes used by P2.0a manifest hashing."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return lowercase SHA-256 for bytes."""
    return hashlib.sha256(value).hexdigest()


def manifest_digest(document: dict[str, object]) -> str:
    """Digest a manifest with its self-digest field removed."""
    unsigned = dict(document)
    unsigned.pop("manifest_digest", None)
    return sha256_bytes(canonical_json_bytes(unsigned))


def seal_manifest(document: dict[str, object]) -> dict[str, object]:
    """Return a copy with a canonical self-digest."""
    sealed = dict(document)
    sealed["manifest_digest"] = manifest_digest(sealed)
    return sealed


def _git(repo: Path, *args: str, check: bool = True) -> str:
    command = ["git", "-C", str(repo), *args]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ReleaseManifestError(f"{' '.join(command)}: {detail}")
    return result.stdout.strip()


def require_repository(repo: Path, expected_repository: str) -> None:
    """Require a Git checkout whose origin maps to the expected GitHub repository."""
    if not repo.is_dir():
        raise ReleaseManifestError(f"Repository path does not exist: {repo}")
    if _git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        raise ReleaseManifestError(f"Not a Git worktree: {repo}")
    remote = _git(repo, "config", "--get", "remote.origin.url")
    observed = normalize_github_repository(remote)
    if observed != expected_repository:
        raise ReleaseManifestError(
            "Repository origin mismatch: "
            f"expected {expected_repository}, observed {observed or remote}"
        )


def require_clean_repository(repo: Path) -> None:
    """Reject uncommitted or untracked input so release selection is unambiguous."""
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ReleaseManifestError(f"Repository must be clean before manifest generation: {repo}")


def normalize_github_repository(remote: str) -> str | None:
    """Normalize common GitHub SSH/HTTPS origin forms to owner/repository."""
    value = remote.strip()
    patterns = (
        r"^git@github\.com:(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?$",
        r"^https://github\.com/(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?/?$",
        r"^http://github\.com/(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return match.group("repo")
    return None


def resolve_commit(repo: Path, ref: str) -> str:
    """Resolve one ref to an exact commit SHA."""
    commit = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not _HEX40_RE.fullmatch(commit):
        raise ReleaseManifestError(f"Resolved ref is not a full Git commit: {ref}")
    return commit


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """Return whether one commit is an ancestor of another."""
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        check=False,
        capture_output=True,
        timeout=15,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise ReleaseManifestError("Unable to evaluate Git ancestry")


def git_file_bytes_optional(repo: Path, commit: str, path: str) -> bytes | None:
    """Read a tracked file, returning None only when the path is absent at that commit."""
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"],
        check=False,
        capture_output=True,
        timeout=15,
    )
    if result.returncode == 0:
        return result.stdout
    path_check = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        capture_output=True,
        timeout=15,
    )
    if path_check.returncode != 0:
        raise ReleaseManifestError(f"Evidence commit is not available locally: {commit}")
    return None


def commit_changed_paths(repo: Path, commit: str) -> tuple[str, ...]:
    """Return deterministic paths changed by a single-parent evidence commit."""
    parents = _git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    if not parents or parents[0] != commit:
        raise ReleaseManifestError(f"Unable to inspect evidence commit: {commit}")
    if len(parents) != 2:
        raise ReleaseManifestError(
            f"Squash-equivalence requires a single-parent evidence commit; observed {commit}"
        )
    parent = parents[1]
    raw = _git(repo, "diff", "--name-only", "--no-renames", parent, commit)
    paths = tuple(sorted(path for path in raw.splitlines() if path))
    if not paths:
        raise ReleaseManifestError(f"Evidence commit has no changed paths: {commit}")
    return paths


def squash_equivalence_record(
    repo: Path, evidence_commit: str, selected_commit: str
) -> dict[str, object] | None:
    """Prove a squash/rebase selection preserves every blob changed by evidence_commit."""
    paths = commit_changed_paths(repo, evidence_commit)
    attested: list[dict[str, object]] = []
    for path in paths:
        evidence_bytes = git_file_bytes_optional(repo, evidence_commit, path)
        selected_bytes = git_file_bytes_optional(repo, selected_commit, path)
        if evidence_bytes != selected_bytes:
            return None
        attested.append(
            {
                "path": path,
                "sha256": None if evidence_bytes is None else sha256_bytes(evidence_bytes),
            }
        )
    return {
        "relation": "squash_equivalent",
        "attested_path_count": len(attested),
        "attested_paths_digest": sha256_bytes(canonical_json_bytes(attested)),
    }


def commit_timestamp(repo: Path, commit: str) -> str:
    """Return deterministic committer timestamp for one selected component commit."""
    value = _git(repo, "show", "-s", "--format=%cI", commit)
    if not value:
        raise ReleaseManifestError(f"Missing commit timestamp: {commit}")
    return value


def git_file_bytes(repo: Path, commit: str, path: str) -> bytes:
    """Read one tracked file exactly from a selected commit."""
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"],
        check=False,
        capture_output=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise ReleaseManifestError(f"Required tracked file is unavailable at {commit}: {path}")
    return result.stdout


def git_paths(repo: Path, commit: str, prefix: str) -> tuple[str, ...]:
    """List tracked paths under a prefix at an exact commit."""
    output = _git(repo, "ls-tree", "-r", "--name-only", commit, "--", prefix)
    return tuple(line for line in output.splitlines() if line)


def _toml_at(repo: Path, commit: str, path: str = "pyproject.toml") -> dict[str, object]:
    try:
        parsed = tomllib.loads(git_file_bytes(repo, commit, path).decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseManifestError(f"Invalid TOML at {commit}:{path}") from exc
    return cast(dict[str, object], parsed)


def _project_metadata(repo: Path, commit: str) -> tuple[str, str, str, tuple[str, ...]]:
    document = _toml_at(repo, commit)
    project = document.get("project")
    if not isinstance(project, dict):
        raise ReleaseManifestError("pyproject.toml must contain [project]")
    name = project.get("name")
    version = project.get("version")
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies", [])
    if not all(isinstance(value, str) and value for value in (name, version, requires_python)):
        raise ReleaseManifestError("Project name, version, and requires-python are required")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise ReleaseManifestError("Project dependencies must be a string array")
    return (
        cast(str, name),
        cast(str, version),
        cast(str, requires_python),
        tuple(sorted(cast(list[str], dependencies))),
    )


def _a2a_requirement(dependencies: tuple[str, ...]) -> str | None:
    for dependency in dependencies:
        normalized = dependency.lower().replace("_", "-")
        if normalized.startswith("a2a-otel-kit"):
            return dependency[len("a2a-otel-kit") :].strip() or "*"
    return None


def component_record(repo: Path, spec: ComponentSpec, commit: str) -> dict[str, object]:
    """Build deterministic source and lockfile evidence for one component."""
    name, version, requires_python, dependencies = _project_metadata(repo, commit)
    lock = git_file_bytes(repo, commit, "uv.lock")
    return {
        "repository": spec.repository,
        "commit": commit,
        "commit_timestamp": commit_timestamp(repo, commit),
        "project_name": name,
        "project_version": version,
        "requires_python": requires_python,
        "lockfile": {
            "path": "uv.lock",
            "sha256": sha256_bytes(lock),
            "size_bytes": len(lock),
        },
        "integration_dependencies": {
            "a2a_otel_kit": _a2a_requirement(dependencies),
        },
    }


def _literal_assignment(source: bytes, name: str, path: str) -> str | None:
    try:
        module = ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise ReleaseManifestError(f"Invalid migration syntax: {path}") from exc
    for node in module.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            targets = list(node.targets)
            value = node.value
        if value is None:
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        literal = ast.literal_eval(value)
        if literal is None:
            return None
        if isinstance(literal, str):
            return literal
        raise ReleaseManifestError(f"Migration {name} must be a string or None: {path}")
    raise ReleaseManifestError(f"Migration {name} assignment missing: {path}")


def migration_record(governance_repo: Path, commit: str) -> dict[str, object]:
    """Discover the single Alembic head from tracked migration source."""
    prefix = "apps/api/alembic/versions"
    paths = tuple(
        path for path in git_paths(governance_repo, commit, prefix) if path.endswith(".py")
    )
    if not paths:
        raise ReleaseManifestError("No Alembic migrations found")
    revisions: dict[str, tuple[str | None, str, bytes]] = {}
    down_revisions: set[str] = set()
    for path in paths:
        raw = git_file_bytes(governance_repo, commit, path)
        revision = _literal_assignment(raw, "revision", path)
        down_revision = _literal_assignment(raw, "down_revision", path)
        if revision is None:
            raise ReleaseManifestError(f"Migration revision cannot be None: {path}")
        if revision in revisions:
            raise ReleaseManifestError(f"Duplicate Alembic revision: {revision}")
        revisions[revision] = (down_revision, path, raw)
        if down_revision is not None:
            down_revisions.add(down_revision)
    heads = sorted(set(revisions) - down_revisions)
    if len(heads) != 1:
        raise ReleaseManifestError(f"Expected exactly one Alembic head, observed {heads}")
    head = heads[0]
    _, path, raw = revisions[head]
    return {
        "alembic_head": head,
        "migration_count": len(revisions),
        "head_file": path,
        "head_file_sha256": sha256_bytes(raw),
    }


def governance_provenance_record(governance_repo: Path, commit: str) -> dict[str, object]:
    """Hash policy/control material that participates in governance provenance."""
    result: dict[str, object] = {}
    for key, path in GOVERNANCE_PROVENANCE_FILES:
        raw = git_file_bytes(governance_repo, commit, path)
        result[key] = {"path": path, "sha256": sha256_bytes(raw), "size_bytes": len(raw)}
    return result


def _json_object(raw: bytes, path: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError(f"Evidence is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseManifestError(f"Evidence root must be a JSON object: {path}")
    return cast(dict[str, object], value)


def _safe_baselines(payload: dict[str, object]) -> dict[str, object]:
    baselines = payload.get("baselines")
    if not isinstance(baselines, dict):
        return {}
    allowed = {
        "governance_head",
        "required_governance_baseline",
        "credit_desk_head",
        "a2a_otel_kit_runtime_version",
    }
    result: dict[str, object] = {}
    for key in sorted(allowed):
        value = baselines.get(key)
        if isinstance(value, str):
            result[key] = value
    return result


def evidence_records(governance_repo: Path, commit: str) -> dict[str, object]:
    """Hash committed live evidence and expose only bounded baseline metadata."""
    result: dict[str, object] = {}
    for key, path in EVIDENCE_SPECS:
        raw = git_file_bytes(governance_repo, commit, path)
        payload = _json_object(raw, path)
        observed_result = payload.get("result")
        result[key] = {
            "path": path,
            "sha256": sha256_bytes(raw),
            "size_bytes": len(raw),
            "schema_version": payload.get("schema_version")
            if isinstance(payload.get("schema_version"), str)
            else None,
            "result": observed_result if isinstance(observed_result, str) else None,
            "baselines": _safe_baselines(payload),
        }
    return result


def _record_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReleaseManifestError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _component_commit(components: dict[str, object], key: str) -> str:
    record = _record_dict(components.get(key), f"components.{key}")
    commit = record.get("commit")
    if not isinstance(commit, str) or not _HEX40_RE.fullmatch(commit):
        raise ReleaseManifestError(f"components.{key}.commit must be a full Git SHA")
    return commit


def compatibility_record(
    *,
    repos: dict[str, Path],
    components: dict[str, object],
    evidence: dict[str, object],
) -> dict[str, object]:
    """Describe exactly what the latest P1.9 evidence can bind to selected sources."""
    p19 = _record_dict(evidence.get("p1_9_governed_actuation"), "P1.9 evidence")
    baselines = _record_dict(p19.get("baselines"), "P1.9 baselines")
    governance_evidence = baselines.get("governance_head")
    credit_evidence = baselines.get("credit_desk_head")
    a2a_runtime_version = baselines.get("a2a_otel_kit_runtime_version")
    if not isinstance(governance_evidence, str) or not _HEX40_RE.fullmatch(governance_evidence):
        raise ReleaseManifestError("P1.9 evidence must include governance_head")
    if not isinstance(credit_evidence, str) or not _HEX40_RE.fullmatch(credit_evidence):
        raise ReleaseManifestError("P1.9 evidence must include credit_desk_head")
    if not isinstance(a2a_runtime_version, str) or not a2a_runtime_version:
        raise ReleaseManifestError("P1.9 evidence must include a2a_otel_kit_runtime_version")

    governance_selected = _component_commit(components, "governance")
    credit_selected = _component_commit(components, "multi_agent_credit_desk")
    a2a_selected = _component_commit(components, "a2a_otel_kit")
    router_selected = _component_commit(components, "policy_model_router")

    governance_relation = _compatibility_relation(
        repos["governance"], governance_evidence, governance_selected
    )
    credit_relation = _compatibility_relation(
        repos["multi_agent_credit_desk"], credit_evidence, credit_selected
    )
    tag = f"v{a2a_runtime_version}"
    a2a_runtime_commit = resolve_commit(repos["a2a_otel_kit"], tag)
    a2a_relation = _compatibility_relation(repos["a2a_otel_kit"], a2a_runtime_commit, a2a_selected)

    return {
        "latest_runtime_evidence": "p1_9_governed_actuation",
        "governance": {
            "evidence_commit": governance_evidence,
            "selected_commit": governance_selected,
            **governance_relation,
        },
        "multi_agent_credit_desk": {
            "evidence_commit": credit_evidence,
            "selected_commit": credit_selected,
            **credit_relation,
        },
        "a2a_otel_kit": {
            "evidence_runtime_version": a2a_runtime_version,
            "evidence_tag": tag,
            "evidence_tag_commit": a2a_runtime_commit,
            "selected_commit": a2a_selected,
            **a2a_relation,
        },
        "policy_model_router": {
            "selected_commit": router_selected,
            "evidence_binding": "not_attested_by_p1_9_report",
        },
        "limitation": (
            "P1.9 records the Router decision source and behavior but does not persist the "
            "Policy Model Router Git commit; P2.0a therefore pins the selected Router source "
            "without claiming that the P1.9 report attests its exact commit."
        ),
    }


def _compatibility_relation(
    repo: Path, evidence_commit: str, selected_commit: str
) -> dict[str, object]:
    if evidence_commit == selected_commit:
        return {"relation": "exact"}
    if is_ancestor(repo, evidence_commit, selected_commit):
        return {"relation": "descendant"}
    squash = squash_equivalence_record(repo, evidence_commit, selected_commit)
    if squash is not None:
        return squash
    raise ReleaseManifestError(
        "Selected commit neither descends from nor preserves the exact changed-path content of "
        f"evidence commit {evidence_commit}: {selected_commit}"
    )


def build_release_manifest(
    *,
    release_version: str,
    repos: dict[str, Path],
    refs: dict[str, str] | None = None,
    require_clean: bool = True,
) -> dict[str, object]:
    """Build a deterministic release manifest from four exact Git repositories."""
    if not _RELEASE_RE.fullmatch(release_version):
        raise ReleaseManifestError("Release version must be SemVer-like, for example 0.2.0-rc1")
    refs = refs or {}
    components: dict[str, object] = {}
    resolved: dict[str, str] = {}
    for spec in COMPONENT_SPECS:
        repo = repos.get(spec.key)
        if repo is None:
            raise ReleaseManifestError(f"Missing repository path for {spec.key}")
        require_repository(repo, spec.repository)
        if require_clean:
            require_clean_repository(repo)
        commit = resolve_commit(repo, refs.get(spec.key, "HEAD"))
        resolved[spec.key] = commit
        components[spec.key] = component_record(repo, spec, commit)

    governance_repo = repos["governance"]
    governance_commit = resolved["governance"]
    evidence = evidence_records(governance_repo, governance_commit)
    unsigned: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "canonicalization": CANONICALIZATION,
        "release": {
            "version": release_version,
            "source_date": commit_timestamp(governance_repo, governance_commit),
        },
        "components": components,
        "governance_provenance": governance_provenance_record(governance_repo, governance_commit),
        "database": migration_record(governance_repo, governance_commit),
        "evidence": evidence,
        "compatibility": compatibility_record(
            repos=repos,
            components=components,
            evidence=evidence,
        ),
    }
    return seal_manifest(unsigned)


def validate_manifest_shape(document: dict[str, object]) -> None:
    """Enforce the closed P2.0a top-level contract before any trust comparison."""
    if set(document) != _ALLOWED_TOP_LEVEL:
        raise ReleaseManifestError("Manifest contains missing or unsupported top-level fields")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseManifestError("Unsupported release manifest schema version")
    if document.get("kind") != MANIFEST_KIND:
        raise ReleaseManifestError("Unexpected release manifest kind")
    if document.get("canonicalization") != CANONICALIZATION:
        raise ReleaseManifestError("Unexpected canonicalization identifier")
    digest = document.get("manifest_digest")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ReleaseManifestError("manifest_digest must be a lowercase SHA-256 digest")
    if digest != manifest_digest(document):
        raise ReleaseManifestError("release manifest self-digest mismatch")
    release = _record_dict(document.get("release"), "release")
    version = release.get("version")
    if not isinstance(version, str) or not _RELEASE_RE.fullmatch(version):
        raise ReleaseManifestError("release.version is invalid")


def verify_release_manifest(
    document: dict[str, object],
    *,
    repos: dict[str, Path],
) -> None:
    """Re-derive every manifest field from declared Git commits and fail on drift/tamper."""
    validate_manifest_shape(document)
    components = _record_dict(document.get("components"), "components")
    refs: dict[str, str] = {}
    for spec in COMPONENT_SPECS:
        repo = repos.get(spec.key)
        if repo is None:
            raise ReleaseManifestError(f"Missing repository path for {spec.key}")
        require_repository(repo, spec.repository)
        refs[spec.key] = _component_commit(components, spec.key)
    release = _record_dict(document.get("release"), "release")
    version = cast(str, release["version"])
    expected = build_release_manifest(
        release_version=version,
        repos=repos,
        refs=refs,
        require_clean=False,
    )
    if canonical_json_bytes(expected) != canonical_json_bytes(document):
        raise ReleaseManifestError(
            "Release manifest does not match re-derived Git/evidence/provenance state"
        )


def load_manifest(path: Path) -> dict[str, object]:
    """Load a release manifest as a strict JSON object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError(f"Unable to read release manifest: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseManifestError("Release manifest root must be an object")
    return cast(dict[str, object], value)


def write_manifest(path: Path, document: dict[str, object]) -> None:
    """Write stable pretty JSON while preserving canonical digest semantics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
