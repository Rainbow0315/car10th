"""Lightweight smoke tests for the LLM task planner.

This script intentionally avoids starting FastAPI, MQTT, or MySQL. It validates
the safety-critical rule fallback path that the mobile app can use when no LLM
gateway is configured.

Usage from repository root:
    python backend/scripts/test_llm_task_planner.py
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


def install_lightweight_stubs() -> None:
    """Stub optional runtime deps when this script runs outside backend venv."""

    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: object = None) -> None:
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fastapi.HTTPException = HTTPException
        fastapi.status = types.SimpleNamespace(
            HTTP_404_NOT_FOUND=404,
            HTTP_409_CONFLICT=409,
        )
        sys.modules["fastapi"] = fastapi

    if "httpx" not in sys.modules:
        httpx = types.ModuleType("httpx")

        class AsyncClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args) -> None:
                return None

            async def post(self, *args, **kwargs):
                raise RuntimeError("network disabled in lightweight test")

        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

    settings_mod = types.ModuleType("common.config.settings")
    settings_mod.settings = types.SimpleNamespace(
        llm_api_key="secret-key-for-test",
        llm_api_base="",
        llm_model="qwen-plus",
        fleet_robot_offline_sec=10,
        fleet_command_ack_timeout_sec=5,
    )
    sys.modules["common.config.settings"] = settings_mod

    mqtt_mod = types.ModuleType("common.mqtt")
    mqtt_mod.fleet_command_topic = lambda robot_code: f"fleet/command/{robot_code}"

    class MqttManager:
        is_connected = True
        last_error = None

        def publish_json(self, *args, **kwargs) -> bool:
            return True

    mqtt_mod.mqtt_manager = MqttManager()
    sys.modules["common.mqtt"] = mqtt_mod


async def run_tests() -> None:
    repo_backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_backend))
    install_lightweight_stubs()

    from apps.web_api.services.llm_task_service import LlmTaskService
    from common.schemas.llm import LlmTaskPlanRequest

    service = LlmTaskService()
    cases = [
        ("stop robot_001", "fleet.safety_stop", True),
        ("ready robot_001", "fleet.readiness", False),
        ("让 robot_001 核验 B2 消防通道的沪A12345", "fleet.plate_verify", True),
        ("fleet summary", "fleet.summary", False),
    ]
    for message, expected_tool, expected_confirmation in cases:
        plan = await service.plan(
            LlmTaskPlanRequest(message=message, allow_llm=False),
        )
        assert plan.steps, message
        assert plan.steps[0].tool == expected_tool, (message, plan.steps[0].tool)
        assert plan.requires_confirmation is expected_confirmation, (
            message,
            plan.requires_confirmation,
        )

    tools = service.list_tools(["robot_001"]).tools
    safety_stop = next(tool for tool in tools if tool.name == "fleet.safety_stop")
    plate_verify = next(tool for tool in tools if tool.name == "fleet.plate_verify")
    assert safety_stop.backend_route == "POST /api/fleet/safety/stop"
    assert safety_stop.command_name == "emergency_stop"
    assert safety_stop.available is True
    assert plate_verify.available is False
    assert plate_verify.unavailable_reason == "not all target robots are ready"

    unsafe_steps = service._steps_from_llm(
        [{"tool": "fleet.plate_verify", "arguments": {"verifier_robot_code": "robot_001"}}]
    )
    assert unsafe_steps == []

    redacted = service._safe_error(RuntimeError("bad secret-key-for-test"))
    assert "secret-key-for-test" not in redacted
    print("llm_task_planner_smoke_ok")


if __name__ == "__main__":
    asyncio.run(run_tests())
