# LiveKit adapter

Install the optional SDK dependency:

```bash
pip install 'voice-agent-eval-lab[livekit]'
```

Voice Eval does not create your `AgentSession`: the room, models, credentials,
and lifecycle belong to your application. Provide a small client with a
`run_turn(user)` method that returns `LiveKitTurnObservation`, then construct
`LiveKitAdapter(client)`.

For CLI or API processes, expose a zero-argument factory and configure it:

```bash
export VOICE_EVAL_LIVEKIT_CLIENT=my_agent.eval_client:create_client
```

The observation can include the final user and assistant transcripts, executed
function calls, end-to-end latency, component timings, and session metadata.
Only include metrics your pipeline actually exposes. LiveKit's current Python
SDK surfaces final user transcripts through `user_input_transcribed`, messages
and per-turn latency through `conversation_item_added`/`ChatMessage.metrics`,
tool calls through `function_tools_executed`, and component metrics from the
individual STT, LLM, and TTS plugins.

`observation_from_events()` normalizes simple event records and is useful for
keeping a production collector easy to test with offline fixtures.
`LiveKitEventCollector.attach(session)` provides the corresponding event hook
for an existing `AgentSession`; forward any per-plugin timing values with
`record_component_metric()` and call `finish_turn()` after the assistant message
is committed.

The adapter does not currently export audio or make claims about interruption
testing. Capture those artifacts in LiveKit itself and run this adapter without
the audio option.
