from voice_agent_eval_lab.adapters import MockCascadeAdapter
from voice_agent_eval_lab.grading import evaluate
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
