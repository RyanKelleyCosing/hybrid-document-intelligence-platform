"""Assembly helpers for the combined public security-posture subtree."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from shutil import copy2
from textwrap import dedent

from .security_posture_api_derivative import (
    DEFAULT_SECURITY_POSTURE_API_DERIVATIVE_OUTPUT,
)
from .security_site_derivative import DEFAULT_SECURITY_SITE_DERIVATIVE_OUTPUT

DEFAULT_SECURITY_POSTURE_SUBTREE_OUTPUT = Path(
    "public-subtrees/security-posture-platform"
)


@dataclass(frozen=True)
class SecurityPostureSubtreePackage:
    """One extracted package materialized into the public subtree."""

    destination_directory_name: str
    included_files: tuple[str, ...]
    source_relative_path: str


def build_security_posture_public_subtree(
    repo_root: Path,
    output_directory: Path,
    *,
    site_package_directory: Path = DEFAULT_SECURITY_SITE_DERIVATIVE_OUTPUT,
    api_package_directory: Path = DEFAULT_SECURITY_POSTURE_API_DERIVATIVE_OUTPUT,
) -> tuple[SecurityPostureSubtreePackage, ...]:
    """Build the combined public subtree from the extracted site and API packages."""

    output_directory.mkdir(parents=True, exist_ok=True)
    packages = (
        _copy_declared_package(
            repo_root=repo_root,
            output_directory=output_directory,
            source_package_directory=site_package_directory,
            destination_directory_name="security-posture-site",
        ),
        _copy_declared_package(
            repo_root=repo_root,
            output_directory=output_directory,
            source_package_directory=api_package_directory,
            destination_directory_name="security-posture-api",
        ),
    )

    _write_subtree_scaffold(output_directory, packages)
    return packages


def _copy_declared_package(
    *,
    repo_root: Path,
    output_directory: Path,
    source_package_directory: Path,
    destination_directory_name: str,
) -> SecurityPostureSubtreePackage:
    source_directory = _resolve_repo_path(repo_root, source_package_directory)
    if not source_directory.is_dir():
        raise FileNotFoundError(
            f"Public derivative package not found: '{source_directory}'."
        )

    destination_directory = output_directory / destination_directory_name
    _reset_directory(destination_directory)

    included_files = _collect_declared_files(source_directory)
    for relative_path in included_files:
        source_path = source_directory / relative_path
        destination_path = destination_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_path, destination_path)

    source_relative_path = source_directory.relative_to(repo_root).as_posix()
    return SecurityPostureSubtreePackage(
        destination_directory_name=destination_directory_name,
        included_files=included_files,
        source_relative_path=source_relative_path,
    )


def _resolve_repo_path(repo_root: Path, candidate_path: Path) -> Path:
    if candidate_path.is_absolute():
        return candidate_path
    return repo_root / candidate_path


def _reset_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        if child.is_dir():
            _clear_directory_contents(child)
        else:
            child.unlink()


def _clear_directory_contents(directory: Path) -> None:
    for child in directory.iterdir():
        if child.is_dir():
            _clear_directory_contents(child)
            child.rmdir()
        else:
            child.unlink()


def _collect_declared_files(source_directory: Path) -> tuple[str, ...]:
    metadata_path = source_directory / "derivative-sources.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"Derivative metadata not found: '{metadata_path.as_posix()}'."
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    declared_files = {"derivative-sources.json"}
    declared_files.update(_collect_declared_metadata_paths(metadata, "copied_files"))
    declared_files.update(
        _collect_declared_metadata_paths(metadata, "validation_files")
    )
    declared_files.update(
        relative_path
        for relative_path in metadata.get("generated_files", [])
        if isinstance(relative_path, str)
    )
    if (source_directory / "package-lock.json").is_file():
        declared_files.add("package-lock.json")

    return tuple(sorted(declared_files))


def _collect_declared_metadata_paths(
    metadata: dict[str, object],
    key: str,
) -> set[str]:
    raw_items = metadata.get(key, [])
    if not isinstance(raw_items, list):
        return set()

    declared_paths: set[str] = set()
    for item in raw_items:
        if isinstance(item, str):
            declared_paths.add(item)
        elif isinstance(item, dict) and isinstance(
            item.get("destination_relative_path"),
            str,
        ):
            declared_paths.add(item["destination_relative_path"])
    return declared_paths


def _write_subtree_scaffold(
    output_directory: Path,
    packages: tuple[SecurityPostureSubtreePackage, ...],
) -> None:
    payload = {
        "generated_files": sorted(
            [
                ".github/workflows/validate.yml",
                ".gitignore",
                "README.md",
                "subtree-sources.json",
            ]
        ),
        "packages": [asdict(package) for package in packages],
        "subtree_name": "security-posture-platform",
    }
    scaffold_files = {
        ".github/workflows/validate.yml": _build_validate_workflow(),
        ".gitignore": _build_gitignore(),
        "README.md": _build_readme(packages),
    }
    for relative_path, content in scaffold_files.items():
        destination_path = output_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(content, encoding="utf-8")
    (output_directory / "subtree-sources.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_gitignore() -> str:
    return dedent(
        """
        security-posture-api/.mypy_cache/
        security-posture-api/.venv/
        security-posture-api/.pytest_cache/
        security-posture-api/.ruff_cache/
        security-posture-api/__pycache__/
        security-posture-api/local.settings.json
        security-posture-api/outputs/
        security-posture-site/coverage/
        security-posture-site/dist/
        security-posture-site/node_modules/
        security-posture-site/*.tsbuildinfo
        """
    ).lstrip()


def _build_validate_workflow() -> str:
    return "\n".join(
        [
            "name: Validate Security Posture Platform",
            "",
            "on:",
            "  pull_request:",
            "  push:",
            "    branches:",
            "      - main",
            "  workflow_dispatch:",
            "",
            "jobs:",
            "  validate-public-safety:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "",
            "      - uses: actions/setup-python@v5",
            "        with:",
            "          python-version: '3.14'",
            "",
            "      - name: Scan for private or machine-specific content",
            "        run: |",
            "          python - <<'PY'",
            "          from pathlib import Path",
            "          import sys",
            "",
            "          forbidden_patterns = (",
            "              'C:\\\\Users\\\\',",
            "              '/Users/',",
            "              'private-repo-boundary-manifest.json',",
            "              'ryankelley1992@outlook.com',",
            "              'DOCINT_SQL_CONNECTION_STRING=',",
            "              'AccountKey=',",
            "              'SharedAccessSignature=',",
            "              'DefaultEndpointsProtocol=',",
            "              '-----BEGIN PRIVATE KEY-----',",
            "          )",
            "",
            "          violations = []",
            "          for path in Path('.').rglob('*'):",
            "              if (",
            "                  not path.is_file()",
            "                  or '.git' in path.parts",
            "                  or path.as_posix() == '.github/workflows/validate.yml'",
            "              ):",
            "                  continue",
            "              try:",
            "                  text = path.read_text(encoding='utf-8')",
            "              except UnicodeDecodeError:",
            "                  continue",
            "              for pattern in forbidden_patterns:",
            "                  if pattern in text:",
            "                      violations.append(f'{path}: {pattern}')",
            "          if violations:",
            "              print('Public safety audit failed:')",
            "              for violation in violations:",
            "                  print(violation)",
            "              sys.exit(1)",
            "          PY",
            "",
            "  validate-site:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "",
            "      - uses: actions/setup-node@v4",
            "        with:",
            "          node-version: '22'",
            "",
            "      - name: Install site dependencies",
            "        working-directory: security-posture-site",
            "        run: npm install",
            "",
            "      - name: Run site tests",
            "        working-directory: security-posture-site",
            "        run: npm test",
            "",
            "      - name: Build site",
            "        working-directory: security-posture-site",
            "        run: npm run build",
            "",
            "  validate-api:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "",
            "      - uses: actions/setup-python@v5",
            "        with:",
            "          python-version: '3.14'",
            "",
            "      - name: Install API dependencies",
            "        working-directory: security-posture-api",
            "        run: |",
            "          python -m pip install --upgrade pip",
            "          pip install -r requirements.txt",
            "          pip install -e .[dev]",
            "",
            "      - name: Run API tests",
            "        working-directory: security-posture-api",
            "        run: pytest tests/unit",
            "",
        ]
    )


def _build_readme(packages: tuple[SecurityPostureSubtreePackage, ...]) -> str:
    package_lines = "\n".join(
        f"- `{package.source_relative_path}` -> `{package.destination_directory_name}/`"
        for package in packages
    )
    return "\n".join(
        [
            "# Security Posture Platform",
            "",
            (
                "This repository is the public-safe demonstration surface for the "
                "Ryan security"
            ),
            "posture experience.",
            "",
            "It keeps the extracted frontend site package and the matching standalone",
            "Azure Functions API package together without the private operator shell,",
            (
                "private review routes, tenant-specific deployment scripts, or "
                "secret-bearing"
            ),
            "environment files.",
            "",
            "It is intended for public demonstration only. The private",
            "`hybrid-document-intelligence-platform` repo remains the live operational",
            "source of truth.",
            "",
            "## Included Packages",
            "",
            package_lines,
            "",
            "## Validation",
            "",
            "```powershell",
            "Set-Location security-posture-site",
            "npm install",
            "npm test",
            "npm run build",
            "",
            "Set-Location ..\\security-posture-api",
            "pip install -r requirements.txt",
            "pip install -e .[dev]",
            "pytest tests/unit",
            "```",
            "",
            "## Refresh From The Private Repo",
            "",
            "From the private repo root, rebuild the demonstration export with:",
            "",
            "```powershell",
            "python scripts/extract_public_security_site_package.py",
            "python scripts/extract_public_security_api_package.py",
            "python scripts/build_public_security_posture_subtree.py",
            "python scripts/export_public_security_posture_repo.py",
            "```",
            "",
            "## CI",
            "",
            "A standalone-repo validation workflow is included at",
            "`.github/workflows/validate.yml` so the public repository validates both",
            (
                "packages and fails fast if machine-specific paths or secret-bearing "
                "content"
            ),
            "leak into the export.",
            "",
        ]
    )