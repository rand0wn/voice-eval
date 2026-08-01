from __future__ import annotations

from pathlib import Path

import pytest

from voice_agent_eval_lab.adapters import get_adapter
from voice_agent_eval_lab.models import Scenario, ToolCall, Turn
from voice_agent_eval_lab.s2s import (
    MockS2SAdapter,
    S2SPipelineAdapter,
    S2STurnObservation,
)


def scenario() -> Scenario:
    return Scenario(
        id="s2s-scn",
        title="S2S",
        turns=[
            Turn(user="Book Tuesday", expected_tools=["check_availability"], must_include=["help"]),
            Turn(user="Confirm it", expected_tools=["create_booking"], must_include=["help"]),
        ],
    )


class FakeS2SClient(S2SPipelineAdapter):
    name = "fake-s2s"

    def __init__(self, audio_bytes: bytes = b"\x00" * 200) -> None:
        self._audio_bytes = audio_bytes
        self.seen_paths: list[Path] = []

    def run_turn(self, user_audio_path: Path) -> S2STurnObservation:
        self.seen_paths.append(user_audio_path)
        return S2STurnObservation(
            assistant_transcript="I can help. Done.",
            tool_calls=[ToolCall(name="check_availability", arguments={})],
            time_to_first_audio_byte_ms=120,
            assistant_audio_ms=900,
            audio_bytes=self._audio_bytes,
            session_metadata={"provider": "fake"},
        )


def test_s2s_adapter_synthesizes_user_audio_and_writes_assistant_audio(tmp_path):
    adapter = FakeS2SClient()
    results = adapter.execute(scenario(), tmp_path)

    assert len(results) == 2
    assert len(adapter.seen_paths) == 2
    for index, result in enumerate(results):
        assert Path(result.user_audio_path).is_file()
        assert Path(result.assistant_audio_path).is_file()
        assert result.assistant == "I can help. Done."
        assert result.time_to_first_audio_byte_ms == 120
        assert result.assistant_audio_ms == 900
        assert result.session_metadata == {"provider": "fake"}
        assert adapter.seen_paths[index] == Path(result.user_audio_path)


def test_s2s_adapter_requires_audio_dir():
    with pytest.raises(ValueError, match="requires audio synthesis"):
        FakeS2SClient().execute(scenario(), None)


def test_s2s_adapter_rejects_bad_observation(tmp_path):
    class BadClient(S2SPipelineAdapter):
        name = "bad"

        def run_turn(self, user_audio_path: Path) -> S2STurnObservation:
            return "not an observation"  # type: ignore[return-value]

    with pytest.raises(TypeError, match="S2STurnObservation"):
        BadClient().execute(scenario(), tmp_path)


def test_s2s_adapter_without_audio_produces_no_assistant_path(tmp_path):
    class SilentClient(S2SPipelineAdapter):
        name = "silent"

        def run_turn(self, user_audio_path: Path) -> S2STurnObservation:
            return S2STurnObservation()

    results = SilentClient().execute(scenario(), tmp_path)
    assert all(result.assistant_audio_path is None for result in results)
    assert all(result.assistant == "" for result in results)


def test_mock_s2s_adapter_is_registered_and_runs_offline(tmp_path):
    adapter = get_adapter("mock-s2s")
    assert adapter.supports_s2s is True
    results = adapter.execute(scenario(), tmp_path)
    assert len(results) == 2
    assert results[0].tool_calls[0].name == "check_availability"
    assert "help" in results[0].assistant.lower()
    for result in results:
        assert Path(result.assistant_audio_path).is_file()
        assert Path(result.assistant_audio_path).stat().st_size > 44


def test_mock_s2s_adapter_requires_audio_dir():
    with pytest.raises(ValueError, match="requires audio synthesis"):
        MockS2SAdapter().execute(scenario(), None)
