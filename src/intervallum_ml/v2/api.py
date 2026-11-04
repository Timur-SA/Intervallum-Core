"""FastAPI v2 router for the OGE data core."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .store import V2Store


class SelectTrainRequest(BaseModel):
    user_id: str
    count: int = 7
    section_id: str | None = None
    topic_id: str | None = None
    type: str | None = None
    exclude_types: list[str] = Field(default_factory=list)
    seed: str | None = None


class SelectTrainResponse(BaseModel):
    tasks: list[dict[str, Any]]
    count: int


class GradeRequest(BaseModel):
    user_id: str
    task_id: str
    answer: Any


class GradeResponse(BaseModel):
    task_id: str
    correct_answer: Any
    is_correct: bool
    outcome: str
    score: float
    xp_by_topic: dict[str, int]
    card_grade: int | None
    bonus_multiplier: float
    boss_status: dict[str, dict]


class ProgressResponse(BaseModel):
    user_id: str
    xp_by_topic: dict[str, int]
    total_xp: int
    explored_types: list[str]
    defeated_bosses: list[str]
    unlocked_sections: list[str]
    items: list[str]
    bosses: dict[str, dict]


def create_v2_router(store: V2Store | None = None) -> APIRouter:
    store = store or V2Store.from_default()
    router = APIRouter(prefix="/v2", tags=["v2 OGE data core"])

    @router.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "track": "9",
            "tasks": len(store.bank.tasks),
            "topics": len(store.bank.topics),
            "sections": len(store.bank.sections),
            "content_ok": store.bank.ok,
        }

    @router.get("/topics")
    def topics() -> dict:
        return {
            "sections": [
                {
                    "id": s.id,
                    "title": s.title,
                    "boss": s.boss,
                    "item": s.item,
                    "item_id": s.item_id,
                    "color": s.color,
                    "topics": list(s.topics),
                }
                for s in store.bank.sections.values()
            ],
            "topics": [
                {"id": t.id, "title": t.title, "section": t.section}
                for t in store.bank.topics.values()
            ],
        }

    @router.post("/select/train", response_model=SelectTrainResponse)
    def select_train(req: SelectTrainRequest) -> SelectTrainResponse:
        tasks = store.select(
            req.user_id,
            count=req.count,
            section_id=req.section_id,
            topic_id=req.topic_id,
            type_filter=req.type,
            exclude_types=tuple(req.exclude_types),
            seed=req.seed,
        )
        return SelectTrainResponse(tasks=tasks, count=len(tasks))

    @router.post("/grade", response_model=GradeResponse)
    def grade(req: GradeRequest) -> GradeResponse:
        try:
            result = store.grade(req.user_id, req.task_id, req.answer)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return GradeResponse(
            task_id=result.task_id,
            correct_answer=result.correct_answer,
            is_correct=result.is_correct,
            outcome=result.outcome,
            score=result.score,
            xp_by_topic=result.xp_by_topic,
            card_grade=result.card_grade,
            bonus_multiplier=result.bonus_multiplier,
            boss_status=result.boss_status,
        )

    @router.get("/progress/{user_id}", response_model=ProgressResponse)
    def progress(user_id: str) -> ProgressResponse:
        return ProgressResponse(**store.progress(user_id))

    @router.post("/boss/{section_id}/defeat")
    def defeat_boss(section_id: str, user_id: str = Query(...)) -> dict:
        return store.defeat(user_id, section_id)

    return router
