from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from ..deps import json_body
from ..errors import json_error
from ..validation import missing_fields

MAX_DIRECTORY_BROWSE_ENTRIES = 500


def _normalize_picked_directory(value: str) -> str:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"selected path is not a directory: {path}")
    return str(path)


def _workspace_name_from_directory(value: str) -> str:
    path = Path(value)
    return path.name or str(path)


def _normalize_browse_directory(value: Any = None) -> Path:
    text = str(value or "").strip()
    path = Path.home() if not text else Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("path must be an absolute directory path")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"path is not a directory: {resolved}")
    return resolved


def browse_directory(value: Any = None) -> dict[str, Any]:
    path = _normalize_browse_directory(value)
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
        return _normalize_picked_directory(picked) if picked else None
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
            return _normalize_picked_directory(picked) if picked else None
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
        return _normalize_picked_directory(picked) if picked else None
    message = result.stderr.strip() or result.stdout.strip() or "directory picker failed"
    raise RuntimeError(message)


def pick_directory() -> str | None:
    if sys.platform == "darwin":
        return _pick_directory_macos()
    if sys.platform.startswith("win"):
        return _pick_directory_windows()
    return _pick_directory_linux()


def workspace_routes(store: Any) -> list[tuple]:
    async def list_workspaces(_: Request) -> JSONResponse:
        return JSONResponse(store.list_workspaces())

    async def browse_workspace_directories(request: Request) -> JSONResponse:
        try:
            payload = await run_in_threadpool(
                browse_directory,
                request.query_params.get("path"),
            )
        except PermissionError as exc:
            return json_error(str(exc), status_code=403)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        except OSError as exc:
            return json_error(str(exc), status_code=500)
        return JSONResponse(payload)

    async def pick_workspace_directory(_: Request) -> JSONResponse:
        try:
            picked = await run_in_threadpool(pick_directory)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            return json_error(str(exc), status_code=500)
        if picked is None:
            return JSONResponse({"working_directory": None, "name": None})
        return JSONResponse(
            {
                "working_directory": picked,
                "name": _workspace_name_from_directory(picked),
            }
        )

    async def create_workspace(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        missing = missing_fields(payload, ("name",))
        if missing:
            return json_error(f"missing required field(s): {', '.join(missing)}")
        try:
            workspace = store.create_workspace(
                name=str(payload["name"]),
                working_directory=payload.get("working_directory"),
            )
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        return JSONResponse(workspace)

    async def update_workspace(request: Request) -> JSONResponse:
        workspace_id = int(request.path_params["workspace_id"])
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        if not payload:
            return json_error("request body must not be empty", status_code=400)
        allowed = {"name", "working_directory"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            return json_error(f"unsupported field(s): {', '.join(unknown)}", status_code=400)
        updates = {key: payload[key] for key in allowed if key in payload}
        try:
            workspace = store.update_workspace(workspace_id, **updates)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        return JSONResponse(workspace)

    async def delete_workspace(request: Request) -> JSONResponse:
        workspace_id = int(request.path_params["workspace_id"])
        try:
            store.delete_workspace(workspace_id)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        return JSONResponse({"success": True})

    return [
        ("/api/workspaces", list_workspaces, ["GET"]),
        ("/api/workspaces/browse-directories", browse_workspace_directories, ["GET"]),
        ("/api/workspaces/pick-directory", pick_workspace_directory, ["POST"]),
        ("/api/workspaces", create_workspace, ["POST"]),
        ("/api/workspaces/{workspace_id:int}", update_workspace, ["PATCH"]),
        ("/api/workspaces/{workspace_id:int}", delete_workspace, ["DELETE"]),
    ]
