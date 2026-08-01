# ElevenLabs adapter

Adapter for [ElevenLabs Conversational AI](https://elevenlabs.io/docs/conversational-ai)
agents. Install the optional dependency:

```bash
pip install 'voice-agent-eval-lab[elevenlabs]'
```

## Environment variables

| Variable | Purpose |
|---|---|
| `ELEVENLABS_API_KEY` | ElevenLabs API key (`xi-api-key` header), used to fetch a signed conversation URL |
| `ELEVENLABS_AGENT_ID` | The Conversational AI agent to evaluate |
| `VOICE_EVAL_ELEVENLABS_CLIENT` | Optional `module:factory` override that returns a pre-built `ElevenLabsConversationClient`, bypassing the two variables above |

`voice-eval run --adapter elevenlabs` without any of these set fails with a
clear `RuntimeError` naming the missing variable or package — never a stack
trace from a failed import or a raw HTTP error.

## How it works

Voice Eval does not create or configure your ElevenLabs agent: the agent,
its prompt, voice, and tools belong to your ElevenLabs dashboard/API
configuration. `ElevenLabsAdapter` drives an existing agent over its
WebSocket API (`wss://api.elevenlabs.io/v1/convai/conversation`), sending
each scripted scenario turn as a `user_message` client event and collecting
the resulting `agent_response`, `client_tool_call`, and `audio` server
events for one `TurnResult` per turn.

For CLI or API processes, you can bypass the built-in WebSocket client
entirely and supply your own:

```bash
export VOICE_EVAL_ELEVENLABS_CLIENT=my_module:create_client
```

`create_client()` must return an object with a
`send_user_message(text) -> ElevenLabsTurnObservation` method.

`observation_from_events()` normalizes raw WebSocket event records (as
listed in ElevenLabs' [client-to-server](https://elevenlabs.io/docs/eleven-agents/customization/events/client-to-server-events)
and [server-to-client](https://elevenlabs.io/docs/eleven-agents/customization/events/client-events)
event references) into an `ElevenLabsTurnObservation`, so a production event
collector and offline test fixtures share identical normalization.

## What's real vs mocked in tests

`tests/test_elevenlabs_adapter.py` never touches the network. It injects a
fake `send_user_message` client directly into `ElevenLabsAdapter` (mirroring
`LiveKitAdapter`'s test pattern) and separately unit-tests
`observation_from_events()` against literal event dictionaries shaped like
ElevenLabs' documented protocol. The only network-capable code path,
`WebSocketElevenLabsClient` in `src/voice_agent_eval_lab/_elevenlabs_ws_client.py`,
is imported lazily and only reached when real credentials are present and no
client/override was supplied — it is not imported or exercised by the
default test suite.

## Audio

If the WebSocket session streams `audio` events, the adapter decodes and
writes the assistant's real PCM16 audio as a WAV file under `audio_dir`. If
no audio was captured (for example, a text-only fake client in tests), the
adapter falls back to the same deterministic offline synthesizer
(`audio.synth_speech`) the mock `cascade`/`realtime` adapters use, so
`--audio` always produces a valid, playable WAV either way.

## Example

```bash
export ELEVENLABS_API_KEY=...
export ELEVENLABS_AGENT_ID=...
voice-eval run --scenario basic_booking --adapter elevenlabs
```
