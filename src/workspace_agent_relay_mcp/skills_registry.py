from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MAX_SKILLS = 50
MAX_DESCRIPTION_LEN = 240


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: str
    scope: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "scope": self.scope,
        }


def _strip_yaml_scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_skill_frontmatter(path: Path) -> SkillMetadata | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline()
            if first.strip() != "---":
                return None
            fields: dict[str, str] = {}
            for line in handle:
                stripped = line.strip()
                if stripped == "---":
                    break
                if not stripped or stripped.startswith("#") or ":" not in line:
                    continue
                key, raw_value = line.split(":", 1)
                key = key.strip()
                if key in {"name", "description"}:
                    fields[key] = _strip_yaml_scalar(raw_value)
            else:
                return None
    except (OSError, UnicodeDecodeError):
        return None
    name = fields.get("name", "").strip()
    description = " ".join(fields.get("description", "").strip().split())
    if not name or not description:
        return None
    return SkillMetadata(
        name=name,
        description=description[:MAX_DESCRIPTION_LEN],
        path=str(path.resolve()),
        scope="",
    )


def _skill_files_under(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return []
    files: list[Path] = []
    for child in children:
        skill_file = child / "SKILL.md"
        if skill_file.is_file():
            files.append(skill_file)
    return files


def _project_roots(working_directory: Any = None) -> list[Path]:
    text = str(working_directory or "").strip()
    if not text:
        return []
    path = Path(text).expanduser()
    if not path.is_absolute():
        return []
    try:
        root = path.resolve()
    except OSError:
        return []
    return [root / ".agents" / "skills", root / ".codex" / "skills"]


def _global_roots(home: Path | None = None) -> list[Path]:
    resolved_home = (home or Path.home()).expanduser()
    return [
        resolved_home / ".agents" / "skills",
        resolved_home / ".codex" / "skills",
        resolved_home / ".codex" / "skills" / ".system",
    ]


def list_available_skills(
    *,
    working_directory: Any = None,
    home: Path | None = None,
    limit: int = MAX_SKILLS,
) -> list[dict[str, str]]:
    capped_limit = max(0, min(int(limit), MAX_SKILLS))
    if capped_limit == 0:
        return []
    candidates: list[tuple[int, str, Path]] = []
    for order, root in enumerate(_project_roots(working_directory)):
        candidates.extend((order, "project", path) for path in _skill_files_under(root))
    offset = len(_project_roots(working_directory))
    for order, root in enumerate(_global_roots(home), start=offset):
        candidates.extend((order, "global", path) for path in _skill_files_under(root))

    collected: list[SkillMetadata] = []
    seen_names: set[str] = set()
    for _, scope, path in sorted(candidates, key=lambda item: (0 if item[1] == "project" else 1, item[2].parent.name.casefold(), str(item[2]))):
        parsed = parse_skill_frontmatter(path)
        if parsed is None:
            continue
        key = parsed.name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        collected.append(
            SkillMetadata(
                name=parsed.name,
                description=parsed.description,
                path=parsed.path,
                scope=scope,
            )
        )
        if len(collected) >= capped_limit:
            break
    collected.sort(key=lambda item: (0 if item.scope == "project" else 1, item.name.casefold(), item.path))
    return [item.to_dict() for item in collected[:capped_limit]]
