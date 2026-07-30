import json
from pathlib import Path

from voice_agent_eval_lab.scenarios import list_scenarios
from voice_agent_eval_lab.runner import (
    compare_evaluation,
    run_evaluation,
    write_compare_reports,
    write_reports,
)


def test_builtin_scenarios_are_packaged():
    packaged = Path(__file__).parents[1] / "src" / "voice_agent_eval_lab" / "scenario_data"
    assert list_scenarios(packaged) == [
        "arjun_cancel",
        "basic_booking",
        "priya_reschedule",
    ]


def test_run_and_reports(tmp_path):
    report = run_evaluation("basic_booking", "realtime")
    json_path, md_path = write_reports(report, tmp_path)
    assert json.loads(json_path.read_text())["scenario_id"] == "basic_booking"
    assert "Tool recall" in md_path.read_text()
    assert report.evaluation.details["average_latency_ms"] == 310


def test_run_with_audio_writes_one_wav_pair_per_turn(tmp_path):
    audio_root = tmp_path / "audio"
    report = run_evaluation("priya_reschedule", "cascade", audio_root=audio_root)
    assert report.audio_dir is not None
    for turn in report.turns:
        assert turn.user_audio_path is not None
        assert turn.assistant_audio_path is not None
        assert Path(turn.user_audio_path).is_file()
        assert Path(turn.assistant_audio_path).is_file()


def test_compare_runs_every_adapter(tmp_path):
    report = compare_evaluation("basic_booking", ["cascade", "realtime"])
    assert [run.adapter.value for run in report.runs] == ["cascade", "realtime"]
    json_path, md_path = write_compare_reports(report, tmp_path)
    assert "cascade" in md_path.read_text()
    assert "realtime" in md_path.read_text()
    assert json.loads(json_path.read_text())["scenario_id"] == "basic_booking"


def test_compare_with_degraded_adapter_makes_failure_visible():
    report = compare_evaluation("arjun_cancel", ["cascade", "degraded"])
    scores = {run.adapter.value: run.evaluation.overall_score for run in report.runs}
    assert scores["cascade"] == 1.0
    assert scores["degraded"] < 0.60
