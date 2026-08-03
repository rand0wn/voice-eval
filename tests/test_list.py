import json
import sys

import pytest

from voice_agent_eval_lab import adapters
from voice_agent_eval_lab.adapters import VoicePipelineAdapter
from voice_agent_eval_lab.cli import main
from voice_agent_eval_lab.models import Scenario, TurnResult


class PluginAdapter(VoicePipelineAdapter):
    name = "plugin-list"
    supports_s2s = True

    def execute(self, scenario: Scenario, audio_dir=None) -> list[TurnResult]:
        return []


def run_cli(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> None:
    monkeypatch.setattr(sys, "argv", ["voice-eval", *arguments])
    main()


def test_list_defaults_include_bundled_scenarios_and_builtin_adapters(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    run_cli(monkeypatch, "list", "--json")

    data = json.loads(capsys.readouterr().out)
    assert data["scenarios"]
    assert data["scenarios"] == sorted(data["scenarios"])
    names = [entry["name"] for entry in data["adapters"]]
    assert names == sorted(names)
    assert {"cascade", "mock-s2s"} <= set(names)
    by_name = {entry["name"]: entry for entry in data["adapters"]}
    assert by_name["mock-s2s"]["supports_s2s"] is True
    assert by_name["cascade"]["supports_s2s"] is False


def test_list_honors_custom_scenario_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "z.yaml").write_text("id: z\ntitle: Z\nturns:\n  - user: Hi\n", encoding="utf-8")
    (scenarios / "a.yaml").write_text("id: a\ntitle: A\nturns:\n  - user: Hi\n", encoding="utf-8")

    run_cli(monkeypatch, "list", "--scenarios", str(scenarios), "--json")

    data = json.loads(capsys.readouterr().out)
    assert data["scenarios"] == ["a", "z"]


def test_list_honors_voice_eval_scenario_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "only.yaml").write_text("id: only\ntitle: Only\nturns:\n  - user: Hi\n", encoding="utf-8")
    monkeypatch.setenv("VOICE_EVAL_SCENARIO_DIR", str(scenarios))

    run_cli(monkeypatch, "list", "--json")

    data = json.loads(capsys.readouterr().out)
    assert data["scenarios"] == ["only"]


def test_list_includes_registered_plugin_adapter(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(adapters, "_ADAPTERS", dict(adapters._ADAPTERS))
    adapters.register_adapter("plugin-list", PluginAdapter)

    run_cli(monkeypatch, "list", "--json")

    data = json.loads(capsys.readouterr().out)
    by_name = {entry["name"]: entry for entry in data["adapters"]}
    assert by_name["plugin-list"]["supports_s2s"] is True


def test_list_human_output_marks_s2s_adapters(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    run_cli(monkeypatch, "list")

    out = capsys.readouterr().out
    assert "- mock-s2s (s2s)" in out
    assert "- cascade\n" in out
