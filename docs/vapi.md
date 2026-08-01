# Vapi adapter

No optional SDK install is required: the built-in real client uses only the
Python standard library (`urllib`).

```bash
python -m pip install -e ".[dev]"
```

Voice Eval does not create your Vapi assistant, phone number, or call: those
belong to your [Vapi dashboard](https://dashboard.vapi.ai) configuration.
Provide a small client with a `run_turn(user)` method that returns
`VapiTurnObservation`, then construct `VapiAdapter(client)`.

## Environment variables

- `VAPI_API_KEY` — a Vapi private API key.
- `VAPI_ASSISTANT_ID` — the assistant to converse with.

If both are set (and `VOICE_EVAL_VAPI_CLIENT` is not), `VapiAdapter()` builds a
best-effort `VapiHTTPClient` that posts each scripted turn to Vapi's Chat API
(`POST https://api.vapi.ai/chat`), chaining `previousChatId` across turns in
the same scenario, and parses the assistant reply plus any executed function
calls out of the response. If credentials are missing, the adapter raises a
clear `RuntimeError` naming the missing variables instead of crashing.

For CLI or API processes, you can instead expose a zero-argument factory and
configure it directly:

```bash
export VOICE_EVAL_VAPI_CLIENT=my_agent.eval_client:create_client
```

`VOICE_EVAL_VAPI_CLIENT` takes precedence over `VAPI_API_KEY`/`VAPI_ASSISTANT_ID`,
so use it if you want to drive a real Vapi call/session yourself (for example
through Vapi's `/call` REST endpoint and its websocket/webhook event stream for
`transcript`, `function-call`, and `speech-update` events) and just hand the
adapter the resulting per-turn observation.

## What's real vs mocked in tests

`tests/test_vapi_adapter.py` always injects a fake `VapiTurnClient` and never
constructs `VapiHTTPClient` or reaches the network — this keeps the default
test suite network-free per `CONTRIBUTING.md`. `VapiHTTPClient` itself is only
exercised when you actually run the adapter with real credentials.

The adapter's injected client returns text signals only (transcript, tool
calls, latency); it does not currently return Vapi's raw call audio. When
`audio_dir` is set, the adapter synthesizes placeholder per-turn WAV files
with `audio.synth_speech`, the same tone-based fixture the built-in mock
adapters use, so every turn still gets a playable artifact even though it is
not the pipeline's actual TTS output.

## Example

```bash
export VAPI_API_KEY=sk_live_...
export VAPI_ASSISTANT_ID=asst_...
voice-eval run --scenario basic_booking --adapter vapi
```

Without credentials or `VOICE_EVAL_VAPI_CLIENT` configured, the same command
fails fast with a `RuntimeError` naming `VAPI_API_KEY`/`VAPI_ASSISTANT_ID`
rather than a stack trace from a missing import or network call.
