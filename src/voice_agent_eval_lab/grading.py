"""Per-turn and aggregate grading for a simulated conversation.

Mirrors a pattern used against real production traffic: don't just check
"did the pipeline respond" — grade every turn against a fixed rubric (tool
recall, response shape, required content, latency budget) and report which
specific rule failed, not just a pass/fail blob.
"""

from __future__ import annotations

import re
from pathlib import Path
from statistics import mean

from .models import Evaluation, Scenario, Turn, TurnGrade, TurnResult

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


def _sentence_count(text: str) -> int:
    parts = [p for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return max(1, len(parts))


def _s2s_audio_playable(result: TurnResult) -> bool:
    """A native S2S turn is only gradeable as "responded" if its audio exists.

    A WAV header alone (44 bytes) is not a response; require some sample
    data past the header before treating the turn as having produced audio.
    """
    if not result.assistant_audio_path:
        return False
    path = Path(result.assistant_audio_path)
    return path.is_file() and path.stat().st_size > 44


def grade_turn(scenario: Scenario, turn: Turn, result: TurnResult, index: int) -> TurnGrade:
    """Grade one turn against every rule that applies to it; return the failures.

    Text-shape rules (`must_include_phrase`, `max_questions_per_turn`,
    `max_sentences_per_turn`, `non_empty_transcript`) only make sense when
    there is transcript text to grade. Native S2S adapters may report no
    transcript at all (see `s2s.py`); when a turn carries assistant audio but
    no transcript, those text rules are skipped in favor of the audio-derived
    rules (`assistant_audio_playable`, `time_to_first_audio_byte_budget`)
    below, which apply whenever the turn produced (or should have produced)
    audio, in text mode or S2S mode alike.
    """
    failed: list[str] = []
    audio_only = bool(result.assistant_audio_path) and not result.assistant.strip()

    actual_tools = {call.name for call in result.tool_calls}
    if turn.expected_tools and not set(turn.expected_tools).issubset(actual_tools):
        failed.append("expected_tools_called")

    if not audio_only:
        for phrase in turn.must_include:
            if phrase.lower() not in result.assistant.lower():
                failed.append("must_include_phrase")
                break

        if result.assistant.count("?") > scenario.max_questions_per_turn:
            failed.append("max_questions_per_turn")

        if _sentence_count(result.assistant) > scenario.max_sentences_per_turn:
            failed.append("max_sentences_per_turn")

        if not result.user.strip() or not result.assistant.strip():
            failed.append("non_empty_transcript")

    if result.latency_ms > scenario.max_latency_ms:
        failed.append("latency_budget")

    audio_checks = 0
    if result.assistant_audio_path:
        audio_checks += 1
        if not _s2s_audio_playable(result):
            failed.append("assistant_audio_playable")
        if (
            scenario.max_time_to_first_audio_byte_ms is not None
            and result.time_to_first_audio_byte_ms is not None
        ):
            audio_checks += 1
            if result.time_to_first_audio_byte_ms > scenario.max_time_to_first_audio_byte_ms:
                failed.append("time_to_first_audio_byte_budget")

    if audio_only:
        rules_checked = 1 + (1 if turn.expected_tools else 0) + audio_checks
    else:
        rules_checked = (
            5 + (1 if turn.expected_tools else 0) + (1 if turn.must_include else 0) + audio_checks
        )
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
