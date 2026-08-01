from __future__ import annotations

import pytest

from voice_agent_eval_lab.models import Scenario, ToolCall, Turn
from voice_agent_eval_lab.vapi_adapter import (
    VapiAdapter,
    VapiTurnObservation,
    _extract_assistant_text,
    _extract_tool_calls,
    _load_configured_client,
)


class FakeVapiClient:
    def run_turn(self, user: str) -> VapiTurnObservation:
        return VapiTurnObservation(
            user_transcript=user,
            assistant="Your booking is cancelled.",
            tool_calls=[ToolCall(name="cancel_booking", arguments={"id": "B1"})],
            latency_ms=380,
            call_metadata={"chat_id": "chat_1"},
        )


def scenario() -> Scenario:
    return Scenario(id="vp", title="Vapi", turns=[Turn(user="Cancel B1")])


def test_vapi_adapter_accepts_injected_client_offline():
    result = VapiAdapter(FakeVapiClient()).execute(scenario())[0]
    assert result.assistant == "Your booking is cancelled."
    assert result.tool_calls[0].name == "cancel_booking"
    assert result.tool_calls[0].arguments == {"id": "B1"}
    assert result.latency_ms == 380
    assert result.session_metadata["chat_id"] == "chat_1"
    assert result.user == "Cancel B1"


def test_vapi_adapter_falls_back_to_wallclock_latency():
    class NoLatencyClient:
        def run_turn(self, user: str) -> VapiTurnObservation:
            return VapiTurnObservation(assistant="Done", user_transcript=user)

    result = VapiAdapter(NoLatencyClient()).execute(scenario())[0]
    assert result.latency_ms >= 0


def test_vapi_adapter_synthesizes_audio_when_requested(tmp_path):
    results = VapiAdapter(FakeVapiClient()).execute(scenario(), tmp_path)
    result = results[0]
    assert result.user_audio_path is not None
    assert result.assistant_audio_path is not None
    assert result.assistant_audio_ms is not None
    assert (tmp_path / "t00_user.wav").exists()
    assert (tmp_path / "t00_bot.wav").exists()


def test_vapi_adapter_rejects_non_observation_client():
    class BadClient:
        def run_turn(self, user: str):
            return {"assistant": "oops"}

    with pytest.raises(TypeError, match="VapiTurnObservation"):
        VapiAdapter(BadClient()).execute(scenario())


def test_missing_credentials_has_actionable_error(monkeypatch):
    monkeypatch.delenv("VOICE_EVAL_VAPI_CLIENT", raising=False)
    monkeypatch.delenv("VAPI_API_KEY", raising=False)
    monkeypatch.delenv("VAPI_ASSISTANT_ID", raising=False)
    with pytest.raises(RuntimeError, match=r"VAPI_API_KEY.*VAPI_ASSISTANT_ID"):
        _load_configured_client()


def test_missing_assistant_id_only_still_actionable(monkeypatch):
    monkeypatch.delenv("VOICE_EVAL_VAPI_CLIENT", raising=False)
    monkeypatch.setenv("VAPI_API_KEY", "sk_test")
    monkeypatch.delenv("VAPI_ASSISTANT_ID", raising=False)
    with pytest.raises(RuntimeError, match=r"VAPI_API_KEY.*VAPI_ASSISTANT_ID"):
        _load_configured_client()


def test_configured_client_factory_must_use_module_colon_attribute(monkeypatch):
    monkeypatch.setenv("VOICE_EVAL_VAPI_CLIENT", "not-a-valid-target")
    with pytest.raises(RuntimeError, match="module:factory"):
        _load_configured_client()


def test_configured_client_factory_loads_injected_client(monkeypatch):
    import sys
    import types

    module = types.ModuleType("fake_vapi_client_module")

    def make_client() -> FakeVapiClient:
        return FakeVapiClient()

    module.make_client = make_client
    sys.modules["fake_vapi_client_module"] = module
    monkeypatch.setenv("VOICE_EVAL_VAPI_CLIENT", "fake_vapi_client_module:make_client")
    try:
        client = _load_configured_client()
        assert isinstance(client, FakeVapiClient)
    finally:
        del sys.modules["fake_vapi_client_module"]


def test_extract_assistant_text_reads_last_assistant_message():
    body = {
        "output": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]
    }
    assert _extract_assistant_text(body) == "second"


def test_extract_assistant_text_defaults_to_empty_string():
    assert _extract_assistant_text({"output": []}) == ""


def test_extract_tool_calls_reads_function_shape():
    body = {
        "output": [
            {
                "role": "assistant",
                "content": "Cancelling.",
                "toolCalls": [
                    {"function": {"name": "cancel_booking", "arguments": {"id": "B1"}}}
                ],
            }
        ]
    }
    calls = _extract_tool_calls(body)
    assert calls[0].name == "cancel_booking"
    assert calls[0].arguments == {"id": "B1"}


def test_extract_tool_calls_parses_stringified_arguments():
    body = {
        "output": [
            {
                "role": "assistant",
                "content": "Cancelling.",
                "toolCalls": [
                    {"function": {"name": "cancel_booking", "arguments": '{"id": "B1"}'}}
                ],
            }
        ]
    }
    calls = _extract_tool_calls(body)
    assert calls[0].arguments == {"id": "B1"}
