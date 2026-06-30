from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_DIRECTORY_BROWSE_ENTRIES = 500
MAX_FILE_BROWSE_ENTRIES = 500


def normalize_picked_directory(value: str) -> str:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"selected path is not a directory: {path}")
    return str(path)


def workspace_name_from_directory(value: str) -> str:
    path = Path(value)
    return path.name or str(path)


def normalize_browse_directory(value: Any = None) -> Path:
    text = str(value or "").strip()
    path = Path.cwd() if not text else Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("path must be an absolute directory path")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"path is not a directory: {resolved}")
    return resolved


def browse_directory(value: Any = None) -> dict[str, Any]:
    path = normalize_browse_directory(value)
    entries: list[dict[str, str]] = []
    for child in path.iterdir():
        try:
            if not child.is_dir():
                continue
            resolved_child = child.resolve()
        except OSError:
            continue
        entries.append({"name": child.name, "path": str(resolved_child)})
    entries.sort(key=lambda item: item["name"].casefold())
    parent = path.parent if path.parent != path else None
    try:
        home = Path.home().expanduser().resolve()
        home_path = str(home) if home.is_dir() else None
    except OSError:
        home_path = None
    return {
        "path": str(path),
        "parent": str(parent) if parent else None,
        "home": home_path,
        "entries": entries[:MAX_DIRECTORY_BROWSE_ENTRIES],
        "truncated": len(entries) > MAX_DIRECTORY_BROWSE_ENTRIES,
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalize_workspace_file_root(value: Any) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError("workspace has no working_directory")
    root = Path(text).expanduser()
    if not root.is_absolute():
        raise ValueError("workspace working_directory must be absolute")
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError(f"workspace working_directory is not a directory: {resolved}")
    return resolved


def normalize_workspace_file_browse_path(*, root: Any, path: Any = None) -> tuple[Path, Path]:
    resolved_root = _normalize_workspace_file_root(root)
    text = str(path or "").strip()
    candidate = resolved_root if not text else Path(text).expanduser()
    if not candidate.is_absolute():
        raise ValueError("path must be an absolute path")
    resolved_path = candidate.resolve()
    if not _is_relative_to(resolved_path, resolved_root):
        raise PermissionError("path is outside the workspace root")
    if not resolved_path.is_dir():
        raise ValueError(f"path is not a directory: {resolved_path}")
    return resolved_root, resolved_path


def _workspace_relative_path(path: Path, root: Path) -> str:
    return "" if path == root else path.relative_to(root).as_posix()


def browse_workspace_files(*, root: Any, path: Any = None) -> dict[str, Any]:
    resolved_root, resolved_path = normalize_workspace_file_browse_path(root=root, path=path)
    entries: list[dict[str, str]] = []
    for child in resolved_path.iterdir():
        try:
            resolved_child = child.resolve()
            if not _is_relative_to(resolved_child, resolved_root):
                continue
            if resolved_child.is_dir():
                kind = "directory"
            elif resolved_child.is_file():
                kind = "file"
            else:
                continue
        except OSError:
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(resolved_child),
                "workspace_relative_path": _workspace_relative_path(resolved_child, resolved_root),
                "kind": kind,
            }
        )
    entries.sort(key=lambda item: (0 if item["kind"] == "directory" else 1, item["name"].casefold(), item["name"]))
    parent = None
    if resolved_path != resolved_root:
        candidate_parent = resolved_path.parent.resolve()
        if _is_relative_to(candidate_parent, resolved_root):
            parent = str(candidate_parent)
    return {
        "root": str(resolved_root),
        "path": str(resolved_path),
        "parent": parent,
        "entries": entries[:MAX_FILE_BROWSE_ENTRIES],
        "truncated": len(entries) > MAX_FILE_BROWSE_ENTRIES,
    }


def _pick_directory_macos() -> str | None:
    script = 'POSIX path of (choose folder with prompt "Choose a workspace directory")'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode == 0:
        picked = result.stdout.strip()
        return normalize_picked_directory(picked) if picked else None
    if "User canceled" in result.stderr or "(-128)" in result.stderr:
        return None
    message = result.stderr.strip() or result.stdout.strip() or "directory picker failed"
    raise RuntimeError(message)


def _pick_directory_linux() -> str | None:
    commands = [
        ["zenity", "--file-selection", "--directory", "--title=Choose a workspace directory"],
        ["kdialog", "--getexistingdirectory"],
    ]
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode == 0:
            picked = result.stdout.strip()
            return normalize_picked_directory(picked) if picked else None
        if result.returncode in {1, 255}:
            return None
        message = result.stderr.strip() or result.stdout.strip() or "directory picker failed"
        raise RuntimeError(message)
    raise RuntimeError("no supported system directory picker is available")


def _pick_directory_windows() -> str | None:
    script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose a workspace directory'
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::WriteLine($dialog.SelectedPath)
}
""".strip()
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Sta", "-Command", script],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode == 0:
        picked = result.stdout.strip()
        return normalize_picked_directory(picked) if picked else None
    message = result.stderr.strip() or result.stdout.strip() or "directory picker failed"
    raise RuntimeError(message)


def pick_directory() -> str | None:
    if sys.platform == "darwin":
        return _pick_directory_macos()
    if sys.platform.startswith("win"):
        return _pick_directory_windows()
    return _pick_directory_linux()
