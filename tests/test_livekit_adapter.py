from __future__ import annotations

import builtins

import pytest

from voice_agent_eval_lab.livekit_adapter import (
    LiveKitAdapter,
    LiveKitEventCollector,
    LiveKitTurnObservation,
    _load_configured_client,
    observation_from_events,
)
from voice_agent_eval_lab.models import Scenario, ToolCall, Turn


class FakeLiveKitClient:
    def run_turn(self, user: str) -> LiveKitTurnObservation:
        return LiveKitTurnObservation(
            user_transcript=user,
            assistant="Your booking is cancelled.",
            tool_calls=[ToolCall(name="cancel_booking", arguments={"id": "B1"})],
            latency_ms=420,
            component_timings_ms={"stt": 80, "llm_ttft": 210, "tts_ttfb": 90},
            session_metadata={"room": "offline-test", "session_id": "S1"},
        )


def scenario() -> Scenario:
    return Scenario(id="lk", title="LiveKit", turns=[Turn(user="Cancel B1")])


def test_livekit_adapter_accepts_injected_client_offline():
    result = LiveKitAdapter(FakeLiveKitClient()).execute(scenario())[0]
    assert result.assistant == "Your booking is cancelled."
    assert result.tool_calls[0].name == "cancel_booking"
    assert result.latency_ms == 420
    assert result.component_timings_ms["llm_ttft"] == 210
    assert result.session_metadata["room"] == "offline-test"


def test_livekit_event_normalization_captures_available_signals():
    observation = observation_from_events(
        [
            {"type": "user_input_transcribed", "transcript": "Cancel B1", "is_final": True},
            {
                "type": "conversation_item_added",
                "role": "assistant",
                "text": "Done",
                "metrics": {"e2e_latency_ms": 350},
            },
            {
                "type": "function_tools_executed",
                "function_calls": [{"name": "cancel", "arguments": {"id": "B1"}}],
            },
            {"type": "component_metric", "name": "tts_ttfb", "duration_ms": 75},
            {"type": "session_metadata", "values": {"room": "r1"}},
        ]
    )
    assert observation.user_transcript == "Cancel B1"
    assert observation.assistant == "Done"
    assert observation.latency_ms == 350
    assert observation.tool_calls[0].arguments == {"id": "B1"}
    assert observation.component_timings_ms == {"tts_ttfb": 75}
    assert observation.session_metadata == {"room": "r1"}


def test_event_collector_hooks_session_and_converts_seconds_to_ms():
    handlers = {}

    class Session:
        def on(self, name):
            return lambda callback: handlers.setdefault(name, callback)

    collector = LiveKitEventCollector({"room": "r1"})
    collector.attach(Session())
    handlers["user_input_transcribed"](
        type("Transcript", (), {"transcript": "hello", "is_final": True})()
    )
    metrics = type("Metrics", (), {"e2e_latency": 0.42})()
    item = type(
        "Item", (), {"role": "assistant", "text_content": "Hi", "metrics": metrics}
    )()
    handlers["conversation_item_added"](type("Event", (), {"item": item})())
    collector.record_component_metric("stt", 80)
    observation = collector.finish_turn()
    assert observation.assistant == "Hi"
    assert observation.latency_ms == 420
    assert observation.component_timings_ms == {"stt": 80}
    assert observation.session_metadata == {"room": "r1"}


def test_event_collector_reads_current_mapping_metrics():
    handlers = {}

    class Session:
        def on(self, name):
            return lambda callback: handlers.setdefault(name, callback)

    collector = LiveKitEventCollector()
    collector.attach(Session())
    item = type(
        "Item",
        (),
        {
            "role": "assistant",
            "text_content": "Done",
            "metrics": {
                "e2e_latency": 0.5,
                "llm_node_ttft": 0.2,
                "tts_node_ttfb": 0.1,
            },
        },
    )()
    handlers["conversation_item_added"](type("Event", (), {"item": item})())

    observation = collector.finish_turn()

    assert observation.latency_ms == 500
    assert observation.component_timings_ms == {"llm_ttft": 200, "tts_ttfb": 100}


def test_audio_request_is_explicitly_unsupported(tmp_path):
    with pytest.raises(ValueError, match="does not export audio"):
        LiveKitAdapter(FakeLiveKitClient()).execute(scenario(), tmp_path)


def test_missing_dependency_has_actionable_error(monkeypatch):
    monkeypatch.delenv("VOICE_EVAL_LIVEKIT_CLIENT", raising=False)
    original_import = __import__

    def reject_livekit(name, *args, **kwargs):
        if name.startswith("livekit"):
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_livekit)
    with pytest.raises(RuntimeError, match=r"\[livekit\].*VOICE_EVAL_LIVEKIT_CLIENT"):
        _load_configured_client()
