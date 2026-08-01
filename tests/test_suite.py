import json

import pytest

from voice_agent_eval_lab.runner import run_suite, write_suite_reports


SCENARIO = """\
id: {id}
title: Example
turns:
  - user: Please help me
"""


def test_suite_is_deterministic_and_writes_aggregate_reports(tmp_path):
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "z.yaml").write_text(SCENARIO.format(id="second"))
    (scenarios / "a.yml").write_text(SCENARIO.format(id="first"))

    report = run_suite("cascade", scenarios)

    assert [run.scenario_id for run in report.runs] == ["first", "second"]
    assert report.scenario_count == 2
    json_path, md_path = write_suite_reports(report, tmp_path / "reports")
    assert json.loads(json_path.read_text())["scenario_count"] == 2
    assert "| first |" in md_path.read_text()


def test_suite_uses_built_in_scenarios():
    report = run_suite("cascade")
    assert report.scenario_count > 0
    assert [run.scenario_id for run in report.runs] == sorted(
        run.scenario_id for run in report.runs
    )


@pytest.mark.parametrize("kind", ["missing", "empty"])
def test_suite_rejects_missing_or_empty_directory(tmp_path, kind):
    directory = tmp_path / kind
    if kind == "empty":
        directory.mkdir()
    with pytest.raises(ValueError, match="Scenario directory"):
        run_suite("cascade", directory)


def test_suite_rejects_invalid_yaml_and_duplicate_ids(tmp_path):
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "bad.yaml").write_text("not: a scenario")
    with pytest.raises(ValueError, match="Invalid scenario file"):
        run_suite("cascade", invalid)

    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    (duplicate / "a.yaml").write_text(SCENARIO.format(id="same"))
    (duplicate / "b.yaml").write_text(SCENARIO.format(id="same"))
    with pytest.raises(ValueError, match="Duplicate scenario id 'same'"):
        run_suite("cascade", duplicate)
