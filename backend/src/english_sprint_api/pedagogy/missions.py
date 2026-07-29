from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MISSIONS_ROOT = PROJECT_ROOT / "missions"


@dataclass(frozen=True, slots=True)
class MissionDefinition:
    id: UUID
    slug: str
    version: int
    title: str
    description: str
    scenario: str
    initial_question: str
    transfer_question: str
    target_skills: tuple[str, ...]
    expected_duration_minutes: int
    difficulty: str
    language_policy: str
    correction_policy: str
    maximum_attempts: int
    maximum_corrections: int
    completion_rules: str
    prompt_context: str


class MissionCatalog:
    def __init__(self, root: Path = MISSIONS_ROOT) -> None:
        definitions = [self._load(path) for path in sorted(root.glob("*.json"))]
        self._by_id = {definition.id: definition for definition in definitions}
        self._by_slug = {definition.slug: definition for definition in definitions}
        if len(self._by_id) != len(definitions) or len(self._by_slug) != len(definitions):
            raise ValueError("Mission IDs and slugs must be unique.")

    @staticmethod
    def _load(path: Path) -> MissionDefinition:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw["maximum_attempts"] != 3:
            raise ValueError(f"{path.name} must define exactly three attempts.")
        if raw["maximum_corrections"] not in {1, 2}:
            raise ValueError(f"{path.name} must limit corrections to one or two.")
        if raw["initial_question"] == raw["transfer_question"]:
            raise ValueError(f"{path.name} transfer question must use a new context.")
        return MissionDefinition(
            id=UUID(raw["id"]),
            slug=raw["slug"],
            version=raw["version"],
            title=raw["title"],
            description=raw["description"],
            scenario=raw["scenario"],
            initial_question=raw["initial_question"],
            transfer_question=raw["transfer_question"],
            target_skills=tuple(raw["target_skills"]),
            expected_duration_minutes=raw["expected_duration_minutes"],
            difficulty=raw["difficulty"],
            language_policy=raw["language_policy"],
            correction_policy=raw["correction_policy"],
            maximum_attempts=raw["maximum_attempts"],
            maximum_corrections=raw["maximum_corrections"],
            completion_rules=raw["completion_rules"],
            prompt_context=raw["prompt_context"],
        )

    def list(self) -> tuple[MissionDefinition, ...]:
        return tuple(sorted(self._by_id.values(), key=lambda item: item.slug))

    def get(self, mission_id: UUID) -> MissionDefinition | None:
        return self._by_id.get(mission_id)


class TutorInstructionBuilder:
    @staticmethod
    def scenario(mission: MissionDefinition) -> str:
        return (
            f"{mission.scenario} Answer naturally. Do not worry about being perfect. "
            f"{mission.initial_question}"
        )

    @staticmethod
    def retry() -> str:
        return "Now answer again. Use the corrected structure, but respond in your own words."

    @staticmethod
    def transfer(mission: MissionDefinition) -> str:
        return mission.transfer_question

    @staticmethod
    def filler() -> str:
        return "Thank you. I am selecting the most important improvement."
