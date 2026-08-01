# Pipecat adapter

[Pipecat](https://github.com/pipecat-ai/pipecat) is an open-source Python
framework for building real-time voice/multimodal agent pipelines. Unlike the
hosted-API adapters in this project (ElevenLabs, Vapi, and similar), Pipecat
is not a vendor you call over HTTP — it is a framework you self-host and
compose locally: you wire your own STT, LLM, and TTS services (and their API
keys) into a `Pipeline` and run it as a `PipelineTask`, with frame processors
and event handlers of your choosing.

Because of that, this adapter mirrors the LiveKit adapter's approach rather
than a hosted-vendor adapter's: Voice Eval does not construct your
`PipelineTask`. Your application owns the pipeline topology, the services,
the credentials, and the lifecycle. Provide a small client with a
`run_turn(user)` method that returns `PipecatTurnObservation`, then construct
`PipecatAdapter(client)`.

Install the optional dependency only if you need it for typing/imports in
your own client code — the adapter itself has no required dependency on
`pipecat-ai`:

```bash
pip install 'voice-agent-eval-lab[pipecat]'
```

For CLI or API processes, expose a zero-argument factory and configure it:

```bash
export VOICE_EVAL_PIPECAT_CLIENT=my_agent.eval_client:create_client
```

`PipecatAdapter(client)` then drives one `run_turn(user)` call per scripted
turn and converts the returned `PipecatTurnObservation` into a `TurnResult`.

The observation can include the final user and assistant transcripts, any
tool/function calls executed during the turn, end-to-end latency, per-frame
processor component timings, and session metadata:

```python
from voice_agent_eval_lab.pipecat_adapter import PipecatTurnObservation, PipecatTurnClient

class MyPipecatClient:
    """Wraps an already-wired Pipecat PipelineTask."""

    def run_turn(self, user: str) -> PipecatTurnObservation:
        # Push a user frame into your PipelineTask, wait for the assistant's
        # response frame, and read whatever metrics your STT/LLM/TTS
        # processors expose (Pipecat commonly reports these as per-processor
        # metrics frames).
        ...
        return PipecatTurnObservation(
            user_transcript=user,
            assistant="Your booking is cancelled.",
            tool_calls=[...],
            latency_ms=420,
            component_timings_ms={"stt": 80, "llm_ttft": 210, "tts_ttfb": 90},
            session_metadata={"pipeline": "booking-agent-v1"},
        )
```

Only include metrics your pipeline actually exposes; absent ones are simply
left out of `component_timings_ms`.

If no client is supplied and `VOICE_EVAL_PIPECAT_CLIENT` is unset, the
adapter raises a clear `RuntimeError` (never a stack trace) explaining how to
wire one up.

The adapter does not currently export audio. Capture audio artifacts inside
your Pipecat pipeline (for example with a recording frame processor) and run
this adapter without the `--audio` option:

```bash
voice-eval run --scenario basic_booking --adapter pipecat
```
