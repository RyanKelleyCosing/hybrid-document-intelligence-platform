"""Unit tests for the combined public security-posture subtree builder."""

from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.security_posture_public_subtree import (
    build_security_posture_public_subtree,
)


def test_build_security_posture_public_subtree_copies_declared_files_only(
    tmp_path: Path,
) -> None:
    """The subtree builder should exclude undeclared build artifacts."""

    repo_root = tmp_path / "repo"
    site_package = repo_root / "public-derivatives" / "security-posture-site"
    api_package = repo_root / "public-derivatives" / "security-posture-api"
    site_package.mkdir(parents=True)
    api_package.mkdir(parents=True)

    _write_derivative_package(
        site_package,
        package_name="ryan-security-posture-site",
        declared_files=("README.md", "src/App.tsx"),
        extra_files=("node_modules/left-pad/index.js",),
    )
    _write_derivative_package(
        api_package,
        package_name="ryan-security-posture-api",
        declared_files=("README.md", "function_app.py"),
        extra_files=("__pycache__/function_app.cpython-314.pyc",),
    )

    output_directory = repo_root / "public-subtrees" / "security-posture-platform"
    packages = build_security_posture_public_subtree(
        repo_root=repo_root,
        output_directory=output_directory,
        site_package_directory=Path("public-derivatives/security-posture-site"),
        api_package_directory=Path("public-derivatives/security-posture-api"),
    )

    assert (output_directory / "security-posture-site" / "README.md").is_file()
    assert (output_directory / "security-posture-site" / "src" / "App.tsx").is_file()
    assert (output_directory / ".github" / "workflows" / "validate.yml").is_file()
    assert not (
        output_directory
        / "security-posture-site"
        / "node_modules"
        / "left-pad"
        / "index.js"
    ).exists()
    assert (output_directory / "security-posture-api" / "function_app.py").is_file()
    assert not (
        output_directory
        / "security-posture-api"
        / "__pycache__"
        / "function_app.cpython-314.pyc"
    ).exists()
    assert [package.destination_directory_name for package in packages] == [
        "security-posture-site",
        "security-posture-api",
    ]
    subtree_readme = (output_directory / "README.md").read_text(encoding="utf-8")
    workflow_text = (
        output_directory / ".github" / "workflows" / "validate.yml"
    ).read_text(encoding="utf-8")
    subtree_sources = json.loads(
        (output_directory / "subtree-sources.json").read_text(encoding="utf-8")
    )
    expected_workflow_lines = [
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
    ]

    assert subtree_readme.startswith("# Security Posture Platform\n")
    assert "public demonstration only" in subtree_readme
    assert workflow_text.splitlines() == expected_workflow_lines
    assert ".github/workflows/validate.yml" in subtree_sources["generated_files"]
    assert "python scripts/export_public_security_posture_repo.py" in subtree_readme


def test_build_security_posture_public_subtree_supports_string_metadata_lists(
    tmp_path: Path,
) -> None:
    """The subtree builder should support string-only metadata lists."""

    repo_root = tmp_path / "repo"
    site_package = repo_root / "public-derivatives" / "security-posture-site"
    api_package = repo_root / "public-derivatives" / "security-posture-api"
    site_package.mkdir(parents=True)
    api_package.mkdir(parents=True)

    _write_string_metadata_package(
        site_package,
        package_name="ryan-security-posture-site",
        copied_files=("src/components/SecurityPostureSite.tsx",),
        generated_files=("README.md",),
        validation_files=("src/components/SecurityPostureSite.test.tsx",),
    )
    _write_string_metadata_package(
        api_package,
        package_name="ryan-security-posture-api",
        copied_files=("src/security_posture_api/public_request_context.py",),
        generated_files=("README.md",),
        validation_files=("tests/unit/test_public_request_context.py",),
    )

    output_directory = repo_root / "public-subtrees" / "security-posture-platform"
    build_security_posture_public_subtree(
        repo_root=repo_root,
        output_directory=output_directory,
        site_package_directory=Path("public-derivatives/security-posture-site"),
        api_package_directory=Path("public-derivatives/security-posture-api"),
    )

    assert (
        output_directory
        / "security-posture-site"
        / "src"
        / "components"
        / "SecurityPostureSite.tsx"
    ).is_file()
    assert (
        output_directory
        / "security-posture-site"
        / "src"
        / "components"
        / "SecurityPostureSite.test.tsx"
    ).is_file()
    assert (
        output_directory
        / "security-posture-api"
        / "src"
        / "security_posture_api"
        / "public_request_context.py"
    ).is_file()
    assert (
        output_directory
        / "security-posture-api"
        / "tests"
        / "unit"
        / "test_public_request_context.py"
    ).is_file()


def _write_derivative_package(
    package_directory: Path,
    *,
    package_name: str,
    declared_files: tuple[str, ...],
    extra_files: tuple[str, ...],
) -> None:
    metadata = {
        "package_name": package_name,
        "copied_files": [],
        "generated_files": list(declared_files),
        "validation_files": [],
    }
    (package_directory / "derivative-sources.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    for relative_path in declared_files:
        destination_path = package_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(relative_path, encoding="utf-8")

    for relative_path in extra_files:
        destination_path = package_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(relative_path, encoding="utf-8")


def _write_string_metadata_package(
    package_directory: Path,
    *,
    package_name: str,
    copied_files: tuple[str, ...],
    generated_files: tuple[str, ...],
    validation_files: tuple[str, ...],
) -> None:
    metadata = {
        "package_name": package_name,
        "copied_files": list(copied_files),
        "generated_files": list(generated_files),
        "validation_files": list(validation_files),
    }
    (package_directory / "derivative-sources.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    for relative_path in copied_files + generated_files + validation_files:
        destination_path = package_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(relative_path, encoding="utf-8")