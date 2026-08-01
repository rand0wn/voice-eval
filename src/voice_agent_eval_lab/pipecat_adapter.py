from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Protocol

from .adapters import VoicePipelineAdapter
from .models import Scenario, ToolCall, TurnResult


@dataclass
class PipecatTurnObservation:
    """Provider-neutral snapshot returned by a Pipecat pipeline client.

    Timings are milliseconds. ``component_timings_ms`` can contain the
    per-processor metrics exposed by the configured Pipecat pipeline (for
    example ``stt``, ``llm_ttft`` and ``tts_ttfb``); absent metrics are left
    absent.
    """

    assistant: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float | None = None
    user_transcript: str | None = None
    component_timings_ms: dict[str, float] = field(default_factory=dict)
    session_metadata: dict[str, Any] = field(default_factory=dict)


class PipecatTurnClient(Protocol):
    def run_turn(self, user: str) -> PipecatTurnObservation: ...


class PipecatAdapter(VoicePipelineAdapter):
    """Evaluate an existing Pipecat pipeline through an injected client.

    Pipecat is a self-hosted framework, not a hosted vendor API: applications
    compose their own STT/LLM/TTS services into a ``Pipeline``/``PipelineTask``
    with whatever frame processors and event handlers they choose. This
    adapter therefore does not construct a pipeline itself. Supply a client
    that drives one turn of your already-wired ``PipelineTask`` and returns
    the frames/metrics it observed, either directly or through
    ``VOICE_EVAL_PIPECAT_CLIENT=module:factory``.
    """

    name = "pipecat"

    def __init__(self, client: PipecatTurnClient | None = None) -> None:
        self.client = client or _load_configured_client()

    def execute(self, scenario: Scenario, audio_dir: Path | None = None) -> list[TurnResult]:
        if audio_dir is not None:
            raise ValueError(
                "The Pipecat adapter does not export audio artifacts. Capture audio in "
                "your Pipecat pipeline (for example a recording processor) and run "
                "without --audio."
            )

        results: list[TurnResult] = []
        for turn in scenario.turns:
            started = perf_counter()
            observed = self.client.run_turn(turn.user)
            elapsed_ms = (perf_counter() - started) * 1000
            if not isinstance(observed, PipecatTurnObservation):
                raise TypeError(
                    "Pipecat client.run_turn() must return PipecatTurnObservation"
                )
            results.append(
                TurnResult(
                    user=observed.user_transcript or turn.user,
                    assistant=observed.assistant,
                    latency_ms=observed.latency_ms
                    if observed.latency_ms is not None
                    else elapsed_ms,
                    tool_calls=observed.tool_calls,
                    component_timings_ms=observed.component_timings_ms,
                    session_metadata=observed.session_metadata,
                )
            )
        return results


def _load_configured_client() -> PipecatTurnClient:
    target = os.getenv("VOICE_EVAL_PIPECAT_CLIENT")
    if not target:
        try:
            importlib.import_module("pipecat")
        except ImportError as exc:
            raise RuntimeError(
                "Pipecat support requires you to wire your own pipeline. Install "
                "the framework with `pip install 'voice-agent-eval-lab[pipecat]'`, "
                "build a PipelineTask with your chosen STT/LLM/TTS services, wrap "
                "it in a PipecatTurnClient, and set "
                "VOICE_EVAL_PIPECAT_CLIENT=your_module:factory."
            ) from exc
        raise RuntimeError(
            "Set VOICE_EVAL_PIPECAT_CLIENT=your_module:factory to a factory that "
            "returns a PipecatTurnClient wrapping your configured PipelineTask."
        )

    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise RuntimeError(
            "VOICE_EVAL_PIPECAT_CLIENT must use the form `python_module:factory`."
        )
    try:
        factory: Callable[[], PipecatTurnClient] = getattr(
            importlib.import_module(module_name), attribute
        )
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"Could not load Pipecat client factory {target!r}: {exc}") from exc
    client = factory()
    if not callable(getattr(client, "run_turn", None)):
        raise RuntimeError(f"Pipecat client factory {target!r} did not return a run_turn client")
    return client
