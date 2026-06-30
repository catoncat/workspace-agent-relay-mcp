from __future__ import annotations

from pathlib import Path

from workspace_agent_relay_mcp.skills_registry import list_available_skills, parse_skill_frontmatter


def _write_skill(root: Path, dirname: str, *, name: str, description: str, body: str = "") -> Path:
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_parse_skill_frontmatter_reads_metadata_without_body(tmp_path: Path) -> None:
    skill_path = _write_skill(
        tmp_path,
        "diagnose",
        name="diagnose",
        description="Disciplined diagnosis loop",
        body="SECRET_SKILL_BODY",
    )

    parsed = parse_skill_frontmatter(skill_path)

    assert parsed is not None
    assert parsed.name == "diagnose"
    assert parsed.description == "Disciplined diagnosis loop"
    assert "SECRET_SKILL_BODY" not in str(parsed)


def test_skills_registry_sorts_project_before_global_and_skips_invalid(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project_root = project / ".agents" / "skills"
    global_root = home / ".agents" / "skills"
    _write_skill(project_root, "project-skill", name="project-skill", description="Project first")
    _write_skill(global_root, "global-skill", name="global-skill", description="Global second")
    invalid = global_root / "invalid" / "SKILL.md"
    invalid.parent.mkdir(parents=True)
    invalid.write_text(
        "\n".join(
            [
                "---",
                "name: invalid",
                "---",
                "SECRET_SKILL_BODY",
            ]
        ),
        encoding="utf-8",
    )

    skills = list_available_skills(working_directory=str(project), home=home)

    assert [skill["name"] for skill in skills] == ["project-skill", "global-skill"]
    assert [skill["scope"] for skill in skills] == ["project", "global"]
    assert "SECRET_SKILL_BODY" not in str(skills)
