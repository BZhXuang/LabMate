"""Skill loading and matching."""

from __future__ import annotations

import json
from pathlib import Path

SKILLS_DIR = Path(__file__).parent / "definitions"

INTENT_TO_SKILL = {
    "lab_equipment": "equipment_status",
    "lab_booking": "equipment_booking",
    "lab_maintenance": "equipment_maintenance",
}


def load_skills() -> list[dict]:
    skills: list[dict] = []
    if not SKILLS_DIR.exists():
        return skills
    for path in sorted(SKILLS_DIR.glob("*.json")):
        skills.append(json.loads(path.read_text(encoding="utf-8")))
    return skills


def skill_by_name(name: str) -> dict | None:
    for skill in load_skills():
        if skill.get("name") == name:
            return skill
    return None


def match_skill(query: str, intent_label: str = "") -> dict | None:
    """Load at most one skill: trigger phrase first, then intent map."""
    for skill in load_skills():
        if any(trigger in query for trigger in skill.get("triggers", [])):
            return skill
    mapped = INTENT_TO_SKILL.get(intent_label)
    if mapped:
        return skill_by_name(mapped)
    return None
