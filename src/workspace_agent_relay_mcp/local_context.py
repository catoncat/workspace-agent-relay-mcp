from __future__ import annotations

from pathlib import Path
from typing import Any


MAX_SELECTED_FILES = 20
MAX_SELECTED_FILE_REASON_LEN = 80


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalized_root(working_directory_snapshot: Any = None) -> Path | None:
    if working_directory_snapshot is None:
        return None
    text = str(working_directory_snapshot).strip()
    if not text:
        return None
    root = Path(text).expanduser()
    if not root.is_absolute():
        raise ValueError("working_directory_snapshot must be an absolute path")
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError(f"working_directory_snapshot is not a directory: {resolved}")
    return resolved


def normalize_selected_files(
    value: Any,
    *,
    working_directory_snapshot: Any = None,
) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("local_context.selected_files must be a list")
    if len(value) > MAX_SELECTED_FILES:
        raise ValueError(f"local_context.selected_files must not exceed {MAX_SELECTED_FILES} items")
    root = _normalized_root(working_directory_snapshot)
    normalized: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"local_context.selected_files[{index}] must be an object")
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            raise ValueError(f"local_context.selected_files[{index}].path is required")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ValueError(f"local_context.selected_files[{index}].path must be absolute")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"local_context.selected_files[{index}].path is not readable: {raw_path}") from exc
        if not resolved.is_file():
            raise ValueError(f"local_context.selected_files[{index}].path must be a file")
        workspace_relative_path = ""
        if root is not None:
            if not _inside_root(resolved, root):
                raise ValueError(f"local_context.selected_files[{index}].path is outside the workspace root")
            workspace_relative_path = resolved.relative_to(root).as_posix()
        elif item.get("workspace_relative_path") is not None:
            candidate = str(item.get("workspace_relative_path") or "").strip()
            if candidate and not Path(candidate).is_absolute() and ".." not in Path(candidate).parts:
                workspace_relative_path = candidate
        resolved_text = str(resolved)
        if resolved_text in seen_paths:
            continue
        seen_paths.add(resolved_text)
        reason = str(item.get("reason") or "user_selected").strip() or "user_selected"
        normalized.append(
            {
                "path": resolved_text,
                "workspace_relative_path": workspace_relative_path,
                "reason": reason[:MAX_SELECTED_FILE_REASON_LEN],
            }
        )
    return normalized


def normalize_local_context(
    value: Any,
    *,
    working_directory_snapshot: Any = None,
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("local_context must be an object")
    allowed = {"selected_files"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unsupported local_context field(s): {', '.join(unknown)}")
    selected_files = normalize_selected_files(
        value.get("selected_files"),
        working_directory_snapshot=working_directory_snapshot,
    )
    context: dict[str, Any] = {}
    if selected_files:
        context["selected_files"] = selected_files
    return context
