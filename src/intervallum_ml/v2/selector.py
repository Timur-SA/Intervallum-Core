"""v2 task selection: mixed topics, mixed types, new/hard bonus marks."""

from __future__ import annotations

from typing import Iterable

from .content import OgeBank, public_task, shuffle_seeded
from .types import OgeTask, TaskType, UserState


def select_train(
    bank: OgeBank,
    state: UserState,
    *,
    count: int = 7,
    section_id: str | None = None,
    topic_id: str | None = None,
    type_filter: str | None = None,
    exclude_types: Iterable[str] = (),
    seed: str | None = None,
) -> list[dict]:
    count = max(1, min(int(count), 50))
    exclude = {str(x) for x in exclude_types}
    candidates: list[OgeTask] = []
    for task in bank.tasks.values():
        if type_filter and task.type.value != type_filter:
            continue
        if task.type.value in exclude:
            continue
        if topic_id and task.topic != topic_id:
            continue
        if section_id:
            section = bank.section_by_topic(task.topic)
            if section is None or section.id != section_id:
                continue
        candidates.append(task)
    if not candidates:
        return []

    seed = seed or "train"
    by_topic: dict[str, list[OgeTask]] = {}
    for task in candidates:
        by_topic.setdefault(task.topic, []).append(task)

    topics = shuffle_seeded(by_topic.keys(), f"{seed}:topics")
    queues: dict[str, list[OgeTask]] = {}
    for topic in topics:
        tasks = by_topic[topic]
        max_xp = bank.topic_max_xp(topic)
        ratio = (state.xp_by_topic.get(topic, 0) / max_xp) if max_xp else 0.0
        target = 1 if ratio < 0.35 else 2 if ratio < 0.75 else 3
        preferred = [t for t in tasks if state.is_new(t.id) or state.is_hard(t)]
        rest = [t for t in tasks if not (state.is_new(t.id) or state.is_hard(t))]
        preferred = sorted(
            shuffle_seeded(preferred, f"{seed}:{topic}:preferred"),
            key=lambda t: abs(t.difficulty - target),
        )
        rest = sorted(
            shuffle_seeded(rest, f"{seed}:{topic}:rest"),
            key=lambda t: abs(t.difficulty - target),
        )
        queues[topic] = preferred + rest

    picked: list[OgeTask] = []
    while len(picked) < count:
        progressed = False
        for topic in topics:
            if len(picked) >= count:
                break
            queue = queues.get(topic, [])
            if queue:
                picked.append(queue.pop(0))
                progressed = True
        if not progressed:
            break

    # Encourage type diversity without sacrificing topic diversity.
    if count >= 3:
        present = {t.type for t in picked}
        for missing_type in [t for t in TaskType if t not in present]:
            replacement = next(
                (t for t in candidates if t.type == missing_type and t not in picked),
                None,
            )
            if replacement is None:
                continue
            if len(picked) < count:
                picked.append(replacement)
                present.add(missing_type)
                continue
            # Replace a duplicate-type task, never the only representative of
            # a type that is already present.
            counts = {t: sum(1 for x in picked if x.type == t) for t in present}
            replace_idx = next(
                (
                    i
                    for i in range(len(picked) - 1, -1, -1)
                    if counts.get(picked[i].type, 0) > 1
                ),
                None,
            )
            if replace_idx is not None:
                counts[picked[replace_idx].type] -= 1
                picked[replace_idx] = replacement
                present.add(missing_type)

    return [
        public_task(
            task,
            is_new=state.is_new(task.id),
            is_hard=state.is_hard(task),
        )
        for task in picked[:count]
    ]
