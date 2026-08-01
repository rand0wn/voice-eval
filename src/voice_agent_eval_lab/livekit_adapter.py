from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping, Protocol

from .adapters import VoicePipelineAdapter
from .models import Scenario, ToolCall, TurnResult


@dataclass
class LiveKitTurnObservation:
    """Provider-neutral snapshot returned by a LiveKit session client.

    Timings are milliseconds. ``component_timings_ms`` can contain the metrics
    exposed by the configured LiveKit pipeline (for example ``stt``,
    ``llm_ttft`` and ``tts_ttfb``); absent metrics are left absent.
    """

    assistant: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float | None = None
    user_transcript: str | None = None
    component_timings_ms: dict[str, float] = field(default_factory=dict)
    session_metadata: dict[str, Any] = field(default_factory=dict)


class LiveKitTurnClient(Protocol):
    def run_turn(self, user: str) -> LiveKitTurnObservation: ...


class LiveKitEventCollector:
    """Collect the supported public ``AgentSession`` events without owning it.

    Call ``attach(session)`` after constructing the session, then ``finish_turn``
    after the assistant turn is committed. Component metrics can be forwarded
    from each configured plugin with ``record_component_metric``.
    """

    def __init__(self, session_metadata: Mapping[str, Any] | None = None) -> None:
        self._events: list[dict[str, Any]] = []
        self._session_metadata = dict(session_metadata or {})

    def attach(self, session: Any) -> None:
        session.on("user_input_transcribed")(self._on_user_transcript)
        session.on("conversation_item_added")(self._on_conversation_item)
        session.on("function_tools_executed")(self._on_tools)

    def _on_user_transcript(self, event: Any) -> None:
        self._events.append(
            {
                "type": "user_input_transcribed",
                "transcript": event.transcript,
                "is_final": event.is_final,
            }
        )

    def _on_conversation_item(self, event: Any) -> None:
        item = event.item
        metrics = getattr(item, "metrics", None)
        e2e_seconds = _metric_value(metrics, "e2e_latency")
        llm_ttft_seconds = _metric_value(metrics, "llm_node_ttft")
        tts_ttfb_seconds = _metric_value(metrics, "tts_node_ttfb")
        role = getattr(item.role, "value", item.role)
        self._events.append(
            {
                "type": "conversation_item_added",
                "role": str(role),
                "text": getattr(item, "text_content", ""),
                "metrics": {
                    "e2e_latency_ms": e2e_seconds * 1000
                    if e2e_seconds is not None
                    else None
                },
            }
        )
        if str(role) == "assistant":
            if llm_ttft_seconds is not None:
                self.record_component_metric("llm_ttft", llm_ttft_seconds * 1000)
            if tts_ttfb_seconds is not None:
                self.record_component_metric("tts_ttfb", tts_ttfb_seconds * 1000)

    def _on_tools(self, event: Any) -> None:
        calls = []
        for call in getattr(event, "function_calls", []):
            calls.append(
                {
                    "name": getattr(call, "name", getattr(call, "function_name", "unknown")),
                    "arguments": getattr(call, "arguments", {}) or {},
                }
            )
        self._events.append({"type": "function_tools_executed", "function_calls": calls})

    def record_component_metric(self, name: str, duration_ms: float) -> None:
        self._events.append(
            {"type": "component_metric", "name": name, "duration_ms": duration_ms}
        )

    def finish_turn(self) -> LiveKitTurnObservation:
        observation = observation_from_events(
            self._events, session_metadata=self._session_metadata
        )
        self._events = []
        return observation


def _metric_value(metrics: Any, name: str) -> float | None:
    """Read current mapping metrics and older attribute-style SDK objects."""

    if metrics is None:
        return None
    if isinstance(metrics, Mapping):
        value = metrics.get(name)
    else:
        value = getattr(metrics, name, None)
    return float(value) if value is not None else None


class LiveKitAdapter(VoicePipelineAdapter):
    """Evaluate an existing LiveKit Agents session through an injected client.

    LiveKit apps choose their own rooms, models, credentials, and lifecycle, so
    this adapter deliberately does not construct an ``AgentSession``. Supply a
    client that drives one turn and returns the SDK events/metrics it observed,
    either directly or through ``VOICE_EVAL_LIVEKIT_CLIENT=module:factory``.
    """

    name = "livekit"

    def __init__(self, client: LiveKitTurnClient | None = None) -> None:
        self.client = client or _load_configured_client()

    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        if audio_dir is not None:
            raise ValueError(
                "The LiveKit adapter does not export audio artifacts. Capture audio in "
                "your LiveKit session and run without --audio."
            )

        results: list[TurnResult] = []
        for turn in scenario.turns:
            started = perf_counter()
            observed = self.client.run_turn(turn.user)
            elapsed_ms = (perf_counter() - started) * 1000
            if not isinstance(observed, LiveKitTurnObservation):
                raise TypeError("LiveKit client.run_turn() must return LiveKitTurnObservation")
            results.append(
                TurnResult(
                    user=observed.user_transcript or turn.user,
                    assistant=observed.assistant,
                    latency_ms=observed.latency_ms if observed.latency_ms is not None else elapsed_ms,
                    tool_calls=observed.tool_calls,
                    component_timings_ms=observed.component_timings_ms,
                    session_metadata=observed.session_metadata,
                )
            )
        return results


def _load_configured_client() -> LiveKitTurnClient:
    target = os.getenv("VOICE_EVAL_LIVEKIT_CLIENT")
    if not target:
        try:
            importlib.import_module("livekit.agents")
        except ImportError as exc:
            raise RuntimeError(
                "LiveKit support is optional. Install it with "
                "`pip install 'voice-agent-eval-lab[livekit]'`, then set "
                "VOICE_EVAL_LIVEKIT_CLIENT=your_module:factory."
            ) from exc
        raise RuntimeError(
            "Set VOICE_EVAL_LIVEKIT_CLIENT=your_module:factory to a factory that "
            "returns a LiveKitTurnClient connected to your configured AgentSession."
        )

    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise RuntimeError(
            "VOICE_EVAL_LIVEKIT_CLIENT must use the form `python_module:factory`."
        )
    try:
        factory: Callable[[], LiveKitTurnClient] = getattr(
            importlib.import_module(module_name), attribute
        )
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"Could not load LiveKit client factory {target!r}: {exc}") from exc
    client = factory()
    if not callable(getattr(client, "run_turn", None)):
        raise RuntimeError(f"LiveKit client factory {target!r} did not return a run_turn client")
    return client


def observation_from_events(
    events: list[Mapping[str, Any]], *, session_metadata: Mapping[str, Any] | None = None
) -> LiveKitTurnObservation:
    """Normalize captured LiveKit Agents event records into one turn.

    This small event seam makes production collectors and offline fixtures use
    identical normalization. Expected record ``type`` values are
    ``user_input_transcribed``, ``conversation_item_added``,
    ``function_tools_executed``, and ``component_metric``.
    """

    user_transcript: str | None = None
    assistant = ""
    latency_ms: float | None = None
    tools: list[ToolCall] = []
    timings: dict[str, float] = {}
    metadata = dict(session_metadata or {})
    for event in events:
        kind = event.get("type")
        if kind == "user_input_transcribed" and event.get("is_final", True):
            user_transcript = str(event.get("transcript", ""))
        elif kind == "conversation_item_added" and event.get("role") == "assistant":
            assistant = str(event.get("text", ""))
            metrics = event.get("metrics") or {}
            if metrics.get("e2e_latency_ms") is not None:
                latency_ms = float(metrics["e2e_latency_ms"])
        elif kind == "function_tools_executed":
            for call in event.get("function_calls", []):
                tools.append(
                    ToolCall(name=str(call["name"]), arguments=dict(call.get("arguments") or {}))
                )
        elif kind == "component_metric":
            name = str(event["name"])
            timings[name] = float(event["duration_ms"])
        elif kind == "session_metadata":
            metadata.update(dict(event.get("values") or {}))
    return LiveKitTurnObservation(
        assistant=assistant,
        tool_calls=tools,
        latency_ms=latency_ms,
        user_transcript=user_transcript,
        component_timings_ms=timings,
        session_metadata=metadata,
    )
