"""Safely replace tracked rc1 provenance with newly generated rc2 provenance."""

import argparse
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from scripts.generate_release_build_provenance import generate
from scripts.release_build_provenance import BuildProvenanceError
from scripts.release_candidate_evidence import RELEASE_VERSION, require_clean_worktree

_PROVENANCE_RELATIVE = Path("artifacts/release/provenance")


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BuildProvenanceError(f"Command failed: {' '.join(command)}: {detail}")


def _snapshot_head(repo: Path, destination: Path) -> None:
    """Materialize the clean current HEAD into a temporary independent Git repository."""
    archive_path = destination.parent / "release-evidence-snapshot.tar"
    with archive_path.open("wb") as handle:
        completed = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=repo,
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise BuildProvenanceError(f"git archive failed: {detail}")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r") as archive:
        archive.extractall(destination, filter="data")

    stale = destination / _PROVENANCE_RELATIVE
    if stale.exists():
        shutil.rmtree(stale)

    _run(["git", "init", "-b", "main"], destination)
    _run(["git", "add", "-A"], destination)
    _run(
        [
            "git",
            "-c",
            "user.name=P2.0e.3 provenance refresh",
            "-c",
            "user.email=p2.0e.3@example.invalid",
            "commit",
            "-m",
            "temporary evidence snapshot",
        ],
        destination,
    )


def _replace_directory(source: Path, target: Path) -> None:
    """Replace only the known generated provenance directory with rollback on copy failure."""
    with tempfile.TemporaryDirectory(prefix="p2-0e3-provenance-backup-") as temporary:
        backup = Path(temporary) / "provenance"
        had_target = target.exists()
        if had_target:
            shutil.copytree(target, backup)
        try:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            if had_target:
                shutil.copytree(backup, target)
            raise


def parse_args() -> argparse.Namespace:
    """Parse repositories required to reproduce the rc2 provenance subjects."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--governance-repo", type=Path, default=Path("."))
    parser.add_argument("--policy-model-router-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--a2a-otel-kit-repo", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Generate rc2 provenance in isolation, then replace only tracked provenance outputs."""
    args = parse_args()
    repo = args.governance_repo.resolve()
    try:
        require_clean_worktree(repo)
        with tempfile.TemporaryDirectory(prefix="p2-0e3-provenance-refresh-") as temporary:
            snapshot = Path(temporary) / "repository"
            _snapshot_head(repo, snapshot)
            output = snapshot / _PROVENANCE_RELATIVE
            provenance = generate(
                repo_root=snapshot,
                release_manifest_path=snapshot / "artifacts/release/release-manifest.json",
                security_bundle_path=(
                    snapshot / "artifacts/release/security/security-evidence-bundle.json"
                ),
                governance_source_repo=repo,
                policy_model_router_repo=args.policy_model_router_repo.resolve(),
                credit_desk_repo=args.credit_desk_repo.resolve(),
                a2a_otel_kit_repo=args.a2a_otel_kit_repo.resolve(),
                output_dir=output,
                expected_release_version=RELEASE_VERSION,
            )
            _replace_directory(output, repo / _PROVENANCE_RELATIVE)
    except (BuildProvenanceError, OSError, subprocess.SubprocessError) as exc:
        print(f"[p2.0e.3-provenance] FAILED: {exc}")
        return 1
    print("[p2.0e.3-provenance] GENERATED")
    print(f"[p2.0e.3-provenance] release: {RELEASE_VERSION}")
    print(f"[p2.0e.3-provenance] digest: {provenance['provenance_digest']}")
    print(f"[p2.0e.3-provenance] output: {_PROVENANCE_RELATIVE.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
