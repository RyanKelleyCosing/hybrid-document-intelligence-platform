"""Unit tests for document_intelligence package exports."""

from __future__ import annotations

import importlib
import sys


def clear_document_intelligence_modules() -> None:
    """Remove cached document_intelligence modules for a clean import."""
    stale_module_names = [
        module_name
        for module_name in list(sys.modules)
        if module_name == "document_intelligence"
        or module_name.startswith("document_intelligence.")
    ]

    for module_name in stale_module_names:
        sys.modules.pop(module_name, None)


def test_package_exports_load_lazily() -> None:
    """The package root should defer heavy backend imports until requested."""
    clear_document_intelligence_modules()

    package = importlib.import_module("document_intelligence")

    assert "document_intelligence.account_matching" not in sys.modules

    _ = package.match_document_to_account

    assert "document_intelligence.account_matching" in sys.modules