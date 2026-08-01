from __future__ import annotations

import importlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Protocol

from . import audio
from .adapters import VoicePipelineAdapter
from .models import Scenario, ToolCall, TurnResult

VAPI_API_BASE = "https://api.vapi.ai"


@dataclass
class VapiTurnObservation:
    """Provider-neutral snapshot returned by a Vapi call/session client.

    ``tool_calls`` covers what Vapi's API calls "function calls" (tool/function
    invocations executed during the assistant's turn). ``latency_ms`` is the
    end-to-end turn latency if the client can report it; otherwise the adapter
    falls back to wall-clock time around the call. ``call_metadata`` can carry
    identifiers such as the Vapi ``callId``/``chatId`` for later lookup.
    """

    assistant: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float | None = None
    user_transcript: str | None = None
    call_metadata: dict[str, Any] = field(default_factory=dict)


class VapiTurnClient(Protocol):
    def run_turn(self, user: str) -> VapiTurnObservation: ...


class VapiAdapter(VoicePipelineAdapter):
    """Drive a Vapi (https://vapi.ai) assistant through an injected client.

    Vapi assistants, phone numbers, and call/session lifecycle are configured
    in the Vapi dashboard or via its REST API, so this adapter deliberately
    does not manage that setup itself. Supply a client that drives one turn
    and returns the transcript/tool-call/latency signals it observed, either
    directly or through ``VOICE_EVAL_VAPI_CLIENT=module:factory``.

    Without an injected client or ``VOICE_EVAL_VAPI_CLIENT``, the adapter
    builds a best-effort real HTTP client (:class:`VapiHTTPClient`) from two
    environment variables:

    - ``VAPI_API_KEY``: a Vapi private API key (from the Vapi dashboard).
    - ``VAPI_ASSISTANT_ID``: the assistant to converse with.

    Missing credentials raise a clear ``RuntimeError`` instead of crashing;
    tests always inject a fake client and never reach the real HTTP path, so
    the default test suite makes no network calls.
    """

    name = "vapi"

    def __init__(self, client: VapiTurnClient | None = None) -> None:
        self.client = client or _load_configured_client()

    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        results: list[TurnResult] = []
        for index, turn in enumerate(scenario.turns):
            started = perf_counter()
            observed = self.client.run_turn(turn.user)
            elapsed_ms = (perf_counter() - started) * 1000
            if not isinstance(observed, VapiTurnObservation):
                raise TypeError("Vapi client.run_turn() must return VapiTurnObservation")

            user_text = observed.user_transcript or turn.user
            user_audio_path = None
            assistant_audio_path = None
            assistant_audio_ms = None
            if audio_dir is not None:
                # Vapi calls are audio-native, but the injected client only
                # returns text signals here; synthesize placeholder audio the
                # same way the built-in mock adapters do so every turn still
                # gets a playable artifact (see audio.synth_speech).
                user_wav = audio_dir / f"t{index:02d}_user.wav"
                bot_wav = audio_dir / f"t{index:02d}_bot.wav"
                audio.synth_speech(user_text, user_wav, voice=f"{scenario.persona}-user")
                assistant_audio_ms = audio.synth_speech(
                    observed.assistant, bot_wav, voice=f"{scenario.persona}-{self.name}"
                )
                user_audio_path = str(user_wav)
                assistant_audio_path = str(bot_wav)

            results.append(
                TurnResult(
                    user=user_text,
                    assistant=observed.assistant,
                    latency_ms=observed.latency_ms if observed.latency_ms is not None else elapsed_ms,
                    tool_calls=observed.tool_calls,
                    user_audio_path=user_audio_path,
                    assistant_audio_path=assistant_audio_path,
                    assistant_audio_ms=assistant_audio_ms,
                    session_metadata=observed.call_metadata,
                )
            )
        return results


class VapiHTTPClient:
    """Best-effort real client against Vapi's Chat API (api.vapi.ai/chat).

    Uses only the standard library (``urllib``) so no extra dependency is
    required to install or import this adapter. Each turn posts the user's
    text to the configured assistant and continues the same chat by chaining
    ``previousChatId``, matching the "start a call/chat, get a transcript and
    any function calls back" shape described in the Vapi docs
    (https://docs.vapi.ai). This client is never exercised by the default
    test suite: tests inject a fake client instead.
    """

    def __init__(
        self,
        api_key: str,
        assistant_id: str,
        *,
        base_url: str = VAPI_API_BASE,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._assistant_id = assistant_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._previous_chat_id: str | None = None

    def run_turn(self, user: str) -> VapiTurnObservation:
        payload: dict[str, Any] = {"assistantId": self._assistant_id, "input": user}
        if self._previous_chat_id:
            payload["previousChatId"] = self._previous_chat_id

        request = urllib.request.Request(
            f"{self._base_url}/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Vapi API request failed: {exc}") from exc
        elapsed_ms = (perf_counter() - started) * 1000

        chat_id = body.get("id")
        if chat_id:
            self._previous_chat_id = chat_id

        return VapiTurnObservation(
            assistant=_extract_assistant_text(body),
            tool_calls=_extract_tool_calls(body),
            latency_ms=elapsed_ms,
            user_transcript=user,
            call_metadata={"chat_id": chat_id} if chat_id else {},
        )


def _extract_assistant_text(body: dict[str, Any]) -> str:
    """Pull the assistant's reply text out of a Vapi chat response body."""
    for message in reversed(body.get("output", [])):
        if message.get("role") == "assistant" and message.get("content"):
            return str(message["content"])
    return ""


def _extract_tool_calls(body: dict[str, Any]) -> list[ToolCall]:
    """Pull executed tool/function calls out of a Vapi chat response body."""
    calls: list[ToolCall] = []
    for message in body.get("output", []):
        for call in message.get("toolCalls", []) or []:
            function = call.get("function", {})
            name = function.get("name") or call.get("name") or "unknown"
            arguments = function.get("arguments") or call.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": arguments}
            calls.append(ToolCall(name=str(name), arguments=dict(arguments)))
    return calls


def _load_configured_client() -> VapiTurnClient:
    target = os.getenv("VOICE_EVAL_VAPI_CLIENT")
    if target:
        module_name, separator, attribute = target.partition(":")
        if not separator or not module_name or not attribute:
            raise RuntimeError("VOICE_EVAL_VAPI_CLIENT must use the form `python_module:factory`.")
        try:
            factory: Callable[[], VapiTurnClient] = getattr(
                importlib.import_module(module_name), attribute
            )
        except (ImportError, AttributeError) as exc:
            raise RuntimeError(f"Could not load Vapi client factory {target!r}: {exc}") from exc
        client = factory()
        if not callable(getattr(client, "run_turn", None)):
            raise RuntimeError(f"Vapi client factory {target!r} did not return a run_turn client")
        return client

    api_key = os.getenv("VAPI_API_KEY")
    assistant_id = os.getenv("VAPI_ASSISTANT_ID")
    if not api_key or not assistant_id:
        raise RuntimeError(
            "Vapi credentials are missing. Set VAPI_API_KEY and VAPI_ASSISTANT_ID "
            "(from https://dashboard.vapi.ai), or set "
            "VOICE_EVAL_VAPI_CLIENT=your_module:factory to inject a custom client."
        )
    return VapiHTTPClient(api_key=api_key, assistant_id=assistant_id)
