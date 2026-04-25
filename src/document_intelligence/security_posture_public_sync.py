"""Sync helpers for the published public security-posture repository."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2, copytree, rmtree
from subprocess import run
from tempfile import TemporaryDirectory
from typing import Protocol

from .repo_boundary import load_repo_boundary_manifest
from .security_posture_api_derivative import (
    DEFAULT_SECURITY_POSTURE_API_DERIVATIVE_OUTPUT,
    extract_security_posture_api_derivative_package,
)
from .security_posture_public_repo import (
    DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_OUTPUT,
    export_security_posture_public_repo,
)
from .security_posture_public_subtree import (
    DEFAULT_SECURITY_POSTURE_SUBTREE_OUTPUT,
    build_security_posture_public_subtree,
)
from .security_site_derivative import (
    DEFAULT_SECURITY_SITE_DERIVATIVE_OUTPUT,
    extract_security_site_derivative_package,
)

DEFAULT_REPO_BOUNDARY_MANIFEST_PATH = Path("docs/private-repo-boundary-manifest.json")
DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_URL = (
    "https://github.com/RyanKelleyCosing/security-posture-platform.git"
)
DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_BRANCH = "main"
DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_COMMIT_MESSAGE = (
    "Sync public demo repo from private source"
)


class CommandRunner(Protocol):
    """Callable protocol for shell command execution."""

    def __call__(
        self,
        args: Sequence[str],
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> str:
        ...


@dataclass(frozen=True)
class GitHubIdentity:
    """Git identity used when pushing the public demo repository."""

    login: str
    email: str


@dataclass(frozen=True)
class SecurityPosturePublicRepoSyncResult:
    """Result of syncing the staged public export to the published repo."""

    branch: str
    commit_sha: str
    pushed: bool
    refreshed_export: bool
    remote_url: str
    staging_relative_path: str


def refresh_security_posture_public_repo_export(
    repo_root: Path,
    *,
    manifest_path: Path = DEFAULT_REPO_BOUNDARY_MANIFEST_PATH,
    security_site_output_dir: Path = DEFAULT_SECURITY_SITE_DERIVATIVE_OUTPUT,
    security_api_output_dir: Path = DEFAULT_SECURITY_POSTURE_API_DERIVATIVE_OUTPUT,
    subtree_output_dir: Path = DEFAULT_SECURITY_POSTURE_SUBTREE_OUTPUT,
    repo_output_dir: Path = DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_OUTPUT,
) -> None:
    """Refresh the derivative, subtree, and repo-staging outputs."""

    resolved_manifest_path = _resolve_repo_path(repo_root, manifest_path)
    manifest = load_repo_boundary_manifest(resolved_manifest_path)
    extract_security_site_derivative_package(
        repo_root=repo_root,
        output_directory=_resolve_repo_path(repo_root, security_site_output_dir),
        manifest=manifest,
        manifest_path=resolved_manifest_path,
    )
    extract_security_posture_api_derivative_package(
        repo_root=repo_root,
        output_directory=_resolve_repo_path(repo_root, security_api_output_dir),
        manifest=manifest,
        manifest_path=resolved_manifest_path,
    )
    build_security_posture_public_subtree(
        repo_root=repo_root,
        output_directory=_resolve_repo_path(repo_root, subtree_output_dir),
    )
    export_security_posture_public_repo(
        repo_root=repo_root,
        output_directory=_resolve_repo_path(repo_root, repo_output_dir),
        subtree_directory=_resolve_repo_path(repo_root, subtree_output_dir),
    )


def resolve_github_identity(
    command_runner: CommandRunner | None = None,
) -> GitHubIdentity:
    """Resolve the authenticated GitHub login into a no-reply git identity."""

    resolved_runner = _run_command if command_runner is None else command_runner
    payload = json.loads(resolved_runner(["gh", "api", "user"]))
    login = payload.get("login")
    github_id = payload.get("id")
    if not isinstance(login, str) or not login.strip():
        raise ValueError("GitHub API response did not include a login value.")
    if not isinstance(github_id, int):
        raise ValueError("GitHub API response did not include a numeric id value.")

    cleaned_login = login.strip()
    return GitHubIdentity(
        login=cleaned_login,
        email=f"{github_id}+{cleaned_login}@users.noreply.github.com",
    )


def sync_security_posture_public_repo(
    repo_root: Path,
    *,
    remote_url: str = DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_URL,
    branch: str = DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_BRANCH,
    commit_message: str = DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_COMMIT_MESSAGE,
    manifest_path: Path = DEFAULT_REPO_BOUNDARY_MANIFEST_PATH,
    security_site_output_dir: Path = DEFAULT_SECURITY_SITE_DERIVATIVE_OUTPUT,
    security_api_output_dir: Path = DEFAULT_SECURITY_POSTURE_API_DERIVATIVE_OUTPUT,
    subtree_output_dir: Path = DEFAULT_SECURITY_POSTURE_SUBTREE_OUTPUT,
    staging_directory: Path = DEFAULT_SECURITY_POSTURE_PUBLIC_REPO_OUTPUT,
    refresh_export: bool = True,
    command_runner: CommandRunner | None = None,
    github_identity: GitHubIdentity | None = None,
    temp_directory_root: Path | None = None,
) -> SecurityPosturePublicRepoSyncResult:
    """Refresh and push the staged public export into the published repo."""

    resolved_runner = _run_command if command_runner is None else command_runner
    if refresh_export:
        refresh_security_posture_public_repo_export(
            repo_root=repo_root,
            manifest_path=manifest_path,
            security_site_output_dir=security_site_output_dir,
            security_api_output_dir=security_api_output_dir,
            subtree_output_dir=subtree_output_dir,
            repo_output_dir=staging_directory,
        )

    resolved_staging_directory = _resolve_repo_path(repo_root, staging_directory)
    if not resolved_staging_directory.is_dir():
        raise FileNotFoundError(
            "Public repo staging directory not found: "
            f"'{resolved_staging_directory.as_posix()}'."
        )

    with TemporaryDirectory(
        dir=None if temp_directory_root is None else str(temp_directory_root),
        prefix="security-posture-public-sync-",
    ) as temp_directory_name:
        working_tree = Path(temp_directory_name) / "repo"
        resolved_runner([
            "git",
            "clone",
            "--branch",
            branch,
            remote_url,
            str(working_tree),
        ])
        resolved_identity = (
            resolve_github_identity(resolved_runner)
            if github_identity is None
            else github_identity
        )
        for attempt in range(2):
            _replace_worktree_contents(resolved_staging_directory, working_tree)
            if not _worktree_has_changes(working_tree, resolved_runner):
                return SecurityPosturePublicRepoSyncResult(
                    branch=branch,
                    commit_sha=_git_head_sha(working_tree, resolved_runner),
                    pushed=False,
                    refreshed_export=refresh_export,
                    remote_url=remote_url,
                    staging_relative_path=_to_repo_relative_path(
                        repo_root,
                        resolved_staging_directory,
                    ),
                )

            _commit_worktree(
                working_tree,
                resolved_identity,
                commit_message,
                resolved_runner,
            )
            try:
                resolved_runner(
                    ["git", "push", "origin", branch, "--force-with-lease"],
                    cwd=working_tree,
                )
                return SecurityPosturePublicRepoSyncResult(
                    branch=branch,
                    commit_sha=_git_head_sha(working_tree, resolved_runner),
                    pushed=True,
                    refreshed_export=refresh_export,
                    remote_url=remote_url,
                    staging_relative_path=_to_repo_relative_path(
                        repo_root,
                        resolved_staging_directory,
                    ),
                )
            except RuntimeError as error:
                if attempt == 1 or not _is_stale_force_with_lease_error(error):
                    raise
                _refresh_worktree_from_remote(working_tree, branch, resolved_runner)

        raise AssertionError("Public repo sync exited the retry loop unexpectedly.")


def _resolve_repo_path(repo_root: Path, candidate_path: Path) -> Path:
    if candidate_path.is_absolute():
        return candidate_path
    return repo_root / candidate_path


def _run_command(
    args: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    result = run(
        [str(part) for part in args],
        capture_output=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
        env=_build_command_env(env),
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "Command returned a non-zero exit code."
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{details}")
    return result.stdout.strip()


def _build_command_env(env: Mapping[str, str] | None) -> dict[str, str]:
    command_env = dict(os.environ)
    if env is not None:
        command_env.update(env)
    return command_env


def _replace_worktree_contents(
    source_directory: Path,
    destination_directory: Path,
) -> None:
    for path in destination_directory.iterdir():
        if path.name == ".git":
            continue
        if path.is_dir():
            rmtree(path)
        else:
            path.unlink()

    for source_path in source_directory.iterdir():
        if source_path.name == ".git":
            continue
        destination_path = destination_directory / source_path.name
        if source_path.is_dir():
            copytree(source_path, destination_path)
        else:
            copy2(source_path, destination_path)


def _worktree_has_changes(
    working_tree: Path,
    command_runner: CommandRunner,
) -> bool:
    return bool(command_runner(["git", "status", "--short"], cwd=working_tree))


def _git_head_sha(
    working_tree: Path,
    command_runner: CommandRunner,
) -> str:
    return command_runner(["git", "rev-parse", "HEAD"], cwd=working_tree)


def _commit_worktree(
    working_tree: Path,
    github_identity: GitHubIdentity,
    commit_message: str,
    command_runner: CommandRunner,
) -> None:
    command_runner(["git", "add", "--all"], cwd=working_tree)
    command_runner(
        ["git", "commit", "--message", commit_message],
        cwd=working_tree,
        env={
            "GIT_AUTHOR_NAME": github_identity.login,
            "GIT_AUTHOR_EMAIL": github_identity.email,
            "GIT_COMMITTER_NAME": github_identity.login,
            "GIT_COMMITTER_EMAIL": github_identity.email,
        },
    )


def _refresh_worktree_from_remote(
    working_tree: Path,
    branch: str,
    command_runner: CommandRunner,
) -> None:
    command_runner(["git", "fetch", "origin", branch], cwd=working_tree)
    command_runner(
        ["git", "reset", "--hard", f"origin/{branch}"],
        cwd=working_tree,
    )


def _is_stale_force_with_lease_error(error: RuntimeError) -> bool:
    message = str(error)
    return "--force-with-lease" in message and "stale info" in message


def _to_repo_relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()