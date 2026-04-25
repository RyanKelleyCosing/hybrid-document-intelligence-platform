"""Unit tests for configured-folder discovery helpers."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from document_intelligence.utils import configured_folder


def test_list_configured_folder_assets_skips_temp_zero_byte_and_fresh_files(
    tmp_path: Path,
) -> None:
    """Configured-folder listing should ignore unstable and temporary drops."""

    folder_root = tmp_path / "watched"
    folder_root.mkdir()
    stable_file = folder_root / "stable.pdf"
    fresh_file = folder_root / "fresh.pdf"
    zero_byte_file = folder_root / "empty.pdf"
    temp_file = folder_root / "~$statement.pdf"

    stable_file.write_bytes(b"stable-pdf")
    fresh_file.write_bytes(b"fresh-pdf")
    zero_byte_file.write_bytes(b"")
    temp_file.write_bytes(b"temp")

    stable_timestamp = (datetime.now(UTC) - timedelta(minutes=5)).timestamp()
    os.utime(stable_file, (stable_timestamp, stable_timestamp))

    listed_assets = configured_folder.list_configured_folder_assets(
        file_pattern="*.pdf",
        folder_path=str(folder_root),
        min_stable_age_seconds=60,
        recursive=False,
    )

    assert tuple(asset.relative_path for asset in listed_assets) == ("stable.pdf",)


def test_list_configured_folder_assets_skips_inaccessible_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Transient access failures should not abort one configured-folder scan."""

    folder_root = tmp_path / "watched"
    folder_root.mkdir()
    stable_file = folder_root / "stable.pdf"
    inaccessible_file = folder_root / "locked.pdf"
    stable_file.write_bytes(b"stable-pdf")
    inaccessible_file.write_bytes(b"locked-pdf")

    original_stat = Path.stat

    def fake_stat(self: Path, *args: object, **kwargs: object):
        if self.name == "locked.pdf":
            raise PermissionError("file is locked")

        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)

    listed_assets = configured_folder.list_configured_folder_assets(
        file_pattern="*.pdf",
        folder_path=str(folder_root),
        recursive=False,
    )

    assert tuple(asset.relative_path for asset in listed_assets) == ("stable.pdf",)
