from __future__ import annotations

from pathlib import Path

import pytest

from workspace_agent_relay_mcp.local_context import normalize_local_context
from workspace_agent_relay_mcp.workspace_directories import browse_workspace_files


def test_selected_file_validation_stores_metadata_without_contents(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    selected = root / "src.py"
    selected.write_text("SECRET_FILE_CONTENT", encoding="utf-8")

    context = normalize_local_context(
        {
            "selected_files": [
                {
                    "path": str(selected),
                    "workspace_relative_path": "ignored.py",
                    "content": "SECRET_FILE_CONTENT",
                }
            ]
        },
        working_directory_snapshot=str(root),
    )

    assert context == {
        "selected_files": [
            {
                "path": str(selected.resolve()),
                "workspace_relative_path": "src.py",
                "reason": "user_selected",
            }
        ]
    }
    assert "SECRET_FILE_CONTENT" not in str(context)


def test_selected_file_validation_rejects_bad_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    inside_file = root / "inside.txt"
    inside_file.write_text("inside", encoding="utf-8")
    outside_file = outside / "outside.txt"
    outside_file.write_text("outside", encoding="utf-8")
    inside_dir = root / "dir"
    inside_dir.mkdir()

    with pytest.raises(ValueError, match="absolute"):
        normalize_local_context({"selected_files": [{"path": "relative.txt"}]}, working_directory_snapshot=str(root))

    with pytest.raises(ValueError, match="file"):
        normalize_local_context({"selected_files": [{"path": str(inside_dir)}]}, working_directory_snapshot=str(root))

    with pytest.raises(ValueError, match="outside"):
        normalize_local_context({"selected_files": [{"path": str(outside_file)}]}, working_directory_snapshot=str(root))

    symlink = root / "escape.txt"
    try:
        symlink.symlink_to(outside_file)
    except OSError as exc:
        pytest.skip(f"symlink unsupported: {exc}")
    with pytest.raises(ValueError, match="outside"):
        normalize_local_context({"selected_files": [{"path": str(symlink)}]}, working_directory_snapshot=str(root))


def test_workspace_file_browse_lists_metadata_and_rejects_escapes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pkg").mkdir()
    app = root / "app.py"
    app.write_text("SECRET_FILE_CONTENT", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()

    payload = browse_workspace_files(root=str(root), path=str(root))

    assert payload["root"] == str(root.resolve())
    assert payload["path"] == str(root.resolve())
    assert payload["parent"] is None
    assert payload["truncated"] is False
    assert payload["entries"] == [
        {
            "name": "pkg",
            "path": str((root / "pkg").resolve()),
            "workspace_relative_path": "pkg",
            "kind": "directory",
        },
        {
            "name": "app.py",
            "path": str(app.resolve()),
            "workspace_relative_path": "app.py",
            "kind": "file",
        },
    ]
    assert "SECRET_FILE_CONTENT" not in str(payload)

    with pytest.raises(ValueError, match="absolute"):
        browse_workspace_files(root=str(root), path="relative")

    with pytest.raises(PermissionError, match="outside"):
        browse_workspace_files(root=str(root), path=str(outside))

    symlink = root / "outside-link"
    try:
        symlink.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unsupported: {exc}")
    with pytest.raises(PermissionError, match="outside"):
        browse_workspace_files(root=str(root), path=str(symlink))
