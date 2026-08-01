from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import metadata
from pathlib import Path
from typing import Callable

from . import audio
from .models import Scenario, ToolCall, Turn, TurnResult


class VoicePipelineAdapter(ABC):
    """Minimal provider boundary. Real integrations implement this contract.

    `execute` receives the scenario and an audio directory (may be `None` to
    skip audio synthesis) and returns one `TurnResult` per scripted turn, in
    order. A real adapter would drive an actual STT/LLM/TTS or speech-to-speech
    pipeline here; the evaluator and grading logic do not change either way.
    """

    name: str

    @abstractmethod
    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        raise NotImplementedError


class _DeterministicAdapter(VoicePipelineAdapter):
    latency_ms: float

    def _respond(self, scenario: Scenario, turn: Turn, index: int, audio_dir: Path | None) -> TurnResult:
        tools = [ToolCall(name=name, arguments={"source": "sim"}) for name in turn.expected_tools]
        required = " ".join(turn.must_include)
        assistant = f"I can help. {required}".strip()

        user_audio_path = None
        assistant_audio_path = None
        assistant_audio_ms = None
        if audio_dir is not None:
            user_wav = audio_dir / f"t{index:02d}_user.wav"
            bot_wav = audio_dir / f"t{index:02d}_bot.wav"
            audio.synth_speech(turn.user, user_wav, voice=f"{scenario.persona}-user")
            assistant_audio_ms = audio.synth_speech(assistant, bot_wav, voice=f"{scenario.persona}-{self.name}")
            user_audio_path = str(user_wav)
            assistant_audio_path = str(bot_wav)

        return TurnResult(
            user=turn.user,
            assistant=assistant,
            latency_ms=self.latency_ms,
            tool_calls=tools,
            user_audio_path=user_audio_path,
            assistant_audio_path=assistant_audio_path,
            assistant_audio_ms=assistant_audio_ms,
        )

    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        return [
            self._respond(scenario, turn, index, audio_dir)
            for index, turn in enumerate(scenario.turns)
        ]


class MockCascadeAdapter(_DeterministicAdapter):
    """Stand-in for a discrete STT -> LLM -> TTS pipeline."""

    name = "cascade"
    latency_ms = 640.0


class MockRealtimeAdapter(_DeterministicAdapter):
    """Stand-in for a native speech-to-speech (realtime) pipeline."""

    name = "realtime"
    latency_ms = 310.0


class MockDegradedAdapter(_DeterministicAdapter):
    """Intentionally unreliable pipeline used to demonstrate useful failures.

    Even-numbered turns miss their expected tool and required response content,
    exceed response-shape limits, and every turn breaches the latency budget.
    This is a demo fixture, not a benchmark of any real provider.
    """

    name = "degraded"
    latency_ms = 1450.0

    def _respond(
        self,
        scenario: Scenario,
        turn: Turn,
        index: int,
        audio_dir: Path | None,
    ) -> TurnResult:
        result = super()._respond(scenario, turn, index, audio_dir)
        if index % 2 == 0:
            result.tool_calls = []
            result.assistant = (
                "I am not sure? Could you repeat? Let me check? This may take a while."
            )
            if result.assistant_audio_path is not None:
                result.assistant_audio_ms = audio.synth_speech(
                    result.assistant,
                    Path(result.assistant_audio_path),
                    voice=f"{scenario.persona}-{self.name}",
                )
        return result


AdapterFactory = Callable[[], VoicePipelineAdapter]
_ADAPTERS: dict[str, AdapterFactory] = {
    "cascade": MockCascadeAdapter,
    "realtime": MockRealtimeAdapter,
    "degraded": MockDegradedAdapter,
}
_ENTRY_POINTS_LOADED = False


def register_adapter(name: str, factory: AdapterFactory, *, replace: bool = False) -> None:
    """Register an adapter factory without modifying this package.

    Libraries should normally expose the factory through the
    ``voice_agent_eval_lab.adapters`` entry-point group. Direct registration is
    useful for applications and tests.
    """

    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("Adapter name cannot be empty")
    if normalized in _ADAPTERS and not replace:
        raise ValueError(f"Adapter {normalized!r} is already registered")
    if not callable(factory):
        raise TypeError("Adapter factory must be callable")
    _ADAPTERS[normalized] = factory


def _load_entry_points() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    _ENTRY_POINTS_LOADED = True
    for entry_point in metadata.entry_points(group="voice_agent_eval_lab.adapters"):
        if entry_point.name.strip().lower() in _ADAPTERS:
            raise ValueError(
                f"Adapter entry point {entry_point.name!r} duplicates an existing adapter"
            )
        register_adapter(entry_point.name, entry_point.load())


def available_adapters() -> tuple[str, ...]:
    _load_entry_points()
    return tuple(sorted(_ADAPTERS))


def get_adapter(name: str) -> VoicePipelineAdapter:
    _load_entry_points()
    normalized = name.strip().lower()
    try:
        adapter = _ADAPTERS[normalized]()
    except KeyError as exc:
        choices = ", ".join(available_adapters())
        raise ValueError(f"Unknown adapter {name!r}. Available adapters: {choices}") from exc
    if not isinstance(adapter, VoicePipelineAdapter):
        raise TypeError(
            f"Adapter factory {normalized!r} returned {type(adapter).__name__}, "
            "expected VoicePipelineAdapter"
        )
    return adapter


def _livekit_factory() -> VoicePipelineAdapter:
    from .livekit_adapter import LiveKitAdapter

    return LiveKitAdapter()


register_adapter("livekit", _livekit_factory)
