"""Questionnaire engine — loads the general questions.json and walks the admin
through it tier by tier. The file is data, not code: swap questions.json and the
interview changes with no backend edits."""
import json
from functools import lru_cache
from typing import Optional

from .config import settings


@lru_cache(maxsize=1)
def load_questionnaire() -> dict:
    with open(settings.questionnaire_path, "r", encoding="utf-8") as f:
        return json.load(f)


def flat_questions() -> list[dict]:
    """All questions across all tiers, in order, each annotated with its tier."""
    q = load_questionnaire()
    out: list[dict] = []
    for tier in q.get("tiers", []):
        for question in tier.get("questions", []):
            item = dict(question)
            item["tier_id"] = tier.get("tier_id")
            item["tier_title"] = tier.get("title")
            out.append(item)
    return out


def question_ids() -> list[str]:
    return [q["question_id"] for q in flat_questions()]


def next_question(answers: dict) -> Optional[dict]:
    """First question (in tier order) that has no answer yet, or None if complete."""
    for q in flat_questions():
        if q["question_id"] not in answers or answers[q["question_id"]] in (None, "", []):
            return q
    return None


def progress(answers: dict) -> dict:
    ids = question_ids()
    answered = [qid for qid in ids if answers.get(qid) not in (None, "", [])]
    return {"answered": len(answered), "total": len(ids), "complete": len(answered) == len(ids)}
