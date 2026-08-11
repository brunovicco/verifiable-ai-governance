"""Run P2.0e.1 from the frozen rc2 source commit and record clean-install evidence."""

import argparse
import os
import platform
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from scripts.release_candidate_evidence import (
    CLEAN_INSTALL_EVIDENCE,
    CLEAN_INSTALL_LOG,
    CLEAN_INSTALL_SCRIPT,
    ReleaseCandidateEvidenceError,
    build_clean_install_evidence,
    manifest_release_info,
    read_json,
    require_clean_worktree,
    write_json,
)


def _tool_version(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ReleaseCandidateEvidenceError(f"Required tool failed: {' '.join(command)}")
    value = (completed.stdout or completed.stderr).strip()
    if not value:
        raise ReleaseCandidateEvidenceError(
            f"Required tool returned no version: {' '.join(command)}"
        )
    return value


def _extract_commit(repo: Path, commit: str, destination: Path) -> None:
    archive_path = destination.parent / "governance-release-source.tar"
    with archive_path.open("wb") as handle:
        completed = subprocess.run(
            ["git", "archive", "--format=tar", commit],
            cwd=repo,
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ReleaseCandidateEvidenceError(f"git archive failed for {commit}: {detail}")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r") as archive:
        archive.extractall(destination, filter="data")


def _run_clean_install(source: Path, project_name: str) -> tuple[int, bytes]:
    script = source / CLEAN_INSTALL_SCRIPT
    if not script.is_file():
        raise ReleaseCandidateEvidenceError(
            f"Frozen release source does not contain {CLEAN_INSTALL_SCRIPT}"
        )
    environment = os.environ.copy()
    environment["P2E1_COMPOSE_PROJECT_NAME"] = project_name
    completed = subprocess.run(
        ["bash", str(script)],
        cwd=source,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode, completed.stdout


def parse_args() -> argparse.Namespace:
    """Parse clean-install evidence capture arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-manifest",
        type=Path,
        default=Path("artifacts/release/release-manifest.json"),
    )
    parser.add_argument("--governance-repo", type=Path, default=Path("."))
    parser.add_argument("--log", type=Path, default=Path(CLEAN_INSTALL_LOG))
    parser.add_argument("--output", type=Path, default=Path(CLEAN_INSTALL_EVIDENCE))
    return parser.parse_args()


def main() -> int:
    """Capture frozen-source fresh-install evidence and write a passing receipt."""
    args = parse_args()
    repo = args.governance_repo.resolve()
    try:
        require_clean_worktree(repo)
        if args.log.exists() or args.output.exists():
            raise ReleaseCandidateEvidenceError(
                "Clean-install release evidence already exists; preserve it or remove it explicitly"
            )
        manifest = read_json(args.release_manifest)
        _, source_commit, _ = manifest_release_info(manifest)
        environment = {
            "system": platform.system(),
            "system_release": platform.release(),
            "machine": platform.machine(),
            "docker": _tool_version(["docker", "--version"], repo),
            "docker_compose": _tool_version(["docker", "compose", "version"], repo),
        }
        with tempfile.TemporaryDirectory(prefix="p2-0e3-clean-install-") as temporary:
            source = Path(temporary) / "source"
            _extract_commit(repo, source_commit, source)
            project_name = f"vag-p2e1-rc2-{os.getpid()}"
            return_code, log_bytes = _run_clean_install(source, project_name)
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_bytes(log_bytes)
        if return_code != 0:
            raise ReleaseCandidateEvidenceError(
                "Frozen-source clean-install E2E failed with exit code "
                f"{return_code}; diagnostic log preserved at {args.log}"
            )
        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        evidence = build_clean_install_evidence(
            manifest=manifest,
            governance_repo=repo,
            log_path=args.log,
            generated_at=generated_at,
            environment=environment,
        )
        write_json(args.output, evidence)
    except (ReleaseCandidateEvidenceError, OSError, subprocess.SubprocessError) as exc:
        print(f"[p2.0e.3-clean-install] FAILED: {exc}")
        return 1
    print("[p2.0e.3-clean-install] GENERATED")
    print(f"[p2.0e.3-clean-install] source commit: {source_commit}")
    print(f"[p2.0e.3-clean-install] evidence: {args.output}")
    print(f"[p2.0e.3-clean-install] digest: {evidence['evidence_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
