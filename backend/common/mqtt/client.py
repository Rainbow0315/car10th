from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Optional

import paho.mqtt.client as mqtt

from common.config.settings import settings

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, dict[str, Any]], None]


class MqttManager:
    """paho-mqtt 封装：后台线程维护连接，供 web_api 发布/订阅。"""

    def __init__(self) -> None:
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.Lock()
        self._message_handler: Optional[MessageHandler] = None
        self._last_error: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._message_handler = handler

    def start(self, subscribe_topics: list[str] | None = None) -> None:
        if self._client is not None:
            return

        subscribe_topics = subscribe_topics or []

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
            clean_session=True,
        )
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        self._client = client
        self._subscribe_topics = subscribe_topics

        try:
            client.connect(
                settings.mqtt_broker_host,
                settings.mqtt_broker_port,
                keepalive=settings.mqtt_keepalive,
            )
            client.loop_start()
            logger.info(
                "MQTT connecting to %s:%s",
                settings.mqtt_broker_host,
                settings.mqtt_broker_port,
            )
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("MQTT connect failed: %s", exc)

    def stop(self) -> None:
        with self._lock:
            if self._client is None:
                return
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                logger.exception("MQTT disconnect error")
            finally:
                self._client = None
                self._connected = False

    def publish_json(
        self,
        topic: str,
        payload: dict[str, Any],
        qos: int = 1,
        retain: bool = False,
    ) -> bool:
        with self._lock:
            if not self._client or not self._connected:
                self._last_error = "MQTT not connected"
                return False
            try:
                result = self._client.publish(
                    topic,
                    json.dumps(payload, ensure_ascii=False),
                    qos=qos,
                    retain=retain,
                )
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    self._last_error = f"publish failed rc={result.rc}"
                    return False
                return True
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("MQTT publish error topic=%s", topic)
                return False

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: Any = None,
    ) -> None:
        if reason_code.is_failure:
            self._connected = False
            self._last_error = f"connect failed: {reason_code}"
            logger.error("MQTT connect failed: %s", reason_code)
            return

        self._connected = True
        self._last_error = None
        logger.info("MQTT connected")

        for topic in getattr(self, "_subscribe_topics", []):
            client.subscribe(topic, qos=1)
            logger.info("MQTT subscribed: %s", topic)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: Any = None,
    ) -> None:
        self._connected = False
        if not reason_code.is_failure:
            logger.info("MQTT disconnected")
        else:
            self._last_error = f"disconnect: {reason_code}"
            logger.warning("MQTT unexpected disconnect: %s", reason_code)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        topic = message.topic
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                payload = {"value": payload}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Invalid MQTT JSON on %s: %s", topic, exc)
            return

        handler = self._message_handler
        if handler is None:
            logger.warning("No MQTT handler for topic %s", topic)
            return

        try:
            handler(topic, payload)
        except Exception:
            logger.exception("MQTT handler error topic=%s", topic)


mqtt_manager = MqttManager()
