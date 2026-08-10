"""Generate P2.0b SBOM and vulnerability evidence from exact P2.0a commits."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.release_security_evidence import (
    CANONICALIZATION,
    KIND,
    REQUIRED_ARTIFACT_ROLES,
    SCHEMA_VERSION,
    SecurityEvidenceError,
    build_artifact_record,
    bundle_digest,
    load_json_object,
    policy_digest,
    release_manifest_digest,
    sha256_bytes,
    summarize_npm_audit,
    summarize_python_audit,
    summarize_trivy_audit,
    verify_bundle,
    verify_cyclonedx,
)

_COMPONENT_REPOS = {
    "governance": "brunovicco/verifiable-ai-governance",
    "policy_model_router": "brunovicco/policy-model-router",
    "multi_agent_credit_desk": "brunovicco/multi-agent-credit-desk",
    "a2a_otel_kit": "brunovicco/a2a-otel-kit",
}


class CommandError(SecurityEvidenceError):
    """Raised when an evidence-producing external command fails."""


def run(
    command: list[str],
    *,
    cwd: Path,
    allowed_codes: tuple[int, ...] = (0,),
    stdout_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one bounded subprocess and validate its exit code."""
    if stdout_path is None:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    else:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_path.open("w", encoding="utf-8") as output:
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
    if completed.returncode not in allowed_codes:
        stderr = (completed.stderr or "").strip()
        raise CommandError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n{stderr}"
        )
    return completed


def tool_version(command: list[str], cwd: Path) -> str:
    """Capture one scanner/build tool version."""
    completed = run(command, cwd=cwd)
    value = (completed.stdout or completed.stderr or "").strip()
    if not value:
        raise CommandError(f"Tool version command produced no output: {' '.join(command)}")
    return value


def git(repo: Path, *args: str) -> str:
    """Run one read-only Git query."""
    completed = run(["git", *args], cwd=repo)
    return completed.stdout.strip()


def normalize_origin(value: str) -> str:
    """Normalize common GitHub origin forms to owner/repository."""
    cleaned = value.strip().removesuffix(".git")
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
        "ssh://git@github.com/",
    )
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :]
    raise SecurityEvidenceError(f"Unsupported GitHub origin URL: {value}")


def require_repo(repo: Path, expected: str, commit: str) -> None:
    """Require local repository identity and exact selected commit availability."""
    if normalize_origin(git(repo, "config", "--get", "remote.origin.url")) != expected:
        raise SecurityEvidenceError(f"Repository identity mismatch for {repo}; expected {expected}")
    run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=repo)


def require_governance_worktree_clean(repo: Path) -> None:
    """Require a clean tooling checkout before evidence generation."""
    if git(repo, "status", "--porcelain"):
        raise SecurityEvidenceError("Governance worktree must be clean before P2.0b generation")


def git_blob(repo: Path, commit: str, path: str) -> bytes:
    """Read one exact Git blob from a selected release commit."""
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SecurityEvidenceError(f"Cannot read {path} from {commit} in {repo}")
    return completed.stdout


def extract_commit(repo: Path, commit: str, destination: Path) -> None:
    """Extract one commit without checking it out or mutating history."""
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination.parent / f"{destination.name}.tar"
    with archive.open("wb") as handle:
        completed = subprocess.run(
            ["git", "archive", "--format=tar", commit],
            cwd=repo,
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    if completed.returncode != 0:
        raise SecurityEvidenceError(f"git archive failed for {repo}@{commit}")
    with tarfile.open(archive, "r") as tar:
        tar.extractall(destination, filter="data")
    archive.unlink()


def verify_manifest_lock_binding(
    repo: Path,
    commit: str,
    component: dict[str, Any],
    component_name: str,
) -> None:
    """Verify P2.0a lock digest against the exact Git object before scanning."""
    lockfile = component.get("lockfile")
    if not isinstance(lockfile, dict):
        raise SecurityEvidenceError(f"Missing lockfile binding for {component_name}")
    path = lockfile.get("path")
    expected = lockfile.get("sha256")
    if not isinstance(path, str) or not isinstance(expected, str):
        raise SecurityEvidenceError(f"Invalid lockfile binding for {component_name}")
    observed = sha256_bytes(git_blob(repo, commit, path))
    if observed != expected:
        raise SecurityEvidenceError(
            f"Lockfile drift for {component_name}: expected {expected}, observed {observed}"
        )


def export_python_requirements(source: Path, output: Path) -> None:
    """Export fully resolved Python dependencies from one exact uv lock."""
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-hashes",
            "--all-packages",
            "--no-emit-workspace",
            "-o",
            str(output),
        ],
        cwd=source,
    )


def pip_audit(requirements: Path, output: Path, fmt: str, cwd: Path) -> None:
    """Run pip-audit while retaining vulnerability exit code 1 as evidence."""
    run(
        [
            "uvx",
            "pip-audit",
            "-r",
            str(requirements),
            "--no-deps",
            "--disable-pip",
            "--format",
            fmt,
            "--output",
            str(output),
        ],
        cwd=cwd,
        allowed_codes=(0, 1),
    )
    if not output.is_file():
        raise CommandError(f"pip-audit did not write {output}")


def npm_evidence(source: Path, sbom: Path, audit: Path) -> None:
    """Generate npm CycloneDX SBOM and JSON audit from package-lock only."""
    run(
        [
            "npm",
            "sbom",
            "--sbom-format=cyclonedx",
            "--package-lock-only",
        ],
        cwd=source,
        stdout_path=sbom,
    )
    run(
        ["npm", "audit", "--json", "--package-lock-only", "--audit-level=low"],
        cwd=source,
        allowed_codes=(0, 1),
        stdout_path=audit,
    )


def build_image(source: Path, dockerfile: str, tag: str, *, web: bool, commit: str) -> str:
    """Build an exact Governance release image and return its image ID."""
    command = ["docker", "build", "--file", dockerfile, "--tag", tag]
    if web:
        command.extend(["--target", "runner", "--build-arg", f"NEXT_PUBLIC_GIT_SHA={commit}"])
    command.append(".")
    run(command, cwd=source)
    completed = run(["docker", "image", "inspect", "--format={{.Id}}", tag], cwd=source)
    image_id = completed.stdout.strip()
    if not image_id:
        raise CommandError(f"Cannot resolve image ID for {tag}")
    return image_id


def trivy_image(tag: str, output: Path, fmt: str, cwd: Path) -> None:
    """Generate one Trivy image report."""
    run(
        ["trivy", "image", "--format", fmt, "--output", str(output), tag],
        cwd=cwd,
    )


def artifact_path(root: Path, section: str, filename: str) -> Path:
    """Return one standard P2.0b artifact path."""
    path = root / "artifacts" / "release" / "security" / section / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def build_parser() -> argparse.ArgumentParser:
    """Build the P2.0b generator CLI."""
    parser = argparse.ArgumentParser(description="Generate P2.0b SBOM and vulnerability evidence")
    parser.add_argument(
        "--release-manifest",
        type=Path,
        default=Path("artifacts/release/release-manifest.json"),
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("config/release-security-policy.json"),
    )
    parser.add_argument("--policy-model-router-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--a2a-otel-kit-repo", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/release/security/security-evidence-bundle.json"),
    )
    return parser


def main() -> int:
    """Generate complete release security evidence and fail on policy violations."""
    args = build_parser().parse_args()
    governance = Path.cwd().resolve()
    repos = {
        "governance": governance,
        "policy_model_router": args.policy_model_router_repo.resolve(),
        "multi_agent_credit_desk": args.credit_desk_repo.resolve(),
        "a2a_otel_kit": args.a2a_otel_kit_repo.resolve(),
    }
    try:
        require_governance_worktree_clean(governance)
        manifest = load_json_object(args.release_manifest)
        manifest_digest = release_manifest_digest(manifest)
        components = manifest.get("components")
        if not isinstance(components, dict):
            raise SecurityEvidenceError("Release manifest components are missing")
        policy = load_json_object(args.policy)
        policy_hash = policy_digest(policy)
        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        generated_on = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).date()

        for name, expected_repo in _COMPONENT_REPOS.items():
            component = components.get(name)
            if not isinstance(component, dict):
                raise SecurityEvidenceError(f"Release manifest component missing: {name}")
            commit = component.get("commit")
            if not isinstance(commit, str):
                raise SecurityEvidenceError(f"Release commit missing: {name}")
            require_repo(repos[name], expected_repo, commit)
            verify_manifest_lock_binding(repos[name], commit, component, name)

        tools = {
            "uv": tool_version(["uv", "--version"], governance),
            "pip_audit": tool_version(["uvx", "pip-audit", "--version"], governance),
            "node": tool_version(["node", "--version"], governance),
            "npm": tool_version(["npm", "--version"], governance),
            "docker": tool_version(["docker", "--version"], governance),
            "trivy": tool_version(["trivy", "--version"], governance),
        }

        artifact_records: list[dict[str, object]] = []
        summaries: dict[str, object] = {}
        image_bindings: dict[str, object] = {}
        output_root = governance
        temp_root = Path(tempfile.mkdtemp(prefix="p2-0b-release-security-"))
        image_tags: list[str] = []
        try:
            source_dirs: dict[str, Path] = {}
            for name in _COMPONENT_REPOS:
                component = components[name]
                assert isinstance(component, dict)
                commit = str(component["commit"])
                source = temp_root / name
                extract_commit(repos[name], commit, source)
                source_dirs[name] = source
                requirements = artifact_path(
                    output_root,
                    "inputs",
                    f"{name}-requirements.txt",
                )
                export_python_requirements(source, requirements)
                audit = artifact_path(output_root, "vulnerabilities", f"{name}-pip-audit.json")
                sbom = artifact_path(output_root, "sbom", f"{name}-python.cdx.json")
                pip_audit(requirements, audit, "json", source)
                pip_audit(requirements, sbom, "cyclonedx-json", source)
                verify_cyclonedx(sbom)
                artifact_records.extend(
                    [
                        build_artifact_record(
                            requirements,
                            output_root,
                            f"python_requirements:{name}",
                            "text/plain",
                        ),
                        build_artifact_record(
                            audit,
                            output_root,
                            f"python_audit:{name}",
                            "application/json",
                        ),
                        build_artifact_record(
                            sbom,
                            output_root,
                            f"python_sbom:{name}",
                            "application/vnd.cyclonedx+json",
                        ),
                    ]
                )
                audit_payload = json.loads(audit.read_text(encoding="utf-8"))
                summaries[f"python:{name}"] = summarize_python_audit(
                    audit_payload,
                    name,
                    policy,
                    generated_on,
                )

            governance_source = source_dirs["governance"]
            npm_sbom = artifact_path(output_root, "sbom", "governance-web-npm.cdx.json")
            npm_audit_path = artifact_path(
                output_root,
                "vulnerabilities",
                "governance-web-npm-audit.json",
            )
            npm_evidence(governance_source, npm_sbom, npm_audit_path)
            verify_cyclonedx(npm_sbom)
            artifact_records.extend(
                [
                    build_artifact_record(
                        npm_sbom,
                        output_root,
                        "npm_sbom:governance_web",
                        "application/vnd.cyclonedx+json",
                    ),
                    build_artifact_record(
                        npm_audit_path,
                        output_root,
                        "npm_audit:governance_web",
                        "application/json",
                    ),
                ]
            )
            summaries["npm:governance_web"] = summarize_npm_audit(
                load_json_object(npm_audit_path),
                policy,
            )

            release_commit = str(components["governance"]["commit"])
            suffix = f"{manifest_digest[:12]}-{os.getpid()}"
            container_specs = (
                ("governance_api", "apps/api/Dockerfile", False),
                ("governance_web", "apps/web/Dockerfile", True),
            )
            for component_name, dockerfile, web in container_specs:
                tag = f"vaigov-p2-0b-{component_name}:{suffix}"
                image_tags.append(tag)
                image_id = build_image(
                    governance_source,
                    dockerfile,
                    tag,
                    web=web,
                    commit=release_commit,
                )
                audit = artifact_path(
                    output_root,
                    "vulnerabilities",
                    f"{component_name}-trivy.json",
                )
                sbom = artifact_path(output_root, "sbom", f"{component_name}-image.cdx.json")
                trivy_image(tag, audit, "json", governance_source)
                trivy_image(tag, sbom, "cyclonedx", governance_source)
                verify_cyclonedx(sbom)
                artifact_records.extend(
                    [
                        build_artifact_record(
                            audit,
                            output_root,
                            f"container_audit:{component_name}",
                            "application/json",
                        ),
                        build_artifact_record(
                            sbom,
                            output_root,
                            f"container_sbom:{component_name}",
                            "application/vnd.cyclonedx+json",
                        ),
                    ]
                )
                summaries[f"container:{component_name}"] = summarize_trivy_audit(
                    load_json_object(audit),
                    component_name,
                    policy,
                )
                image_bindings[component_name] = {
                    "source_commit": release_commit,
                    "image_id": image_id,
                }
        finally:
            for tag in image_tags:
                subprocess.run(
                    ["docker", "image", "rm", "--force", tag],
                    cwd=governance,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            shutil.rmtree(temp_root, ignore_errors=True)

        roles = {str(record["role"]) for record in artifact_records}
        if roles != REQUIRED_ARTIFACT_ROLES:
            raise SecurityEvidenceError("Generator did not produce all required artifact roles")
        artifact_records.sort(key=lambda record: str(record["role"]))
        source_bindings = {
            name: {
                "repository": components[name]["repository"],
                "commit": components[name]["commit"],
                "lockfile_sha256": components[name]["lockfile"]["sha256"],
            }
            for name in sorted(_COMPONENT_REPOS)
        }
        verdict = "pass"
        if any(
            isinstance(summary, dict) and summary.get("verdict") == "fail"
            for summary in summaries.values()
        ):
            verdict = "fail"
        release = manifest.get("release")
        if not isinstance(release, dict):
            raise SecurityEvidenceError("Release manifest release section is missing")
        bundle: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "canonicalization": CANONICALIZATION,
            "generated_at": generated_at,
            "release_version": release.get("version"),
            "release_manifest_digest": manifest_digest,
            "policy_digest": policy_hash,
            "source_bindings": source_bindings,
            "tools": tools,
            "images": image_bindings,
            "artifacts": artifact_records,
            "summaries": summaries,
            "verdict": verdict,
        }
        bundle["bundle_digest"] = bundle_digest(bundle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verify_bundle(args.output, args.release_manifest, args.policy)
        print("[p2.0b] GENERATED")
        print(f"[p2.0b] bundle: {args.output}")
        print(f"[p2.0b] digest: {bundle['bundle_digest']}")
        print(f"[p2.0b] verdict: {verdict}")
        if verdict != "pass":
            raise SecurityEvidenceError("Release security policy verdict is FAIL")
        return 0
    except (SecurityEvidenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[p2.0b] FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
