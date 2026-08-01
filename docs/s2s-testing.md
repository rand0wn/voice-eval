# Native speech-to-speech (S2S) testing

Text mode (the default) drives a pipeline with `turn.user` as a string and
grades the text/tool-calls it returns. That works for cascaded pipelines
(STT -> LLM -> TTS) and for anything that exposes intermediate text, but a
native speech-to-speech pipeline (OpenAI Realtime, ElevenLabs Conversational
AI, Vapi, Pipecat, and similar) may never produce text at all — audio goes in,
audio comes out. S2S mode drives and grades that path directly: it
synthesizes `turn.user` to a WAV, hands the WAV to the adapter, and grades the
adapter's returned audio (and, if it reports one, a transcript alongside it).

## When to use it

- **Text mode** (`--audio-mode text`, the default): your adapter's pipeline
  is cascaded, or otherwise exposes text you can grade directly. This is
  almost always the right default — text-shape rules (required phrases,
  question/sentence limits) are strictly more informative than audio-only
  signals when text is available.
- **S2S mode** (`--audio-mode s2s`): your adapter wraps a native
  speech-to-speech pipeline that has no intermediate text, or you specifically
  want to exercise/grade the audio path itself (e.g. confirm the pipeline
  actually produces a playable response within a latency budget).

## Running it

```bash
voice-eval run --scenario basic_booking --adapter mock-s2s --audio-mode s2s
```

S2S mode always synthesizes and writes audio artifacts — there's nothing else
to grade a native pipeline from — so `reports/audio/<run-id>/tNN_user.wav` and
`tNN_bot.wav` are written even without passing `--audio`. `compare` and
`suite` accept the same flag.

`mock-s2s` is an offline demo adapter (no network, no credentials) that
mirrors the existing `cascade`/`realtime`/`degraded` mocks, so you can see the
full workflow before wiring up a real provider.

## The contract

The extension point lives in `src/voice_agent_eval_lab/s2s.py`, mirroring the
`LiveKitTurnObservation`/`LiveKitTurnClient` pattern in `livekit_adapter.py`:

- **`S2STurnObservation`** — what one turn from a native S2S pipeline looks
  like: `assistant_transcript` (optional — `None` when the pipeline doesn't
  expose one), `tool_calls`, `time_to_first_audio_byte_ms`,
  `assistant_audio_ms`, and the assistant's audio as either `audio_bytes` or
  `audio_path`. Every field except the audio itself is optional and defaults
  to "unavailable" so partial pipelines still work.
- **`S2SClient`** — a `Protocol` with one method, `run_turn(user_audio_path)
  -> S2STurnObservation`, for wrapping an existing session/streaming client
  without subclassing anything.
- **`S2SPipelineAdapter`** — a `VoicePipelineAdapter` base class. Subclass it
  and implement `run_turn(self, user_audio_path: Path) ->
  S2STurnObservation`; the base class's `execute()` handles synthesizing
  `turn.user` to a WAV via `audio.synth_speech`, timing the round trip,
  writing the returned audio under `audio_dir` (same `tNN_user.wav` /
  `tNN_bot.wav` layout as every other adapter), and building the
  `TurnResult`. It sets `supports_s2s = True`, which is how the runner
  validates `--audio-mode s2s` against an adapter without branching on
  adapter type.

```python
from pathlib import Path
from voice_agent_eval_lab.s2s import S2SPipelineAdapter, S2STurnObservation

class MyRealtimeAdapter(S2SPipelineAdapter):
    name = "my-realtime"

    def run_turn(self, user_audio_path: Path) -> S2STurnObservation:
        # Send the WAV at user_audio_path into your realtime session,
        # collect the assistant's audio (and transcript/tool-calls, if any).
        audio_bytes, transcript, tools, ttfb_ms, duration_ms = self._drive(user_audio_path)
        return S2STurnObservation(
            assistant_transcript=transcript,  # or None if unavailable
            tool_calls=tools,
            time_to_first_audio_byte_ms=ttfb_ms,
            assistant_audio_ms=duration_ms,
            audio_bytes=audio_bytes,
        )
```

Register it like any other adapter: `register_adapter("my-realtime",
MyRealtimeAdapter)` or a `voice_agent_eval_lab.adapters` entry point (see
[adapter-plugins.md](adapter-plugins.md)). Nothing in `runner.py`, the CLI, or
`grading.py` needs to know your adapter exists.

## Grading in S2S mode

`grading.py` adds two rules that apply whenever a turn carries assistant
audio (in either mode):

- **`assistant_audio_playable`** — the turn's `assistant_audio_path` must
  point at a WAV file that actually contains sample data (more than a bare
  44-byte header). This is the audio-mode equivalent of "did it respond".
- **`time_to_first_audio_byte_budget`** — only checked when the scenario sets
  `max_time_to_first_audio_byte_ms` and the turn reports
  `time_to_first_audio_byte_ms`; fails when the observed value exceeds the
  budget.

When a turn has assistant audio but **no** transcript (`assistant_transcript`
was `None` or empty), the text-shape rules that need text to evaluate
(`must_include_phrase`, `max_questions_per_turn`, `max_sentences_per_turn`,
`non_empty_transcript`) are skipped for that turn rather than auto-failing —
grading falls back to what audio can actually tell you: tool calls, latency,
and the two audio rules above. When a transcript **is** available, every
existing text rule applies exactly as it does in text mode, so a pipeline
that reports one gets full text-based grading for free.

## Limitations

- `audio.synth_speech` is still a deterministic tone-based fixture, not real
  TTS (see the README's "Swap the audio synthesis for real TTS" section) — a
  real adapter sends that tone WAV into the pipeline unless you swap the
  synthesizer for real speech.
- S2S mode requires an audio directory; there is no text-only variant of it
  by design.
