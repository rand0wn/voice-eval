from __future__ import annotations

import builtins
import wave

import pytest

from voice_agent_eval_lab.elevenlabs_adapter import (
    ElevenLabsAdapter,
    ElevenLabsTurnObservation,
    _load_configured_client,
    observation_from_events,
)
from voice_agent_eval_lab.models import Scenario, ToolCall, Turn


class FakeElevenLabsClient:
    def __init__(self):
        self.sent: list[str] = []

    def send_user_message(self, text: str) -> ElevenLabsTurnObservation:
        self.sent.append(text)
        # 8000 samples at 16kHz == 500ms, so duration math is checkable.
        pcm = (b"\x00\x01" * 8000)
        return ElevenLabsTurnObservation(
            user_transcript=text,
            assistant="Your booking is cancelled.",
            tool_calls=[ToolCall(name="cancel_booking", arguments={"id": "B1"})],
            latency_ms=380,
            audio_pcm16=pcm,
            session_metadata={"conversation_id": "conv_1"},
        )


def scenario() -> Scenario:
    return Scenario(id="el", title="ElevenLabs", turns=[Turn(user="Cancel B1")])


def test_elevenlabs_adapter_accepts_injected_client_offline():
    client = FakeElevenLabsClient()
    result = ElevenLabsAdapter(client).execute(scenario())[0]
    assert client.sent == ["Cancel B1"]
    assert result.user == "Cancel B1"
    assert result.assistant == "Your booking is cancelled."
    assert result.tool_calls[0].name == "cancel_booking"
    assert result.tool_calls[0].arguments == {"id": "B1"}
    assert result.latency_ms == 380
    assert result.session_metadata["conversation_id"] == "conv_1"
    # No audio_dir was passed, so no audio artifacts are written.
    assert result.user_audio_path is None
    assert result.assistant_audio_path is None


def test_elevenlabs_adapter_writes_captured_audio(tmp_path):
    client = FakeElevenLabsClient()
    result = ElevenLabsAdapter(client).execute(scenario(), tmp_path)[0]

    assert result.user_audio_path is not None
    assert result.assistant_audio_path is not None
    with wave.open(result.assistant_audio_path, "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16_000
        assert wav_file.getnframes() == 8000
    assert result.assistant_audio_ms == pytest.approx(500.0)


def test_elevenlabs_adapter_falls_back_to_synth_when_no_audio_captured(tmp_path):
    class NoAudioClient:
        def send_user_message(self, text: str) -> ElevenLabsTurnObservation:
            return ElevenLabsTurnObservation(user_transcript=text, assistant="Done.")

    result = ElevenLabsAdapter(NoAudioClient()).execute(scenario(), tmp_path)[0]
    assert result.assistant_audio_path is not None
    assert result.assistant_audio_ms is not None
    with wave.open(result.assistant_audio_path, "rb") as wav_file:
        assert wav_file.getnframes() > 0


def test_elevenlabs_event_normalization_captures_available_signals():
    observation = observation_from_events(
        [
            {
                "type": "user_transcript",
                "user_transcription_event": {"user_transcript": "Cancel B1"},
            },
            {
                "type": "client_tool_call",
                "client_tool_call": {
                    "tool_name": "cancel_booking",
                    "parameters": {"id": "B1"},
                    "tool_call_id": "tc_1",
                },
            },
            {
                "type": "audio",
                "audio_event": {"audio_base_64": "AAA="},
            },
            {
                "type": "agent_response",
                "agent_response_event": {"agent_response": "Your booking is cancelled."},
            },
            {"type": "session_metadata", "values": {"conversation_id": "conv_1"}},
        ]
    )
    assert observation.user_transcript == "Cancel B1"
    assert observation.assistant == "Your booking is cancelled."
    assert observation.tool_calls[0].name == "cancel_booking"
    assert observation.tool_calls[0].arguments == {"id": "B1"}
    assert observation.audio_pcm16 is not None
    assert observation.session_metadata == {"conversation_id": "conv_1"}


def test_missing_credentials_has_actionable_error(monkeypatch):
    monkeypatch.delenv("VOICE_EVAL_ELEVENLABS_CLIENT", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_AGENT_ID", raising=False)
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        _load_configured_client()


def test_missing_dependency_has_actionable_error(monkeypatch):
    monkeypatch.delenv("VOICE_EVAL_ELEVENLABS_CLIENT", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent")
    original_import = __import__

    def reject_websockets(name, *args, **kwargs):
        if name.startswith("websockets"):
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_websockets)
    with pytest.raises(RuntimeError, match=r"\[elevenlabs\].*VOICE_EVAL_ELEVENLABS_CLIENT"):
        _load_configured_client()


def test_invalid_override_target_is_rejected(monkeypatch):
    monkeypatch.setenv("VOICE_EVAL_ELEVENLABS_CLIENT", "not-a-valid-target")
    with pytest.raises(RuntimeError, match="python_module:factory"):
        _load_configured_client()
