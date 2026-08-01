from voice_agent_eval_lab.adapters import MockCascadeAdapter, MockDegradedAdapter
from voice_agent_eval_lab.grading import evaluate, grade_turn
from voice_agent_eval_lab.models import Scenario, ToolCall, Turn, TurnResult
from voice_agent_eval_lab.scenarios import load_scenario


def test_perfect_mock_pipeline():
    scenario = load_scenario("basic_booking")
    evaluation = evaluate(scenario, MockCascadeAdapter().execute(scenario))
    assert evaluation.tool_recall == 1
    assert evaluation.transcript_score == 1
    assert evaluation.rubric_score == 1
    assert evaluation.turn_grade_score == 1
    assert evaluation.overall_score == 1
    assert evaluation.details["average_latency_ms"] == 640
    assert all(not grade.failed_rules for grade in evaluation.turn_grades)


def test_multi_turn_persona_scenario_grades_all_turns():
    scenario = load_scenario("priya_reschedule")
    results = MockCascadeAdapter().execute(scenario)
    evaluation = evaluate(scenario, results)
    assert len(evaluation.turn_grades) == len(scenario.turns) == 4
    assert evaluation.tool_recall == 1


def test_missing_tool_call_fails_that_turns_grade():
    scenario = load_scenario("basic_booking")
    results = MockCascadeAdapter().execute(scenario)
    results[0].tool_calls = []
    evaluation = evaluate(scenario, results)
    assert "expected_tools_called" in evaluation.turn_grades[0].failed_rules
    assert evaluation.turn_grades[0].score < 1.0


def test_degraded_adapter_exposes_multiple_failure_types():
    scenario = load_scenario("arjun_cancel")
    evaluation = evaluate(scenario, MockDegradedAdapter().execute(scenario))

    assert 0.50 < evaluation.overall_score < 0.60
    assert evaluation.tool_recall == 0.3333
    assert evaluation.rubric_score == 0.3333
    assert evaluation.details["p95_ms"] == 1450.0
    assert {
        "expected_tools_called",
        "must_include_phrase",
        "max_questions_per_turn",
        "max_sentences_per_turn",
        "latency_budget",
    }.issubset(evaluation.turn_grades[0].failed_rules)


def test_s2s_turn_with_playable_audio_and_no_transcript_skips_text_rules(tmp_path):
    scenario = Scenario(id="s2s", title="S2S", turns=[Turn(user="Hi", expected_tools=["book"])])
    wav = tmp_path / "bot.wav"
    wav.write_bytes(b"\x00" * 200)
    result = TurnResult(
        user="Hi",
        assistant="",
        latency_ms=100,
        tool_calls=[ToolCall(name="book")],
        assistant_audio_path=str(wav),
    )
    grade = grade_turn(scenario, scenario.turns[0], result, 0)
    assert grade.failed_rules == []
    assert grade.score == 1.0


def test_s2s_turn_missing_audio_fails_playable_rule(tmp_path):
    scenario = Scenario(id="s2s2", title="S2S", turns=[Turn(user="Hi")])
    missing_wav = tmp_path / "missing.wav"
    result = TurnResult(
        user="Hi",
        assistant="",
        latency_ms=100,
        assistant_audio_path=str(missing_wav),
    )
    grade = grade_turn(scenario, scenario.turns[0], result, 0)
    assert "assistant_audio_playable" in grade.failed_rules


def test_s2s_time_to_first_audio_byte_budget(tmp_path):
    scenario = Scenario(
        id="s2s3", title="S2S", turns=[Turn(user="Hi")], max_time_to_first_audio_byte_ms=100
    )
    wav = tmp_path / "bot.wav"
    wav.write_bytes(b"\x00" * 200)
    result = TurnResult(
        user="Hi",
        assistant="",
        latency_ms=50,
        assistant_audio_path=str(wav),
        time_to_first_audio_byte_ms=500,
    )
    grade = grade_turn(scenario, scenario.turns[0], result, 0)
    assert "time_to_first_audio_byte_budget" in grade.failed_rules
