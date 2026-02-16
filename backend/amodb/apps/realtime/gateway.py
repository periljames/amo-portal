from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import msgpack

from . import schemas

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional dependency in dev
    mqtt = None


class RealtimeGateway:
    def __init__(self) -> None:
        self.enabled = os.getenv("REALTIME_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self.internal_url = os.getenv("MQTT_BROKER_INTERNAL_URL", "")
        self._client = None
        self._connected = False

    def connect(self) -> None:
        if not self.enabled or not mqtt or not self.internal_url:
            return
        if self._client:
            return
        self._client = mqtt.Client(protocol=mqtt.MQTTv311)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.connect_async(self._host(), self._port(), keepalive=30)
        self._client.loop_start()

    def _host(self) -> str:
        return self.internal_url.split("://", 1)[-1].split(":", 1)[0]

    def _port(self) -> int:
        value = self.internal_url.split(":")[-1]
        return int(value) if value.isdigit() else 1883

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        self._connected = rc == 0
        logger.info("mqtt connected", extra={"mqtt_connects": 1, "rc": rc})

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self._connected = False
        logger.warning("mqtt disconnected", extra={"mqtt_disconnects": 1, "rc": rc})

    def publish(self, *, topic: str, envelope: schemas.RealtimeEnvelope, qos: int = 0, retain: bool = False) -> None:
        if not self.enabled:
            return
        payload = msgpack.packb(envelope.model_dump(mode="python"), use_bin_type=True)
        if not self._client or not self._connected:
            raise RuntimeError("Broker not connected")
        result = self._client.publish(topic, payload=payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Broker publish failed: {result.rc}")

    def parse(self, payload: bytes) -> schemas.RealtimeEnvelope:
        data = msgpack.unpackb(payload, raw=False, strict_map_key=False)
        return schemas.RealtimeEnvelope.model_validate(data)

    def health(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "connected": self._connected,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


gateway = RealtimeGateway()
