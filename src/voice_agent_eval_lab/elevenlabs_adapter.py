from __future__ import annotations

import base64
import importlib
import os
import wave
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping, Protocol

from . import audio
from .adapters import VoicePipelineAdapter
from .models import Scenario, ToolCall, TurnResult

# Matches the sample rate audio.py's offline synthesizer already uses, and the
# common ElevenLabs Conversational AI PCM output format (`pcm_16000`).
_ASSISTANT_AUDIO_SAMPLE_RATE = 16_000


@dataclass
class ElevenLabsTurnObservation:
    """Provider-neutral snapshot returned by an ElevenLabs conversation client.

    Timings are milliseconds. ``audio_pcm16`` is raw mono 16-bit PCM audio for
    the assistant's spoken reply, if the client captured it (the WebSocket
    API streams it as base64-encoded ``audio`` events); leave it ``None`` when
    audio wasn't captured and the adapter will fall back to the offline
    synthesizer used by the mock adapters.
    """

    assistant: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float | None = None
    user_transcript: str | None = None
    audio_pcm16: bytes | None = None
    session_metadata: dict[str, Any] = field(default_factory=dict)


class ElevenLabsConversationClient(Protocol):
    def send_user_message(self, text: str) -> ElevenLabsTurnObservation: ...


class ElevenLabsAdapter(VoicePipelineAdapter):
    """Evaluate ElevenLabs Conversational AI through an injected client.

    ElevenLabs agents are configured and owned in the ElevenLabs dashboard (or
    via their agent-management API), so this adapter deliberately does not
    create or configure an agent. Supply a client that sends one text turn
    over the ``wss://api.elevenlabs.io/v1/convai/conversation`` session and
    returns the events it observed, either directly or through
    ``VOICE_EVAL_ELEVENLABS_CLIENT=module:factory``.

    Required environment variables for the default (real) client:

    - ``ELEVENLABS_API_KEY`` -- ElevenLabs API key (``xi-api-key`` header),
      used to fetch a signed conversation URL for private agents.
    - ``ELEVENLABS_AGENT_ID`` -- the Conversational AI agent to evaluate.

    Neither variable is read by this adapter's tests; they only matter when
    no ``client`` is injected and no ``VOICE_EVAL_ELEVENLABS_CLIENT`` override
    is set, i.e. when actually talking to the real API.
    """

    name = "elevenlabs"

    def __init__(self, client: ElevenLabsConversationClient | None = None) -> None:
        self.client = client or _load_configured_client()

    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        results: list[TurnResult] = []
        for index, turn in enumerate(scenario.turns):
            started = perf_counter()
            observed = self.client.send_user_message(turn.user)
            elapsed_ms = (perf_counter() - started) * 1000
            if not isinstance(observed, ElevenLabsTurnObservation):
                raise TypeError(
                    "ElevenLabs client.send_user_message() must return "
                    "ElevenLabsTurnObservation"
                )

            user_audio_path = None
            assistant_audio_path = None
            assistant_audio_ms = None
            if audio_dir is not None:
                user_wav = audio_dir / f"t{index:02d}_user.wav"
                bot_wav = audio_dir / f"t{index:02d}_bot.wav"
                audio.synth_speech(
                    observed.user_transcript or turn.user,
                    user_wav,
                    voice=f"{scenario.persona}-user",
                )
                if observed.audio_pcm16:
                    assistant_audio_ms = _write_pcm16_wav(observed.audio_pcm16, bot_wav)
                else:
                    assistant_audio_ms = audio.synth_speech(
                        observed.assistant, bot_wav, voice=f"{scenario.persona}-{self.name}"
                    )
                user_audio_path = str(user_wav)
                assistant_audio_path = str(bot_wav)

            results.append(
                TurnResult(
                    user=observed.user_transcript or turn.user,
                    assistant=observed.assistant,
                    latency_ms=observed.latency_ms if observed.latency_ms is not None else elapsed_ms,
                    tool_calls=observed.tool_calls,
                    user_audio_path=user_audio_path,
                    assistant_audio_path=assistant_audio_path,
                    assistant_audio_ms=assistant_audio_ms,
                    session_metadata=observed.session_metadata,
                )
            )
        return results


def _write_pcm16_wav(pcm16_bytes: bytes, path: Path) -> float:
    """Wrap raw mono 16-bit PCM audio (as ElevenLabs streams it) into a WAV file.

    Returns the duration in milliseconds, matching ``audio.synth_speech``'s
    return contract so callers can treat both sources interchangeably.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(_ASSISTANT_AUDIO_SAMPLE_RATE)
        wav_file.writeframes(pcm16_bytes)
    n_samples = len(pcm16_bytes) // 2
    return (n_samples / _ASSISTANT_AUDIO_SAMPLE_RATE) * 1000


def _load_configured_client() -> ElevenLabsConversationClient:
    target = os.getenv("VOICE_EVAL_ELEVENLABS_CLIENT")
    if not target:
        try:
            importlib.import_module("websockets")
        except ImportError as exc:
            raise RuntimeError(
                "ElevenLabs support is optional. Install it with "
                "`pip install 'voice-agent-eval-lab[elevenlabs]'`, set "
                "ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID, then either "
                "construct ElevenLabsAdapter(client=...) directly or set "
                "VOICE_EVAL_ELEVENLABS_CLIENT=your_module:factory."
            ) from exc
        api_key = os.getenv("ELEVENLABS_API_KEY")
        agent_id = os.getenv("ELEVENLABS_AGENT_ID")
        if not api_key or not agent_id:
            raise RuntimeError(
                "ElevenLabs credentials missing. Set ELEVENLABS_API_KEY and "
                "ELEVENLABS_AGENT_ID (see docs/elevenlabs.md), or set "
                "VOICE_EVAL_ELEVENLABS_CLIENT=your_module:factory to a factory "
                "that returns an ElevenLabsConversationClient."
            )
        from ._elevenlabs_ws_client import WebSocketElevenLabsClient

        return WebSocketElevenLabsClient(api_key=api_key, agent_id=agent_id)

    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise RuntimeError(
            "VOICE_EVAL_ELEVENLABS_CLIENT must use the form `python_module:factory`."
        )
    try:
        factory: Callable[[], ElevenLabsConversationClient] = getattr(
            importlib.import_module(module_name), attribute
        )
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"Could not load ElevenLabs client factory {target!r}: {exc}") from exc
    client = factory()
    if not callable(getattr(client, "send_user_message", None)):
        raise RuntimeError(
            f"ElevenLabs client factory {target!r} did not return a send_user_message client"
        )
    return client


def observation_from_events(
    events: list[Mapping[str, Any]], *, session_metadata: Mapping[str, Any] | None = None
) -> ElevenLabsTurnObservation:
    """Normalize captured ElevenLabs Conversational AI WebSocket events into one turn.

    This mirrors the LiveKit adapter's ``observation_from_events`` seam so a
    production collector and offline test fixtures share identical
    normalization. Expected record ``type`` values follow the documented
    server-to-client protocol: ``user_transcript``, ``agent_response``,
    ``client_tool_call``, and ``audio``.
    """

    user_transcript: str | None = None
    assistant = ""
    tools: list[ToolCall] = []
    audio_chunks: list[bytes] = []
    metadata = dict(session_metadata or {})
    for event in events:
        kind = event.get("type")
        if kind == "user_transcript":
            user_transcript = str(event.get("user_transcription_event", {}).get("user_transcript", ""))
        elif kind == "agent_response":
            assistant = str(event.get("agent_response_event", {}).get("agent_response", ""))
        elif kind == "client_tool_call":
            call = event.get("client_tool_call", {})
            tools.append(
                ToolCall(
                    name=str(call.get("tool_name", "unknown")),
                    arguments=dict(call.get("parameters") or {}),
                )
            )
        elif kind == "audio":
            b64 = event.get("audio_event", {}).get("audio_base_64")
            if b64:
                audio_chunks.append(base64.b64decode(b64))
        elif kind == "session_metadata":
            metadata.update(dict(event.get("values") or {}))

    return ElevenLabsTurnObservation(
        assistant=assistant,
        tool_calls=tools,
        user_transcript=user_transcript,
        audio_pcm16=b"".join(audio_chunks) if audio_chunks else None,
        session_metadata=metadata,
    )
