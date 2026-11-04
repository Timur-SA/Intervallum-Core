"""Domain types for the Intervallum-Core v2 data core (OGE track)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    SINGLE = "single"
    MULTI = "multi"
    MATCHING = "matching"
    CARDS = "cards"
    FORCES = "forces"
    INTERACTIVE = "interactive"


class Difficulty(int, Enum):
    EASY = 1
    MEDIUM = 2
    HARD = 3


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    section: str


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    boss: str
    item: str
    item_id: str
    color: str
    topics: tuple[str, ...]


@dataclass(frozen=True)
class OgeTask:
    id: str
    type: TaskType
    topic: str
    difficulty: int
    payload: dict[str, Any]

    @property
    def section(self) -> str | None:
        return None


@dataclass
class TaskStat:
    attempts: int = 0
    best_score: float = 0.0


@dataclass
class UserState:
    user_id: str
    xp_by_topic: dict[str, int] = field(default_factory=dict)
    explored_types: set[str] = field(default_factory=set)
    best_score_by_type: dict[str, float] = field(default_factory=dict)
    task_stats: dict[str, TaskStat] = field(default_factory=dict)
    best_xp_by_task: dict[str, int] = field(default_factory=dict)
    defeated_bosses: set[str] = field(default_factory=set)
    unlocked_sections: set[str] = field(default_factory=lambda: {"mechanics"})
    items: set[str] = field(default_factory=set)

    def is_new(self, task_id: str) -> bool:
        stat = self.task_stats.get(task_id)
        return stat is None or stat.attempts == 0

    def is_hard(self, task: OgeTask) -> bool:
        stat = self.task_stats.get(task.id)
        return task.difficulty >= 3 or (stat is not None and stat.best_score < 0.7)


@dataclass(frozen=True)
class GradeResultV2:
    task_id: str
    correct_answer: Any
    is_correct: bool
    outcome: str
    score: float
    xp_by_topic: dict[str, int]
    card_grade: int | None
    bonus_multiplier: float
    boss_status: dict[str, dict]
