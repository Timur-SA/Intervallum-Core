# API v2 — ОГЭ 9 класс

Префикс: `/v2`.

## health

```bash
curl http://127.0.0.1:8000/v2/health
```

```json
{"status":"ok","track":"9","tasks":77,"topics":20,"sections":3,"content_ok":true}
```

## topics

```bash
curl http://127.0.0.1:8000/v2/topics
```

Возвращает разделы, темы, боссов и предметы.

## select/train

```bash
curl -X POST http://127.0.0.1:8000/v2/select/train \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo",
    "count": 7,
    "seed": "demo"
  }'
```

Можно ограничить выборку:

- `section_id` — `mechanics`, `thermal`, `electromagnetism`;
- `topic_id` — например, `ohm`;
- `type` — `single`, `multi`, `matching`, `cards`, `forces`, `interactive`;
- `exclude_types` — исключить типы;
- `seed` — воспроизводимость.

Ответ:

```json
{
  "count": 7,
  "tasks": [
    {
      "id": "single-uniform-motion",
      "type": "single",
      "topic": "uniform-motion",
      "difficulty": 1,
      "isNew": true,
      "isHard": false,
      "bonusMultiplier": 1.5,
      "prompt": "...",
      "options": []
    }
  ]
}
```

Задания возвращаются без правильных ответов.

## grade

```bash
curl -X POST http://127.0.0.1:8000/v2/grade \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo",
    "task_id": "single-uniform-motion",
    "answer": {"optionId": "c"}
  }'
```

Ответ:

```json
{
  "task_id": "single-uniform-motion",
  "correct_answer": {"optionId": "c"},
  "is_correct": true,
  "outcome": "correct",
  "score": 1.0,
  "xp_by_topic": {"uniform-motion": 15},
  "card_grade": null,
  "bonus_multiplier": 1.5,
  "boss_status": {}
}
```

### Форматы ответов

| Тип | Ответ |
|---|---|
| `single` | `{"optionId": "c"}` |
| `multi` | `{"optionIds": ["a", "b"]}` |
| `matching` | `{"links": {"pair-id": "правильный вариант"}}` |
| `cards` | `{"selfAssessment": 0..3}` |
| `forces` | `{"vectors": [{"type": "gravity"}, ...]}` |
| `interactive` | `{"value": 6, "attempts": 1}` |

Для `forces` и `interactive` можно передать `attempts`: каждая лишняя попытка снижает результат.

Карточки возвращают `card_grade`:
- `0` — неверно или пропуск;
- `1` — слишком легко;
- `2` — нормально;
- `3` — сложно.

## progress

```bash
curl http://127.0.0.1:8000/v2/progress/demo
```

Возвращает опыт по темам, изученные типы, побеждённых боссов, предметы и статус боссов.

## boss defeat

```bash
curl -X POST "http://127.0.0.1:8000/v2/boss/mechanics/defeat?user_id=demo"
```

Босс открывается, когда по всем темам раздела набрано 80% опыта. После победы открывается следующий раздел.

## Опыт

- База: `10 × сложность`.
- Новое задание: ×1.5.
- Сложное задание: ×1.5.
- Новое и сложное: ×2.
- Повторное решение не начисляет опыт сверх прошлого лучшего результата.
