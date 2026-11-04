"""OGE content bank: loading, validation, public projection and boss thresholds."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .types import OgeTask, Section, TaskType, Topic

BASE_XP = 10


@dataclass(frozen=True)
class ContentIssue:
    severity: str
    code: str
    message: str
    task_id: str | None = None


@dataclass(frozen=True)
class OgeBank:
    sections: dict[str, Section]
    topics: dict[str, Topic]
    tasks: dict[str, OgeTask]
    issues: tuple[ContentIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def section_by_topic(self, topic_id: str) -> Section | None:
        topic = self.topics.get(topic_id)
        return self.sections.get(topic.section) if topic else None

    def topic_tasks(self, topic_id: str) -> list[OgeTask]:
        return [t for t in self.tasks.values() if t.topic == topic_id]

    def topic_max_xp(self, topic_id: str) -> int:
        return sum(
            BASE_XP * t.difficulty
            for t in self.topic_tasks(topic_id)
            if t.type != TaskType.CARDS
        )

    def topic_unlock_xp(self, topic_id: str) -> int:
        return int(self.topic_max_xp(topic_id) * 0.8 + 0.9999)

    def boss_xp_required(self, section_id: str) -> int:
        section = self.sections.get(section_id)
        if section is None:
            return 0
        return sum(self.topic_unlock_xp(t) for t in section.topics)

    def boss_status(self, section_id: str, xp_by_topic: dict[str, int]) -> dict:
        section = self.sections.get(section_id)
        if section is None:
            return {}
        xp = sum(xp_by_topic.get(t, 0) for t in section.topics)
        required = self.boss_xp_required(section_id)
        return {
            "section": section_id,
            "title": section.title,
            "boss": section.boss,
            "xp": xp,
            "required": required,
            "ready": xp >= required,
        }


def _issue(severity: str, code: str, message: str, task_id: str | None = None) -> ContentIssue:
    return ContentIssue(severity, code, message, task_id)


def validate_bank(bank: OgeBank) -> tuple[ContentIssue, ...]:
    issues: list[ContentIssue] = []
    for task in bank.tasks.values():
        if task.type not in set(TaskType):
            issues.append(_issue("error", "bad_type", f"Unknown task type {task.type}", task.id))
            continue
        if task.topic not in bank.topics:
            issues.append(_issue("error", "bad_topic", f"Unknown topic {task.topic}", task.id))
        if task.difficulty not in (1, 2, 3):
            issues.append(_issue("error", "bad_difficulty", "Difficulty must be 1..3", task.id))
        p = task.payload
        if task.type == TaskType.SINGLE:
            options = {o.get("id") for o in p.get("options", [])}
            if p.get("correctOptionId") not in options:
                issues.append(_issue("error", "bad_single", "correctOptionId is not in options", task.id))
        elif task.type == TaskType.MULTI:
            options = {o.get("id") for o in p.get("options", [])}
            correct = set(p.get("correctOptionIds", []))
            if not correct or not correct.issubset(options):
                issues.append(_issue("error", "bad_multi", "correctOptionIds must be a non-empty subset", task.id))
        elif task.type == TaskType.MATCHING:
            pairs = p.get("pairs", [])
            if len(pairs) < 2:
                issues.append(_issue("error", "bad_matching", "Matching needs at least two pairs", task.id))
            rights = [pair.get("right") for pair in pairs]
            if len(set(rights)) != len(rights):
                issues.append(_issue("error", "duplicate_right", "Matching right values must be unique", task.id))
        elif task.type == TaskType.CARDS:
            if not p.get("question") or not p.get("answer"):
                issues.append(_issue("error", "bad_card", "Card needs question and answer", task.id))
        elif task.type == TaskType.FORCES:
            refs = p.get("forceTask", {}).get("refs", [])
            if not refs:
                issues.append(_issue("error", "bad_forces", "Force task has no reference forces", task.id))
        elif task.type == TaskType.INTERACTIVE:
            find = p.get("physicsTask", {}).get("find", {})
            if "value" not in find:
                issues.append(_issue("error", "bad_interactive", "Interactive task has no target value", task.id))
    return tuple(issues)


def load_oge_bank(content_dir: str | Path) -> OgeBank:
    content_dir = Path(content_dir)
    topics_data = json.loads((content_dir / "topics.json").read_text(encoding="utf-8"))
    tasks_data = json.loads((content_dir / "tasks.json").read_text(encoding="utf-8"))

    sections: dict[str, Section] = {}
    for row in topics_data.get("sections", []):
        section = Section(
            id=str(row["id"]),
            title=str(row["title"]),
            boss=str(row.get("boss", "")),
            item=str(row.get("item", "")),
            item_id=str(row.get("item_id", "")),
            color=str(row.get("color", "")),
            topics=tuple(str(x) for x in row.get("topics", [])),
        )
        sections[section.id] = section

    topics: dict[str, Topic] = {}
    for row in topics_data.get("topics", []):
        topic = Topic(
            id=str(row["id"]),
            title=str(row["title"]),
            section=str(row["section"]),
        )
        topics[topic.id] = topic

    tasks: dict[str, OgeTask] = {}
    for row in tasks_data.get("tasks", []):
        task_id = str(row["id"])
        if task_id in tasks:
            raise ValueError(f"Duplicate OGE task id: {task_id}")
        task = OgeTask(
            id=task_id,
            type=TaskType(row["type"]),
            topic=str(row["topic"]),
            difficulty=int(row["difficulty"]),
            payload=dict(row),
        )
        tasks[task_id] = task

    bank = OgeBank(sections=sections, topics=topics, tasks=tasks)
    issues = validate_bank(bank)
    return OgeBank(sections=sections, topics=topics, tasks=tasks, issues=issues)


def public_task(task: OgeTask, *, is_new: bool, is_hard: bool) -> dict[str, Any]:
    """Return a task without answers, explanations or reference force vectors."""

    p = task.payload
    base: dict[str, Any] = {
        "id": task.id,
        "type": task.type.value,
        "topic": task.topic,
        "difficulty": task.difficulty,
        "isNew": is_new,
        "isHard": is_hard,
        "bonusMultiplier": 1.0 + (0.5 if is_new else 0.0) + (0.5 if is_hard else 0.0),
    }
    if task.type == TaskType.SINGLE:
        base.update({
            "prompt": p.get("prompt", ""),
            "options": p.get("options", []),
            "hint": p.get("hint"),
        })
    elif task.type == TaskType.MULTI:
        base.update({
            "prompt": p.get("prompt", ""),
            "options": p.get("options", []),
            "hint": p.get("hint"),
        })
    elif task.type == TaskType.MATCHING:
        pairs = p.get("pairs", [])
        rights = [pair.get("right") for pair in pairs]
        # Keep the right side available but decoupled from the correct mapping.
        base.update({
            "prompt": p.get("prompt", ""),
            "pairs": [{"id": pair.get("id"), "left": pair.get("left")} for pair in pairs],
            "rightOptions": rights,
        })
    elif task.type == TaskType.CARDS:
        base.update({
            "question": p.get("question", ""),
            "formula": p.get("formula"),
            "answerKind": p.get("answerKind"),
        })
    elif task.type == TaskType.FORCES:
        force_task = dict(p.get("forceTask", {}))
        force_task.pop("refs", None)
        force_task.pop("assessment", None)
        base.update({
            "forceTask": force_task,
            "forceCount": len(p.get("forceTask", {}).get("refs", [])),
        })
    elif task.type == TaskType.INTERACTIVE:
        physics = dict(p.get("physicsTask", {}))
        find = dict(physics.get("find", {}))
        find.pop("value", None)
        find.pop("targetFormula", None)
        physics["find"] = find
        physics.pop("explanation", None)
        base.update({"physicsTask": physics})
    return base


def decorate_tasks(bank: OgeBank, state) -> list[OgeTask]:
    return list(bank.tasks.values())


def shuffle_seeded(items: Iterable[Any], seed: str) -> list[Any]:
    values = list(items)
    random.Random(seed).shuffle(values)
    return values
