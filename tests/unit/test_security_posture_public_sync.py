"""Unit tests for syncing the public security-posture demo repo."""

from __future__ import annotations

import os
from pathlib import Path
from subprocess import run

from document_intelligence.security_posture_public_sync import (
    GitHubIdentity,
    resolve_github_identity,
    sync_security_posture_public_repo,
)


def test_resolve_github_identity_builds_noreply_address() -> None:
    """The GitHub identity helper should derive the no-reply email format."""

    def fake_runner(
        args: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        del cwd, env
        assert args == ["gh", "api", "user"]
        return '{"login": "RyanKelleyCosing", "id": 267755581}'

    identity = resolve_github_identity(fake_runner)

    assert identity.login == "RyanKelleyCosing"
    assert identity.email == "267755581+RyanKelleyCosing@users.noreply.github.com"


def test_sync_security_posture_public_repo_pushes_staged_export(
    tmp_path: Path,
) -> None:
    """Syncing should mirror the staged export into the published repo."""

    remote_repo = _create_bare_remote_repo(tmp_path, {"old.txt": "old\n"})
    repo_root = tmp_path / "private-repo"
    staging_directory = repo_root / "public-repo-staging" / "security-posture-platform"
    _write_file(staging_directory / "README.md", "# Security Posture Platform\n")
    _write_file(
        staging_directory / ".github" / "workflows" / "validate.yml",
        "name: Validate\n",
    )

    result = sync_security_posture_public_repo(
        repo_root=repo_root,
        remote_url=str(remote_repo),
        branch="main",
        commit_message="Sync public demo repo from private source",
        staging_directory=Path("public-repo-staging/security-posture-platform"),
        refresh_export=False,
        github_identity=GitHubIdentity(
            login="Sync User",
            email="sync@example.com",
        ),
        temp_directory_root=tmp_path,
    )

    assert result.pushed is True
    assert (
        result.staging_relative_path
        == "public-repo-staging/security-posture-platform"
    )

    verification_clone = tmp_path / "verification-clone"
    _run_git(["clone", str(remote_repo), str(verification_clone)])
    assert (verification_clone / "README.md").read_text(encoding="utf-8").startswith(
        "# Security Posture Platform"
    )
    assert (verification_clone / ".github" / "workflows" / "validate.yml").is_file()
    assert not (verification_clone / "old.txt").exists()

    commit_log = _run_git(
        ["log", "-1", "--format=%an <%ae>%n%s"],
        cwd=verification_clone,
    )
    assert "Sync User <sync@example.com>" in commit_log
    assert "Sync public demo repo from private source" in commit_log


def test_sync_security_posture_public_repo_skips_push_when_export_matches_remote(
    tmp_path: Path,
) -> None:
    """Syncing should be a no-op when the staged export already matches HEAD."""

    remote_repo = _create_bare_remote_repo(
        tmp_path,
        {"README.md": "# Security Posture Platform\n"},
        remote_name="matching-remote.git",
    )
    repo_root = tmp_path / "matching-private-repo"
    staging_directory = repo_root / "public-repo-staging" / "security-posture-platform"
    _write_file(staging_directory / "README.md", "# Security Posture Platform\n")

    result = sync_security_posture_public_repo(
        repo_root=repo_root,
        remote_url=str(remote_repo),
        branch="main",
        staging_directory=Path("public-repo-staging/security-posture-platform"),
        refresh_export=False,
        temp_directory_root=tmp_path,
    )

    assert result.pushed is False

    verification_clone = tmp_path / "matching-verification-clone"
    _run_git(["clone", str(remote_repo), str(verification_clone)])
    commit_count = _run_git(["rev-list", "--count", "HEAD"], cwd=verification_clone)
    assert commit_count == "1"


def test_sync_security_posture_public_repo_retries_when_remote_moves(
    tmp_path: Path,
) -> None:
    """Syncing should recover when another push advances the remote mid-flight."""

    remote_repo = _create_bare_remote_repo(
        tmp_path,
        {"README.md": "# Initial\n"},
        remote_name="retry-remote.git",
    )
    repo_root = tmp_path / "retry-private-repo"
    staging_directory = repo_root / "public-repo-staging" / "security-posture-platform"
    _write_file(staging_directory / "README.md", "# Security Posture Platform\n")

    push_attempts = 0

    def runner(
        args: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        nonlocal push_attempts
        if args == ["git", "push", "origin", "main", "--force-with-lease"]:
            push_attempts += 1
            if push_attempts == 1:
                _advance_remote(remote_repo, tmp_path, "retry-concurrent")
        return _run_command(args, cwd=cwd, env=env)

    result = sync_security_posture_public_repo(
        repo_root=repo_root,
        remote_url=str(remote_repo),
        branch="main",
        commit_message="Sync public demo repo from private source",
        staging_directory=Path("public-repo-staging/security-posture-platform"),
        refresh_export=False,
        github_identity=GitHubIdentity(
            login="Sync User",
            email="sync@example.com",
        ),
        temp_directory_root=tmp_path,
        command_runner=runner,
    )

    assert result.pushed is True
    assert push_attempts == 2

    verification_clone = tmp_path / "retry-verification-clone"
    _run_git(["clone", str(remote_repo), str(verification_clone)])
    assert (verification_clone / "README.md").read_text(encoding="utf-8") == (
        "# Security Posture Platform\n"
    )


def _create_bare_remote_repo(
    temp_root: Path,
    files: dict[str, str],
    *,
    remote_name: str = "remote.git",
) -> Path:
    remote_repo = temp_root / remote_name
    bootstrap_clone = temp_root / f"{remote_name}-bootstrap"
    _run_git(["init", "--bare", "--initial-branch=main", str(remote_repo)])
    _run_git(["clone", str(remote_repo), str(bootstrap_clone)])
    for relative_path, content in files.items():
        _write_file(bootstrap_clone / relative_path, content)
    _run_git(["add", "--all"], cwd=bootstrap_clone)
    _run_git(
        [
            "-c",
            "user.name=Initial User",
            "-c",
            "user.email=initial@example.com",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=bootstrap_clone,
    )
    _run_git(["push", "origin", "main"], cwd=bootstrap_clone)
    return remote_repo


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    result = run(
        ["git", *args],
        capture_output=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
        env=_build_env(env),
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    result = run(
        args,
        capture_output=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
        env=_build_env(env),
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{details}")
    return result.stdout.strip()


def _advance_remote(remote_repo: Path, temp_root: Path, clone_name: str) -> None:
    clone_path = temp_root / clone_name
    _run_git(["clone", str(remote_repo), str(clone_path)])
    _write_file(clone_path / "concurrent.txt", "remote moved\n")
    _run_git(["add", "--all"], cwd=clone_path)
    _run_git(
        [
            "-c",
            "user.name=Concurrent User",
            "-c",
            "user.email=concurrent@example.com",
            "commit",
            "-m",
            "Concurrent update",
        ],
        cwd=clone_path,
    )
    _run_git(["push", "origin", "main"], cwd=clone_path)


def _build_env(env: dict[str, str] | None) -> dict[str, str]:
    command_env = dict(os.environ)
    if env is not None:
        command_env.update(env)
    return command_env