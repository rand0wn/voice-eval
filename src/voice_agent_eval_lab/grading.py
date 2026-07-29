"""Per-turn and aggregate grading for a simulated conversation.

Mirrors a pattern used against real production traffic: don't just check
"did the pipeline respond" — grade every turn against a fixed rubric (tool
recall, response shape, required content, latency budget) and report which
specific rule failed, not just a pass/fail blob.
"""

from __future__ import annotations

import re
from statistics import mean

from .models import Evaluation, Scenario, Turn, TurnGrade, TurnResult

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


def _sentence_count(text: str) -> int:
    parts = [p for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return max(1, len(parts))


def grade_turn(scenario: Scenario, turn: Turn, result: TurnResult, index: int) -> TurnGrade:
    """Grade one turn against every rule that applies to it; return the failures."""
    failed: list[str] = []

    actual_tools = {call.name for call in result.tool_calls}
    if turn.expected_tools and not set(turn.expected_tools).issubset(actual_tools):
        failed.append("expected_tools_called")

    for phrase in turn.must_include:
        if phrase.lower() not in result.assistant.lower():
            failed.append("must_include_phrase")
            break

    if result.assistant.count("?") > scenario.max_questions_per_turn:
        failed.append("max_questions_per_turn")

    if _sentence_count(result.assistant) > scenario.max_sentences_per_turn:
        failed.append("max_sentences_per_turn")

    if result.latency_ms > scenario.max_latency_ms:
        failed.append("latency_budget")

    if not result.user.strip() or not result.assistant.strip():
        failed.append("non_empty_transcript")

    rules_checked = 5 + (1 if turn.expected_tools else 0) + (1 if turn.must_include else 0)
    score = 1.0 - (len(failed) / rules_checked) if rules_checked else 1.0
    return TurnGrade(index=index, score=round(max(0.0, score), 4), failed_rules=failed)


def latency_score(results: list[TurnResult], ceiling_ms: float) -> tuple[float, float]:
    average = mean(item.latency_ms for item in results) if results else 0.0
    score = 1.0 if not results else max(0.0, min(1.0, ceiling_ms / max(average, ceiling_ms)))
    return score, average


def latency_percentiles(results: list[TurnResult]) -> dict[str, float]:
    if not results:
        return {"p50_ms": 0.0, "p95_ms": 0.0}
    values = sorted(item.latency_ms for item in results)

    def _pct(p: float) -> float:
        k = (len(values) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(values) - 1)
        return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 2)

    return {"p50_ms": _pct(0.5), "p95_ms": _pct(0.95)}


def tool_recall(scenario: Scenario, results: list[TurnResult]) -> tuple[float, int, int]:
    expected = [tool for turn in scenario.turns for tool in turn.expected_tools]
    actual = [call.name for result in results for call in result.tool_calls]
    matched = sum(1 for tool in expected if tool in actual)
    return (matched / len(expected) if expected else 1.0), matched, len(expected)


def transcript_score(scenario: Scenario, results: list[TurnResult]) -> float:
    if len(results) != len(scenario.turns):
        return 0.0
    complete = sum(bool(item.user.strip() and item.assistant.strip()) for item in results)
    return complete / len(scenario.turns) if scenario.turns else 1.0


def rubric_score(scenario: Scenario, results: list[TurnResult]) -> tuple[float, int, int]:
    required = [(index, phrase) for index, turn in enumerate(scenario.turns) for phrase in turn.must_include]
    matched = sum(phrase.lower() in results[index].assistant.lower() for index, phrase in required if index < len(results))
    return (matched / len(required) if required else 1.0), matched, len(required)


def evaluate(scenario: Scenario, results: list[TurnResult]) -> Evaluation:
    latency, average = latency_score(results, scenario.max_latency_ms)
    tools, tools_hit, tools_total = tool_recall(scenario, results)
    transcript = transcript_score(scenario, results)
    rubric, rubric_hit, rubric_total = rubric_score(scenario, results)

    turn_grades = [
        grade_turn(scenario, turn, result, index)
        for index, (turn, result) in enumerate(zip(scenario.turns, results))
    ]
    turn_grade_score = mean(g.score for g in turn_grades) if turn_grades else 1.0

    overall = mean([latency, tools, transcript, rubric, turn_grade_score])
    return Evaluation(
        latency_score=round(latency, 4),
        tool_recall=round(tools, 4),
        transcript_score=round(transcript, 4),
        rubric_score=round(rubric, 4),
        turn_grade_score=round(turn_grade_score, 4),
        overall_score=round(overall, 4),
        turn_grades=turn_grades,
        details={
            "average_latency_ms": round(average, 2),
            **latency_percentiles(results),
            "tools_matched": tools_hit,
            "tools_expected": tools_total,
            "rubric_matched": rubric_hit,
            "rubric_expected": rubric_total,
        },
    )
