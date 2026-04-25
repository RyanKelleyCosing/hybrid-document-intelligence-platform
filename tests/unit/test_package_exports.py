"""Unit tests for document_intelligence package exports."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def isolated_document_intelligence_modules() -> Iterator[None]:
    """Snapshot and restore ``sys.modules`` entries for ``document_intelligence``.

    Popping submodules without restoring them rebinds class identity for any
    later test that lazily re-imports them, which breaks pydantic instance
    checks against models loaded earlier in the session.
    """
    saved = {
        name: module
        for name, module in sys.modules.items()
        if name == "document_intelligence" or name.startswith("document_intelligence.")
    }
    for name in saved:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        # Drop any modules imported during the test, then restore the originals
        # so subsequent tests observe the same class objects they imported at
        # collection time.
        for name in [
            n
            for n in list(sys.modules)
            if n == "document_intelligence" or n.startswith("document_intelligence.")
        ]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_package_exports_load_lazily() -> None:
    """The package root should defer heavy backend imports until requested."""
    with isolated_document_intelligence_modules():
        package = importlib.import_module("document_intelligence")

        assert "document_intelligence.account_matching" not in sys.modules

        _ = package.match_document_to_account

        assert "document_intelligence.account_matching" in sys.modules