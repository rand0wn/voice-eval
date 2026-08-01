from __future__ import annotations

import importlib

import pytest

from voice_agent_eval_lab.models import Scenario, ToolCall, Turn
from voice_agent_eval_lab.pipecat_adapter import (
    PipecatAdapter,
    PipecatTurnObservation,
    _load_configured_client,
)


class FakePipecatClient:
    def run_turn(self, user: str) -> PipecatTurnObservation:
        return PipecatTurnObservation(
            user_transcript=user,
            assistant="Your booking is cancelled.",
            tool_calls=[ToolCall(name="cancel_booking", arguments={"id": "B1"})],
            latency_ms=420,
            component_timings_ms={"stt": 80, "llm_ttft": 210, "tts_ttfb": 90},
            session_metadata={"pipeline": "offline-test", "session_id": "S1"},
        )


def scenario() -> Scenario:
    return Scenario(id="pc", title="Pipecat", turns=[Turn(user="Cancel B1")])


def test_pipecat_adapter_accepts_injected_client_offline():
    result = PipecatAdapter(FakePipecatClient()).execute(scenario())[0]
    assert result.user == "Cancel B1"
    assert result.assistant == "Your booking is cancelled."
    assert result.tool_calls[0].name == "cancel_booking"
    assert result.tool_calls[0].arguments == {"id": "B1"}
    assert result.latency_ms == 420
    assert result.component_timings_ms["llm_ttft"] == 210
    assert result.component_timings_ms["stt"] == 80
    assert result.component_timings_ms["tts_ttfb"] == 90
    assert result.session_metadata["pipeline"] == "offline-test"


def test_pipecat_adapter_falls_back_to_measured_latency_when_absent():
    class NoLatencyClient:
        def run_turn(self, user: str) -> PipecatTurnObservation:
            return PipecatTurnObservation(assistant="ok")

    result = PipecatAdapter(NoLatencyClient()).execute(scenario())[0]
    assert result.latency_ms >= 0


def test_audio_request_is_explicitly_unsupported(tmp_path):
    with pytest.raises(ValueError, match="does not export audio"):
        PipecatAdapter(FakePipecatClient()).execute(scenario(), tmp_path)


def test_missing_client_has_actionable_error(monkeypatch):
    monkeypatch.delenv("VOICE_EVAL_PIPECAT_CLIENT", raising=False)
    with pytest.raises(RuntimeError, match=r"VOICE_EVAL_PIPECAT_CLIENT"):
        _load_configured_client()


def test_missing_dependency_has_actionable_error(monkeypatch):
    monkeypatch.delenv("VOICE_EVAL_PIPECAT_CLIENT", raising=False)
    original_import_module = importlib.import_module

    def reject_pipecat(name, *args, **kwargs):
        if name.startswith("pipecat"):
            raise ImportError("not installed")
        return original_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", reject_pipecat)
    with pytest.raises(RuntimeError, match=r"\[pipecat\].*VOICE_EVAL_PIPECAT_CLIENT"):
        _load_configured_client()


def test_invalid_client_factory_target_is_rejected(monkeypatch):
    monkeypatch.setenv("VOICE_EVAL_PIPECAT_CLIENT", "not-a-valid-target")
    with pytest.raises(RuntimeError, match="python_module:factory"):
        _load_configured_client()
