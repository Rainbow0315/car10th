from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from apps.web_api.services.robot_service import robot_service
from common.config.settings import settings
from common.mqtt import APP_CONTROL_SUBSCRIBE, ALARM_NOTIFY, mqtt_manager, robot_status_topic
from common.schemas.robot import AlarmNotifyPayload, MqttHealthResponse, RobotControlRequest, RobotStatusPayload
from common.utils.operation_log import write_operation_log

logger = logging.getLogger(__name__)


class MqttService:
    def __init__(self) -> None:
        self._heartbeat_task: asyncio.Task | None = None

    def start(self) -> None:
        mqtt_manager.set_message_handler(self.handle_message)
        mqtt_manager.start(subscribe_topics=[APP_CONTROL_SUBSCRIBE])
        logger.info("MQTT service started")

    async def start_heartbeat(self) -> None:
        if self._heartbeat_task is not None:
            return
        self._heartbeat_task = asyncio.create_task(self._status_heartbeat_loop())

    async def stop(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        mqtt_manager.stop()
        logger.info("MQTT service stopped")

    def health(self) -> MqttHealthResponse:
        return MqttHealthResponse(
            connected=mqtt_manager.is_connected,
            broker=f"{settings.mqtt_broker_host}:{settings.mqtt_broker_port}",
            client_id=settings.mqtt_client_id,
            last_error=mqtt_manager.last_error,
        )

    def handle_message(self, topic: str, payload: dict[str, Any]) -> None:
        robot_code = robot_service.parse_control_topic(topic)
        if robot_code is None:
            logger.warning("Ignored MQTT topic: %s", topic)
            return

        command = str(payload.get("command", "")).strip()
        if not command:
            logger.warning("MQTT control missing command on %s", topic)
            return

        cmd_payload = payload.get("payload", {})
        if not isinstance(cmd_payload, dict):
            cmd_payload = {}

        try:
            result = robot_service.dispatch_control(robot_code, command, cmd_payload)
            logger.info("MQTT control handled: %s -> %s", topic, result.get("status"))
            self.publish_robot_status(robot_code)
        except HTTPException as exc:
            logger.warning("MQTT control failed on %s: %s", topic, exc.detail)
        except Exception:
            logger.exception("MQTT control error on %s", topic)

    def publish_robot_status(self, robot_code: str) -> bool:
        status_data = robot_service.get_status(robot_code)
        payload = RobotStatusPayload.model_validate(status_data).model_dump(mode="json")
        topic = robot_status_topic(robot_code)
        return mqtt_manager.publish_json(topic, payload, qos=1, retain=True)

    def publish_all_robot_status(self) -> None:
        for item in robot_service.list_status():
            self.publish_robot_status(item["robot_code"])

    def publish_alarm(self, alarm: AlarmNotifyPayload) -> bool:
        return mqtt_manager.publish_json(
            ALARM_NOTIFY,
            alarm.model_dump(mode="json"),
            qos=1,
            retain=False,
        )

    def control_via_rest(
        self,
        db: Session,
        user_id: int,
        request: RobotControlRequest,
    ) -> dict[str, Any]:
        result = robot_service.dispatch_control(
            request.robot_code,
            request.command,
            request.payload,
        )
        write_operation_log(
            db,
            user_id=user_id,
            action="robot_control",
            description=f"下发指令 {request.command} 至 {request.robot_code}",
        )
        db.commit()
        self.publish_robot_status(request.robot_code)
        return result

    async def _status_heartbeat_loop(self) -> None:
        interval = max(1, settings.mqtt_status_interval_sec)
        while True:
            try:
                if mqtt_manager.is_connected:
                    self.publish_all_robot_status()
            except Exception:
                logger.exception("MQTT status heartbeat failed")
            await asyncio.sleep(interval)


mqtt_service = MqttService()
