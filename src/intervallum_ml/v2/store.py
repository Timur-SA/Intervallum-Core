"""In-memory store and application service for the v2 OGE data core."""

from __future__ import annotations

from pathlib import Path

from .content import OgeBank, load_oge_bank
from .grading import defeat_boss, grade_task
from .selector import select_train
from .types import GradeResultV2, UserState


class V2Store:
    def __init__(self, bank: OgeBank) -> None:
        self.bank = bank
        self.users: dict[str, UserState] = {}

    @classmethod
    def from_default(cls) -> "V2Store":
        candidates = [
            Path(__file__).resolve().parents[3] / "content" / "oge_2026",
            Path.cwd() / "content" / "oge_2026",
            Path("/app/content/oge_2026"),
        ]
        for path in candidates:
            if (path / "tasks.json").exists():
                return cls(load_oge_bank(path))
        raise FileNotFoundError("OGE content bank not found")

    def user(self, user_id: str) -> UserState:
        if user_id not in self.users:
            self.users[user_id] = UserState(user_id=user_id)
        return self.users[user_id]

    def select(
        self,
        user_id: str,
        *,
        count: int = 7,
        section_id: str | None = None,
        topic_id: str | None = None,
        type_filter: str | None = None,
        exclude_types: tuple[str, ...] = (),
        seed: str | None = None,
    ) -> list[dict]:
        return select_train(
            self.bank,
            self.user(user_id),
            count=count,
            section_id=section_id,
            topic_id=topic_id,
            type_filter=type_filter,
            exclude_types=exclude_types,
            seed=seed,
        )

    def grade(self, user_id: str, task_id: str, answer: dict | str | int) -> GradeResultV2:
        task = self.bank.tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        return grade_task(self.bank, self.user(user_id), task, answer)

    def defeat(self, user_id: str, section_id: str) -> dict:
        return defeat_boss(self.bank, self.user(user_id), section_id)

    def progress(self, user_id: str) -> dict:
        state = self.user(user_id)
        bosses = {
            section_id: {
                **self.bank.boss_status(section_id, state.xp_by_topic),
                "defeated": section_id in state.defeated_bosses,
            }
            for section_id in self.bank.sections
        }
        return {
            "user_id": user_id,
            "xp_by_topic": state.xp_by_topic,
            "total_xp": sum(state.xp_by_topic.values()),
            "explored_types": sorted(state.explored_types),
            "defeated_bosses": sorted(state.defeated_bosses),
            "unlocked_sections": sorted(state.unlocked_sections),
            "items": sorted(state.items),
            "bosses": bosses,
        }
