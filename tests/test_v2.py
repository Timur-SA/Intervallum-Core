from __future__ import annotations

from collections import Counter
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from intervallum_ml.v2 import V2Store, create_v2_router, load_oge_bank
from intervallum_ml.v2.selector import select_train
from intervallum_ml.v2.types import TaskType, UserState

ROOT = Path(__file__).parents[1]
BANK_DIR = ROOT / "content" / "oge_2026"


def bank():
    return load_oge_bank(BANK_DIR)


def force_vectors(payload):
    vectors = []
    for ref in payload["forceTask"]["refs"]:
        region = ref["region"]
        if region.get("kind") == "point":
            x, y = region["x"], region["y"]
        else:
            x = (region["a"]["x"] + region["b"]["x"]) / 2
            y = (region["a"]["y"] + region["b"]["y"]) / 2
        vectors.append({
            "type": ref["type"], "x": x, "y": y,
            "dx": ref["dx"], "dy": ref["dy"],
        })
    return vectors


def test_bank_loads_and_is_valid():
    b = bank()
    assert b.ok
    assert len(b.tasks) == 77
    assert len(b.topics) == 20
    assert len(b.sections) == 3
    counts = Counter(t.type for t in b.tasks.values())
    assert counts[TaskType.SINGLE] == 20
    assert counts[TaskType.MULTI] == 18
    assert counts[TaskType.MATCHING] == 7
    assert counts[TaskType.CARDS] == 20
    assert counts[TaskType.FORCES] == 6
    assert counts[TaskType.INTERACTIVE] == 6


def test_public_tasks_hide_answers():
    b = bank()
    state = UserState("u")
    for task in b.tasks.values():
        public = select_train(b, state, count=77, type_filter=task.type.value, seed="x")
        item = next(x for x in public if x["id"] == task.id)
        assert "correctOptionId" not in item
        assert "correctOptionIds" not in item
        assert "explanation" not in item
        if task.type == TaskType.CARDS:
            assert "answer" not in item
        if task.type == TaskType.FORCES:
            assert "refs" not in item["forceTask"]
        if task.type == TaskType.INTERACTIVE:
            assert "value" not in item["physicsTask"]["find"]


def test_every_task_can_be_graded_correctly():
    b = bank()
    store = V2Store(b)
    for task in b.tasks.values():
        p = task.payload
        if task.type == TaskType.SINGLE:
            answer = {"optionId": p["correctOptionId"]}
        elif task.type == TaskType.MULTI:
            answer = {"optionIds": p["correctOptionIds"]}
        elif task.type == TaskType.MATCHING:
            answer = {"links": {pair["id"]: pair["right"] for pair in p["pairs"]}}
        elif task.type == TaskType.CARDS:
            answer = {"selfAssessment": 3}
        elif task.type == TaskType.FORCES:
            answer = {"vectors": force_vectors(p)}
        elif task.type == TaskType.INTERACTIVE:
            answer = {"value": p["physicsTask"]["find"]["value"]}
        else:
            raise AssertionError(task.type)
        result = store.grade("test", task.id, answer)
        assert result.score == 1.0, (task.id, task.type, result.score)


def test_multi_penalties():
    b = bank()
    store = V2Store(b)
    task = next(t for t in b.tasks.values() if t.type == TaskType.MULTI)
    correct = task.payload["correctOptionIds"]
    assert store.grade("u", task.id, {"optionIds": correct}).score == 1.0
    assert store.grade("u", task.id, {"optionIds": correct[:1]}).score == 0.5
    assert store.grade("u", task.id, {"optionIds": correct + ["x"]}).score < 1.0


def test_card_grade_is_returned():
    b = bank()
    store = V2Store(b)
    task = next(t for t in b.tasks.values() if t.type == TaskType.CARDS)
    result = store.grade("u", task.id, {"selfAssessment": 2})
    assert result.card_grade == 2
    assert 0 < result.score < 1


def test_xp_bonus_and_anti_farm():
    b = bank()
    store = V2Store(b)
    task = next(t for t in b.tasks.values() if t.type == TaskType.SINGLE)
    first = store.grade("u", task.id, {"optionId": task.payload["correctOptionId"]})
    second = store.grade("u", task.id, {"optionId": task.payload["correctOptionId"]})
    assert first.bonus_multiplier == 1.5
    assert first.xp_by_topic
    assert second.xp_by_topic == {}


def test_select_is_mixed_and_marks_tasks():
    b = bank()
    state = UserState("u")
    tasks = select_train(b, state, count=7, seed="demo")
    assert len(tasks) == 7
    assert len({t["id"] for t in tasks}) == 7
    assert len({t["type"] for t in tasks}) >= 3
    assert len({t["topic"] for t in tasks}) >= 3
    assert all("isNew" in t and "isHard" in t for t in tasks)


def test_boss_threshold_and_defeat():
    b = bank()
    state = UserState("u")
    section = b.sections["mechanics"]
    for topic in section.topics:
        state.xp_by_topic[topic] = b.topic_unlock_xp(topic)
    from intervallum_ml.v2.grading import defeat_boss

    status = b.boss_status("mechanics", state.xp_by_topic)
    assert status["ready"] is True
    result = defeat_boss(b, state, "mechanics")
    assert result["defeated"] is True
    assert "mechanics" in state.defeated_bosses
    assert "thermal" in state.unlocked_sections


def test_v2_api_flow():
    b = bank()
    store = V2Store(b)
    app = FastAPI()
    app.include_router(create_v2_router(store))
    client = TestClient(app)

    health = client.get("/v2/health").json()
    assert health["tasks"] == 77

    selected = client.post("/v2/select/train", json={"user_id": "u", "count": 5, "seed": "api"})
    assert selected.status_code == 200, selected.text
    tasks = selected.json()["tasks"]
    assert len(tasks) == 5

    task = tasks[0]
    if task["type"] == "single":
        answer = {"optionId": next(t for t in b.tasks.values() if t.id == task["id"]).payload["correctOptionId"]}
    elif task["type"] == "multi":
        answer = {"optionIds": next(t for t in b.tasks.values() if t.id == task["id"]).payload["correctOptionIds"]}
    elif task["type"] == "matching":
        pairs = next(t for t in b.tasks.values() if t.id == task["id"]).payload["pairs"]
        answer = {"links": {p["id"]: p["right"] for p in pairs}}
    elif task["type"] == "cards":
        answer = {"selfAssessment": 3}
    elif task["type"] == "forces":
        answer = {
            "vectors": force_vectors(
                next(t for t in b.tasks.values() if t.id == task["id"]).payload
            )
        }
    else:
        answer = {"value": next(t for t in b.tasks.values() if t.id == task["id"]).payload["physicsTask"]["find"]["value"]}

    graded = client.post("/v2/grade", json={"user_id": "u", "task_id": task["id"], "answer": answer})
    assert graded.status_code == 200, graded.text
    assert graded.json()["score"] == 1.0

    progress = client.get("/v2/progress/u")
    assert progress.status_code == 200
    assert progress.json()["total_xp"] > 0
