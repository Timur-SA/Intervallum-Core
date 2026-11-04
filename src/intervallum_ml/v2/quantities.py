"""Extraction of numeric values and units from OGE task text.

The Core spec asks the parser to mark dimensionless and dimensional values.
This module is intentionally deterministic: it is used by the content
analytics and by an external FIPI importer, not by the online grader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .content import OgeBank
from .types import TaskType

_UNITS = [
    "м/с²", "м/с2", "м/с", "кг/м³", "кг/м3", "Дж/(кг·К)", "Дж/(кг·°C)",
    "Н·м", "км/ч", "мл", "см", "мм", "км", "кг", "г", "мг", "Н", "Дж", "м",
    "Вт", "Па", "кПа", "МПа", "Кл", "мкКл", "нКл", "А", "мА", "Ом",
    "кОм", "В", "мВ", "К", "°C", "л", "м³", "м2", "м²", "с", "мин", "ч",
]
_UNIT_PATTERN = "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))
_QUANTITY_RE = re.compile(
    rf"(?P<value>-?\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNIT_PATTERN})(?![A-Za-zА-Яа-я])"
)


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str
    raw: str
    dimensionless: bool = False


def extract_quantities(text: str) -> list[Quantity]:
    found: list[Quantity] = []
    for match in _QUANTITY_RE.finditer(text or ""):
        raw = match.group(0)
        unit = match.group("unit")
        try:
            value = float(match.group("value").replace(",", "."))
        except ValueError:
            continue
        found.append(Quantity(value=value, unit=unit, raw=raw, dimensionless=False))
    return found


def extract_dimensionless(text: str) -> list[float]:
    """Numbers without a unit, useful for ratios and coefficients."""

    stripped = _QUANTITY_RE.sub(" ", text or "")
    values = []
    for match in re.finditer(r"(?<![\w.,])-?\d+(?:[.,]\d+)?(?![\w,])", stripped):
        try:
            values.append(float(match.group(0).replace(",", ".")))
        except ValueError:
            continue
    return values


def coverage_report(bank: OgeBank) -> dict:
    by_type: dict[str, int] = {}
    by_section: dict[str, int] = {}
    by_topic: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    with_quantities = 0
    without_explanation = 0
    for task in bank.tasks.values():
        by_type[task.type.value] = by_type.get(task.type.value, 0) + 1
        section = bank.section_by_topic(task.topic)
        key = section.id if section else "unknown"
        by_section[key] = by_section.get(key, 0) + 1
        by_topic[task.topic] = by_topic.get(task.topic, 0) + 1
        by_difficulty[str(task.difficulty)] = by_difficulty.get(str(task.difficulty), 0) + 1
        text = " ".join(
            str(task.payload.get(k, "")) for k in ("prompt", "question", "description")
        )
        if extract_quantities(text):
            with_quantities += 1
        if not task.payload.get("explanation") and task.type not in {TaskType.CARDS, TaskType.INTERACTIVE}:
            without_explanation += 1

    missing_topics = [
        topic_id
        for topic_id, topic in bank.topics.items()
        if by_topic.get(topic_id, 0) == 0
    ]
    return {
        "tasks": len(bank.tasks),
        "topics": len(bank.topics),
        "sections": len(bank.sections),
        "by_type": by_type,
        "by_section": by_section,
        "by_topic": by_topic,
        "by_difficulty": by_difficulty,
        "tasks_with_quantities": with_quantities,
        "tasks_without_explanation": without_explanation,
        "missing_topics": missing_topics,
    }


def llm_review_prompt(task) -> str:
    payload = task.payload
    body = payload.get("prompt") or payload.get("question") or payload.get("description") or ""
    answer = (
        payload.get("correctOptionId")
        or payload.get("correctOptionIds")
        or payload.get("answer")
        or payload.get("physicsTask", {}).get("find", {}).get("value")
    )
    return (
        "Проверь задачу ОГЭ по физике. Ответь строго JSON "
        '{"ok": true/false, "reason": "..."}.\n'
        f"Тип: {task.type.value}\nТема: {task.topic}\nСложность: {task.difficulty}\n"
        f"Условие: {body}\nПравильный ответ: {answer}\n"
        "Проверь: однозначность условия, корректность ответа, отсутствие опечаток, "
        "соответствие теме и уровню ОГЭ."
    )
