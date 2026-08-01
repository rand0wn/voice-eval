"""Native speech-to-speech (S2S) extension point.

Text-driven adapters (`adapters.py`, `livekit_adapter.py`) feed `turn.user`
straight to the pipeline and grade the text it returns. Native S2S pipelines
(OpenAI Realtime, ElevenLabs Conversational AI, Vapi, Pipecat, ...) often
don't expose intermediate text at all -- the only thing you can drive in and
observe out is audio. This module is the reusable seam for that: synthesize
`turn.user` to a WAV, hand the WAV to the pipeline, and normalize whatever it
gives back (audio, an optional transcript, tool calls, timings) into the same
`TurnResult` the rest of the runner/CLI/grading already understand.

Mirrors the `LiveKitTurnObservation` / `LiveKitTurnClient` pattern in
`livekit_adapter.py` on purpose, so both "real" integration seams look and
behave the same way. Sibling adapters (ElevenLabs, Vapi, Pipecat, ...) should
build on this module rather than inventing their own audio contract:

- Implement `S2SClient` (or subclass `S2SPipelineAdapter` and implement
  `run_turn`) against your provider's session/streaming API.
- Return an `S2STurnObservation` per turn. Only `audio_bytes` or `audio_path`
  is required; everything else (`assistant_transcript`, `tool_calls`,
  `time_to_first_audio_byte_ms`, `assistant_audio_ms`, `session_metadata`) is
  optional and should be left at its default when your pipeline doesn't
  expose it.
- `S2SPipelineAdapter.execute()` handles synthesizing the user turn to audio,
  timing the round trip, writing the returned audio under `audio_dir`, and
  building the `TurnResult` -- so the runner and CLI never need to branch on
  adapter type; they just call `adapter.execute(scenario, audio_dir)` like
  any other adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from . import audio
from .adapters import VoicePipelineAdapter
from .models import Scenario, ToolCall, TurnResult


@dataclass
class S2STurnObservation:
    """Provider-neutral snapshot returned by a native speech-to-speech client.

    Timings are milliseconds. ``assistant_transcript`` is optional: report it
    when the pipeline exposes one (many do, as a debug/analytics side
    channel) so the existing text-based grading rules (must-include phrases,
    tool recall wording, sentence/question shape) still apply; leave it
    ``None`` when it is genuinely unavailable and grading falls back to the
    audio-derived signals (`assistant_audio_playable`,
    `time_to_first_audio_byte_budget`, latency, tool calls).

    Provide the assistant's audio as either ``audio_bytes`` (raw/streamed
    bytes already assembled by the caller) or ``audio_path`` (a file the
    client already wrote); ``audio_bytes`` takes precedence when both are
    set. At least one should be set for a turn to count as producing a
    playable response.
    """

    assistant_transcript: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    time_to_first_audio_byte_ms: float | None = None
    assistant_audio_ms: float | None = None
    audio_bytes: bytes | None = None
    audio_path: str | None = None
    session_metadata: dict[str, Any] = field(default_factory=dict)


class S2SClient(Protocol):
    """One turn in, one `S2STurnObservation` out, driven by audio (not text)."""

    def run_turn(self, user_audio_path: Path) -> S2STurnObservation: ...


class S2SPipelineAdapter(VoicePipelineAdapter):
    """Base class for adapters driven by synthesized user audio, not text.

    Subclasses implement `run_turn` (same shape as `S2SClient.run_turn`)
    instead of `execute` directly. This base class synthesizes each
    `turn.user` to a WAV via `audio.synth_speech`, times the round trip,
    normalizes the returned `S2STurnObservation` into a `TurnResult`, and
    writes the assistant's audio under `audio_dir` -- identical artifact
    layout (`t{index:02d}_user.wav` / `t{index:02d}_bot.wav`) to the existing
    mock adapters, so downstream tooling (report writers, audio review)
    doesn't need to know which mode produced a run.

    S2S mode always requires an `audio_dir`: there is nothing else to send
    into (or grade from) a native speech pipeline.
    """

    supports_s2s = True

    def run_turn(self, user_audio_path: Path) -> S2STurnObservation:
        raise NotImplementedError

    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        if audio_dir is None:
            raise ValueError(
                f"{type(self).__name__} requires audio synthesis: run with "
                "`--audio-mode s2s` (audio artifacts are written automatically). "
                "It drives the pipeline with synthesized audio and cannot run text-only."
            )
        audio_dir.mkdir(parents=True, exist_ok=True)

        results: list[TurnResult] = []
        for index, turn in enumerate(scenario.turns):
            user_wav = audio_dir / f"t{index:02d}_user.wav"
            audio.synth_speech(turn.user, user_wav, voice=f"{scenario.persona}-user")

            started = perf_counter()
            observed = self.run_turn(user_wav)
            elapsed_ms = (perf_counter() - started) * 1000
            if not isinstance(observed, S2STurnObservation):
                raise TypeError(f"{type(self).__name__}.run_turn() must return S2STurnObservation")

            assistant_audio_path: str | None = None
            if observed.audio_bytes is not None or observed.audio_path is not None:
                bot_wav = audio_dir / f"t{index:02d}_bot.wav"
                if observed.audio_bytes is not None:
                    bot_wav.write_bytes(observed.audio_bytes)
                else:
                    bot_wav.write_bytes(Path(observed.audio_path).read_bytes())
                assistant_audio_path = str(bot_wav)

            results.append(
                TurnResult(
                    user=turn.user,
                    assistant=observed.assistant_transcript or "",
                    latency_ms=elapsed_ms,
                    tool_calls=observed.tool_calls,
                    user_audio_path=str(user_wav),
                    assistant_audio_path=assistant_audio_path,
                    assistant_audio_ms=observed.assistant_audio_ms,
                    time_to_first_audio_byte_ms=observed.time_to_first_audio_byte_ms,
                    session_metadata=observed.session_metadata,
                )
            )
        return results


class MockS2SAdapter(S2SPipelineAdapter):
    """Offline demo of a native speech-to-speech pipeline.

    Stands in for a provider like OpenAI Realtime or ElevenLabs
    Conversational AI that only exchanges audio: it "listens" to the
    synthesized user WAV (a demo fixture, not real STT) and returns
    synthesized assistant audio plus a transcript side-channel, going through
    the exact same `S2SPipelineAdapter.execute()` path a real integration
    would. No network access or credentials required, matching the existing
    `MockCascadeAdapter` / `MockRealtimeAdapter` demo adapters in
    `adapters.py`.
    """

    name = "mock-s2s"
    latency_ms = 280.0

    def __init__(self) -> None:
        self._scenario: Scenario | None = None
        self._turn_index = 0

    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        self._scenario = scenario
        self._turn_index = 0
        return super().execute(scenario, audio_dir)

    def run_turn(self, user_audio_path: Path) -> S2STurnObservation:
        assert self._scenario is not None, "run_turn called outside of execute()"
        turn = self._scenario.turns[self._turn_index]
        self._turn_index += 1

        tool_calls = [
            ToolCall(name=tool_name, arguments={"source": "mock-s2s"})
            for tool_name in turn.expected_tools
        ]
        required = " ".join(turn.must_include)
        transcript = f"I can help. {required}".strip()

        scratch_wav = user_audio_path.parent / f"{user_audio_path.stem}_reply_scratch.wav"
        assistant_audio_ms = audio.synth_speech(
            transcript, scratch_wav, voice=f"{self._scenario.persona}-{self.name}"
        )
        audio_bytes = scratch_wav.read_bytes()
        scratch_wav.unlink(missing_ok=True)

        return S2STurnObservation(
            assistant_transcript=transcript,
            tool_calls=tool_calls,
            time_to_first_audio_byte_ms=self.latency_ms * 0.4,
            assistant_audio_ms=assistant_audio_ms,
            audio_bytes=audio_bytes,
            session_metadata={"mode": "s2s-mock"},
        )
