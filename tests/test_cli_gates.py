import sys

import pytest

from voice_agent_eval_lab import __version__
from voice_agent_eval_lab.cli import main


def run_cli(monkeypatch, *arguments: str) -> None:
    monkeypatch.setattr(sys, "argv", ["voice-eval", *arguments])
    main()


def test_version_flag_matches_package_version(monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        run_cli(monkeypatch, "--version")

    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == f"voice-eval {__version__}"


def test_run_passes_when_every_gate_is_met(monkeypatch, tmp_path):
    run_cli(
        monkeypatch,
        "run",
        "--scenario",
        "arjun_cancel",
        "--adapter",
        "cascade",
        "--output",
        str(tmp_path),
        "--min-score",
        "1",
        "--min-tool-recall",
        "1",
        "--max-p95-ms",
        "640",
    )


def test_run_exits_one_and_explains_failed_gates(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        run_cli(
            monkeypatch,
            "run",
            "--scenario",
            "arjun_cancel",
            "--adapter",
            "degraded",
            "--output",
            str(tmp_path),
            "--min-score",
            "0.9",
            "--min-tool-recall",
            "0.8",
            "--max-p95-ms",
            "1000",
        )

    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert "degraded: overall score" in stderr
    assert "degraded: tool recall" in stderr
    assert "degraded: P95 latency" in stderr
    assert list(tmp_path.glob("*.json")), "failed runs should still leave diagnostic reports"


def test_compare_applies_gates_to_every_adapter(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        run_cli(
            monkeypatch,
            "compare",
            "--scenario",
            "arjun_cancel",
            "--adapters",
            "cascade",
            "degraded",
            "--output",
            str(tmp_path),
            "--min-score",
            "0.9",
        )

    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert "degraded: overall score" in stderr
    assert "cascade: overall score" not in stderr


def test_suite_runs_directory_and_applies_gates(monkeypatch, tmp_path, capsys):
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "one.yaml").write_text(
        """\
id: one
title: One
turns:
  - user: Please cancel it
    expected_tools: [cancel_booking]
    must_include: [cancelled]
""",
        encoding="utf-8",
    )
    reports = tmp_path / "reports"

    with pytest.raises(SystemExit) as error:
        run_cli(
            monkeypatch,
            "suite",
            "--scenarios",
            str(scenarios),
            "--adapter",
            "degraded",
            "--output",
            str(reports),
            "--min-score",
            "0.9",
        )

    assert error.value.code == 1
    assert "degraded: overall score" in capsys.readouterr().err
    assert list(reports.glob("*_suite.json"))


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--min-score", "1.1", "must be between 0 and 1"),
        ("--min-tool-recall", "-0.1", "must be between 0 and 1"),
        ("--max-p95-ms", "-1", "must be zero or greater"),
    ],
)
def test_gate_ranges_are_validated(monkeypatch, capsys, flag, value, message):
    with pytest.raises(SystemExit) as error:
        run_cli(monkeypatch, "run", flag, value)

    assert error.value.code == 2
    assert message in capsys.readouterr().err


def test_defaults_preserve_the_existing_success_behavior(monkeypatch, tmp_path):
    run_cli(
        monkeypatch,
        "run",
        "--scenario",
        "arjun_cancel",
        "--adapter",
        "degraded",
        "--output",
        str(tmp_path),
    )
