from __future__ import annotations

from pathlib import Path

from intervallum_ml.v2.content import load_oge_bank
from intervallum_ml.v2.quantities import (
    coverage_report,
    extract_dimensionless,
    extract_quantities,
    llm_review_prompt,
)

ROOT = Path(__file__).parents[1]
BANK = ROOT / "content" / "oge_2026"


def test_extract_quantities_with_units():
    items = extract_quantities("Тело прошло 20 м за 4 с, сила 5 Н, ускорение 2 м/с².")
    assert {item.unit for item in items} == {"м", "с", "Н", "м/с²"}
    assert [item.value for item in items] == [20.0, 4.0, 5.0, 2.0]


def test_extract_dimensionless_numbers():
    values = extract_dimensionless("Отношение равно 2,5. Масса 200 г, скорость 5 м/с.")
    assert 2.5 in values
    assert 200.0 not in values
    assert 5.0 not in values


def test_coverage_report_covers_all_topics():
    bank = load_oge_bank(BANK)
    report = coverage_report(bank)
    assert report["tasks"] == 77
    assert report["missing_topics"] == []
    assert report["by_type"]["single"] == 20
    assert report["by_type"]["cards"] == 20
    assert report["tasks_with_quantities"] > 0


def test_llm_prompt_contains_task_and_answer():
    bank = load_oge_bank(BANK)
    task = next(t for t in bank.tasks.values() if t.type.value == "single")
    prompt = llm_review_prompt(task)
    assert task.id in prompt or "Проверь задачу" in prompt
    assert "Правильный ответ" in prompt
