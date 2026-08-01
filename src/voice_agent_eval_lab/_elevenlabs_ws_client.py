"""Real ElevenLabs Conversational AI WebSocket client.

This module is only imported when no test double is injected into
``ElevenLabsAdapter`` and no ``VOICE_EVAL_ELEVENLABS_CLIENT`` override is set,
i.e. when actually talking to the live API with real credentials. It is never
imported by the default test suite, so the ``websockets`` dependency stays
optional (see the ``elevenlabs`` extra in ``pyproject.toml``).

Protocol reference: wss://api.elevenlabs.io/v1/convai/conversation
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from .elevenlabs_adapter import ElevenLabsTurnObservation, observation_from_events

_SIGNED_URL_ENDPOINT = "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"
_DIRECT_URL_TEMPLATE = "wss://api.elevenlabs.io/v1/convai/conversation?agent_id={agent_id}"


class WebSocketElevenLabsClient:
    """Drives one ElevenLabs Conversational AI session over its WebSocket API.

    Each ``send_user_message`` call sends a ``user_message`` client event and
    collects server events (``agent_response``, ``client_tool_call``,
    ``audio``, ...) until the agent's reply is complete, then normalizes them
    with ``observation_from_events``.
    """

    def __init__(self, api_key: str, agent_id: str) -> None:
        self._api_key = api_key
        self._agent_id = agent_id
        self._conn: Any = None

    def _signed_url(self) -> str:
        request = urllib.request.Request(
            f"{_SIGNED_URL_ENDPOINT}?agent_id={self._agent_id}",
            headers={"xi-api-key": self._api_key},
        )
        with urllib.request.urlopen(request) as response:  # noqa: S310 - documented HTTPS API
            payload = json.loads(response.read())
        return str(payload["signed_url"])

    def _connection(self) -> Any:
        if self._conn is None:
            import websockets.sync.client as ws_client

            self._conn = ws_client.connect(self._signed_url())
        return self._conn

    def send_user_message(self, text: str) -> ElevenLabsTurnObservation:
        conn = self._connection()
        conn.send(json.dumps({"type": "user_message", "text": text}))

        events: list[dict[str, Any]] = []
        while True:
            raw = conn.recv()
            event = json.loads(raw)
            events.append(event)
            if event.get("type") == "ping":
                conn.send(json.dumps({"type": "pong", "event_id": event.get("ping_event", {}).get("event_id")}))
                continue
            if event.get("type") == "agent_response":
                break
        return observation_from_events(events)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
