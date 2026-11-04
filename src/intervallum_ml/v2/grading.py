"""v2 grading, XP, anti-farming and boss progression."""

from __future__ import annotations

from typing import Any

from .content import BASE_XP, OgeBank
from .types import GradeResultV2, OgeTask, TaskStat, TaskType, UserState


def _score_outcome(score: float) -> str:
    if score >= 1.0:
        return "correct"
    if score > 0.0:
        return "partial"
    return "wrong"


def _card_grade(answer: dict[str, Any]) -> int:
    value = answer.get("selfAssessment", answer.get("self_assessment", answer.get("grade", 0)))
    try:
        grade = int(value)
    except (TypeError, ValueError):
        grade = 0
    return max(0, min(3, grade))


def grade_task(
    bank: OgeBank,
    state: UserState,
    task: OgeTask,
    answer: dict[str, Any] | str | int,
) -> GradeResultV2:
    if isinstance(answer, (str, int)):
        answer = {"value": answer}
    answer = dict(answer or {})

    is_new = state.is_new(task.id)
    is_hard = state.is_hard(task)
    bonus = 1.0 + (0.5 if is_new else 0.0) + (0.5 if is_hard else 0.0)
    score = 0.0
    correct_answer: Any = None
    card_grade: int | None = None
    correct_flag = False
    p = task.payload

    if task.type == TaskType.SINGLE:
        selected = answer.get("optionId", answer.get("option_id", answer.get("value")))
        correct = p.get("correctOptionId")
        score = 1.0 if selected == correct else 0.0
        correct_flag = score == 1.0
        correct_answer = {"optionId": correct}

    elif task.type == TaskType.MULTI:
        selected = answer.get("optionIds", answer.get("option_ids", []))
        if isinstance(selected, str):
            selected = [selected]
        selected_set = set(selected)
        correct_set = set(p.get("correctOptionIds", []))
        if not correct_set:
            score = 0.0
        else:
            missed = len(correct_set - selected_set)
            extra = len(selected_set - correct_set)
            score = max(0.0, 1.0 - (missed + extra) / len(correct_set))
        correct_flag = selected_set == correct_set
        correct_answer = {"optionIds": sorted(correct_set)}

    elif task.type == TaskType.MATCHING:
        links = answer.get("links", {})
        pairs = p.get("pairs", [])
        if not pairs:
            score = 0.0
        else:
            correct_count = sum(1 for pair in pairs if links.get(pair.get("id")) == pair.get("right"))
            score = correct_count / len(pairs)
        correct_flag = score >= 1.0
        correct_answer = {"links": {pair.get("id"): pair.get("right") for pair in pairs}}

    elif task.type == TaskType.CARDS:
        card_grade = _card_grade(answer)
        score = card_grade / 3.0
        correct_flag = card_grade >= 2
        correct_answer = {"answer": p.get("answer", ""), "grade": card_grade}

    elif task.type == TaskType.FORCES:
        vectors = answer.get("vectors", answer.get("forces", []))
        refs = p.get("forceTask", {}).get("refs", [])
        ref_types = {r.get("type") for r in refs}
        drawn_types = {v.get("type") for v in vectors if isinstance(v, dict)}
        if not ref_types:
            score = 0.0
        else:
            bad = len(ref_types.symmetric_difference(drawn_types))
            score = max(0.0, 1.0 - bad / len(ref_types))
        attempts = int(answer.get("attempts", 1))
        if score > 0 and attempts > 1:
            score = max(0.0, score - 0.25 * (attempts - 1))
        correct_flag = score >= 1.0
        correct_answer = {"forces": sorted(ref_types)}

    elif task.type == TaskType.INTERACTIVE:
        physics = p.get("physicsTask", {})
        find = physics.get("find", {})
        correct_value = find.get("value")
        raw_value = answer.get("value", answer.get("finalValue", answer.get("final_value")))
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = None
        if value is not None and correct_value is not None:
            tolerance = max(1e-6, abs(float(correct_value)) * 1e-3)
            score = 1.0 if abs(value - float(correct_value)) <= tolerance else 0.0
        attempts = int(answer.get("attempts", 1))
        if score > 0 and attempts > 1:
            score = max(0.0, score - 0.25 * (attempts - 1))
        correct_flag = score >= 1.0
        correct_answer = {"value": correct_value, "formula": find.get("targetFormula")}

    else:
        score = 0.0
        correct_answer = None

    xp_awarded = int(round(BASE_XP * task.difficulty * score * bonus))
    previous_best = state.best_xp_by_task.get(task.id, 0)
    gained = max(0, xp_awarded - previous_best)
    state.best_xp_by_task[task.id] = max(previous_best, xp_awarded)
    if gained:
        state.xp_by_topic[task.topic] = state.xp_by_topic.get(task.topic, 0) + gained

    previous_stat = state.task_stats.get(task.id)
    state.task_stats[task.id] = TaskStat(
        attempts=(previous_stat.attempts if previous_stat else 0) + 1,
        best_score=max(previous_stat.best_score if previous_stat else 0.0, score),
    )
    state.explored_types.add(task.type.value)
    state.best_score_by_type[task.type.value] = max(
        state.best_score_by_type.get(task.type.value, 0.0), score
    )

    bosses = {
        section_id: bank.boss_status(section_id, state.xp_by_topic)
        for section_id in bank.sections
    }
    return GradeResultV2(
        task_id=task.id,
        correct_answer=correct_answer,
        is_correct=correct_flag,
        outcome=_score_outcome(score),
        score=score,
        xp_by_topic={task.topic: gained} if gained else {},
        card_grade=card_grade,
        bonus_multiplier=bonus,
        boss_status=bosses,
    )


def defeat_boss(bank: OgeBank, state: UserState, section_id: str) -> dict:
    status = bank.boss_status(section_id, state.xp_by_topic)
    if not status or not status.get("ready") or section_id in state.defeated_bosses:
        return {"defeated": False, **status}
    section = bank.sections[section_id]
    state.defeated_bosses.add(section_id)
    if section.item_id:
        state.items.add(section.item_id)
    order = list(bank.sections)
    idx = order.index(section_id)
    if idx + 1 < len(order):
        state.unlocked_sections.add(order[idx + 1])
    return {"defeated": True, **status, "item": section.item, "next_section": order[idx + 1] if idx + 1 < len(order) else None}
