from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

import msgpack

from amodb.database import WriteSessionLocal

from . import messaging, models, schemas

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional dependency in development
    mqtt = None


class RealtimeGateway:
    def __init__(self) -> None:
        self.enabled = os.getenv("REALTIME_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self.internal_url = os.getenv("MQTT_BROKER_INTERNAL_URL", "")
        self._client = None
        self._connected = False
        self._stop = threading.Event()
        self._drain_thread: threading.Thread | None = None
        self._flush_lock = threading.Lock()

    def connect(self) -> None:
        if not self.enabled or not mqtt or not self.internal_url:
            return
        if self._client:
            return
        self._stop.clear()
        self._client = mqtt.Client(protocol=mqtt.MQTTv311)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.connect_async(self._host(), self._port(), keepalive=30)
        self._client.loop_start()
        self._start_drain_thread()

    def _host(self) -> str:
        return self.internal_url.split("://", 1)[-1].split(":", 1)[0]

    def _port(self) -> int:
        value = self.internal_url.split(":")[-1]
        return int(value) if value.isdigit() else 1883

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        self._connected = rc == 0
        if self._connected:
            client.subscribe("amo/+/user/+/outbox", qos=1)
            self.flush_pending()
        logger.info("mqtt connected", extra={"mqtt_connects": 1, "rc": rc})

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self._connected = False
        logger.warning("mqtt disconnected", extra={"mqtt_disconnects": 1, "rc": rc})

    def _on_message(self, client, userdata, message) -> None:
        topic = str(getattr(message, "topic", ""))
        parts = topic.split("/")
        if len(parts) != 5 or parts[0] != "amo" or parts[2] != "user" or parts[4] != "outbox":
            logger.warning("Rejected realtime message on unexpected topic", extra={"topic": topic})
            return
        amo_id, user_id = parts[1], parts[3]
        db = WriteSessionLocal()
        try:
            envelope = self.parse(bytes(message.payload))
            if envelope.amoId != amo_id or envelope.userId != user_id:
                raise ValueError("Realtime topic identity does not match the signed envelope")
            messaging.process_inbound_envelope(db, envelope)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to process inbound realtime message", extra={"topic": topic})
        finally:
            db.close()
        self.flush_pending()

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

    def flush_pending(self, *, limit: int = 200) -> int:
        if not self.enabled or not self._connected or not self._client:
            return 0
        if not self._flush_lock.acquire(blocking=False):
            return 0
        published = 0
        db = WriteSessionLocal()
        try:
            rows = (
                db.query(models.RealtimeOutbox)
                .filter(models.RealtimeOutbox.published_at.is_(None))
                .order_by(models.RealtimeOutbox.created_at.asc(), models.RealtimeOutbox.id.asc())
                .limit(max(1, min(limit, 1000)))
                .all()
            )
            for row in rows:
                try:
                    envelope = self.parse(row.payload_bin)
                    self.publish(topic=row.topic, envelope=envelope, qos=1)
                    row.published_at = datetime.now(timezone.utc)
                    row.last_error = None
                    published += 1
                except Exception as exc:
                    row.retry_count = int(row.retry_count or 0) + 1
                    row.last_error = str(exc)[:2000]
                    logger.warning("Realtime outbox delivery failed", extra={"outbox_id": row.id, "topic": row.topic})
                    break
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Realtime outbox drain failed")
        finally:
            db.close()
            self._flush_lock.release()
        return published

    def _start_drain_thread(self) -> None:
        if self._drain_thread and self._drain_thread.is_alive():
            return

        def _drain() -> None:
            while not self._stop.wait(1.0):
                if self._connected:
                    self.flush_pending()

        self._drain_thread = threading.Thread(target=_drain, name="realtime-outbox-drain", daemon=True)
        self._drain_thread.start()

    def disconnect(self) -> None:
        client = self._client
        self._client = None
        self._connected = False
        self._stop.set()
        if self._drain_thread and self._drain_thread.is_alive():
            self._drain_thread.join(timeout=2)
        self._drain_thread = None
        if not client:
            return
        try:
            try:
                client.loop_stop(force=True)
            except TypeError:
                client.loop_stop()
        except Exception:
            logger.debug("mqtt loop_stop failed during shutdown", exc_info=True)
        try:
            client.disconnect()
        except Exception:
            logger.debug("mqtt disconnect failed during shutdown", exc_info=True)

    def health(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "connected": self._connected,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


gateway = RealtimeGateway()
