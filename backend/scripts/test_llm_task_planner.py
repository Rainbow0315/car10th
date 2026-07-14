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

        class APIRouter:
            def get(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

            def post(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

        def Query(default=None, *args, **kwargs):
            return default

        fastapi.APIRouter = APIRouter
        fastapi.Query = Query
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
        llm_model="gpt-5.4-mini",
        llm_planner_timeout_sec=12.0,
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

    import apps.web_api.services.llm_task_service as llm_task_module
    from apps.web_api.services.llm_task_service import LlmTaskService
    from common.schemas.llm import LlmTaskExecuteRequest, LlmTaskPlanRequest

    def fake_send_cmd_vel_to_ros_bridges(robot_codes, **kwargs):
        duration = float(kwargs["duration"])
        effective_duration = duration + 0.35 if len(robot_codes) > 1 and duration >= 1.0 else duration
        rate_hz = float(kwargs["rate_hz"])
        effective_rate_hz = max(rate_hz, 15.0) if len(robot_codes) > 1 and duration >= 1.0 else rate_hz
        return {
            "target_robots": robot_codes,
            "all_ok": True,
            "command": "cmd_vel",
            "requested_duration": duration,
            "effective_duration": effective_duration,
            "duration_compensation": effective_duration - duration,
            "requested_rate_hz": rate_hz,
            "effective_rate_hz": effective_rate_hz,
            "members": [
                {
                    "robot_code": robot_code,
                    "ros_bridge_url": f"http://{robot_code}.test:8001",
                    "ok": True,
                    "status_code": 200,
                    "elapsed_ms": 1.0,
                    "response": {"status": "accepted"},
                    "error": None,
                }
                for robot_code in robot_codes
            ],
        }

    llm_task_module.send_cmd_vel_to_ros_bridges = fake_send_cmd_vel_to_ros_bridges

    service = LlmTaskService()
    cases = [
        ("stop robot_001", "fleet.safety_stop", True),
        ("move forward robot_001", "fleet.motion", True),
        ("list robots", "fleet.list_robots", False),
        ("rescue approach robot_001", "fleet.rescue_approach", True),
        ("rescue search robot_001", "fleet.rescue_search", True),
        ("corridor crawl robot_001", "fleet.corridor_crawl", True),
        ("yield robot_001", "fleet.corridor_yield", True),
        ("avoid hazard robot_001", "fleet.hazard_avoidance", True),
        ("formation robot_001", "fleet.formation", True),
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

    motion_cases = [
        ("move forward robot_001 for 2 seconds", "forward", 2.0),
        ("move forward robot_001 for 3 seconds", "forward", 3.0),
        ("robot_001 前进 5 秒", "forward", 5.0),
        ("robot_001 前进三秒", "forward", 3.0),
        ("robot_001 前进五秒", "forward", 5.0),
        ("robot_001 后退 1 秒", "backward", 1.0),
        ("robot_001 \u540e\u9000 2s", "backward", 2.0),
        ("robot_001 向左移动 0.5 秒", "left", 0.5),
        ("robot_001 向右移动 0.5 秒", "right", 0.5),
        ("robot_001 左转 1 秒", "rotate_left", 1.0),
        ("robot_001 右转 1 秒", "rotate_right", 1.0),
    ]
    for message, expected_action, expected_duration in motion_cases:
        plan = await service.plan(
            LlmTaskPlanRequest(message=message, allow_llm=True),
        )
        assert plan.source == "rule_fallback", message
        assert plan.steps[0].tool == "fleet.motion", (message, plan.steps[0].tool)
        assert plan.steps[0].arguments["action"] == expected_action, plan.steps[0].arguments
        assert plan.steps[0].arguments["duration_seconds"] == expected_duration, plan.steps[0].arguments

    fallback_sequence = await service.plan(
        LlmTaskPlanRequest(message="让 robot_001 先前进 3 秒，再向右走 3 秒", allow_llm=False),
    )
    assert fallback_sequence.source == "rule_fallback"
    assert [step.tool for step in fallback_sequence.steps] == ["fleet.motion", "fleet.motion"]
    assert [step.arguments["action"] for step in fallback_sequence.steps] == ["forward", "right"]
    assert [step.arguments["duration_seconds"] for step in fallback_sequence.steps] == [3.0, 3.0]

    fallback_two_robot = await service.plan(
        LlmTaskPlanRequest(
            message="让两辆车同时后退 1 秒",
            robot_codes=["robot_001", "robot_002"],
            allow_llm=False,
        ),
    )
    assert fallback_two_robot.source == "rule_fallback"
    assert len(fallback_two_robot.steps) == 1
    assert fallback_two_robot.steps[0].arguments["robot_codes"] == ["robot_001", "robot_002"]
    assert fallback_two_robot.steps[0].arguments["action"] == "backward"
    assert fallback_two_robot.steps[0].arguments["duration_seconds"] == 1.0

    tools = service.list_tools(["robot_001"]).tools
    safety_stop = next(tool for tool in tools if tool.name == "fleet.safety_stop")
    motion = next(tool for tool in tools if tool.name == "fleet.motion")
    nudge_forward = next(tool for tool in tools if tool.name == "fleet.nudge_forward")
    corridor_crawl = next(tool for tool in tools if tool.name == "fleet.corridor_crawl")
    plate_verify = next(tool for tool in tools if tool.name == "fleet.plate_verify")
    assert safety_stop.backend_route == "POST /api/fleet/safety/stop"
    assert safety_stop.command_name == "emergency_stop"
    assert safety_stop.available is True
    assert motion.command_name == "llm_motion"
    assert motion.available is False
    assert motion.unavailable_reason == "not all target robots are ready"
    assert nudge_forward.command_name == "nudge_forward"
    assert nudge_forward.available is False
    assert nudge_forward.unavailable_reason == "not all target robots are ready"
    assert corridor_crawl.command_name == "corridor_crawl"
    assert corridor_crawl.available is False
    assert corridor_crawl.unavailable_reason == "not all target robots are ready"
    assert plate_verify.available is False
    assert plate_verify.unavailable_reason == "not all target robots are ready"

    status = service.runtime_status()
    assert status.llm_configured is False
    assert status.planner_mode == "rule_fallback"

    from apps.web_api.services import llm_task_service as llm_module

    llm_module.settings.llm_api_base = "https://example.com/v1/chat/completions?token=secret-key-for-test"
    configured_status = service.runtime_status()
    assert configured_status.llm_configured is True
    assert configured_status.planner_mode == "llm"
    assert configured_status.api_base_host == "example.com"
    assert "secret-key-for-test" not in configured_status.model
    assert "secret-key-for-test" not in configured_status.message

    unsafe_steps = service._steps_from_llm(
        [{"tool": "fleet.plate_verify", "arguments": {"verifier_robot_code": "robot_001"}}]
    )
    assert unsafe_steps == []

    normalized_motion_steps = service._steps_from_llm(
        [
            {
                "tool": "fleet.motion",
                "arguments": {
                    "action": "move_forward",
                    "duration_seconds": "3秒",
                },
            }
        ],
        request=LlmTaskPlanRequest(message="让 robot_001 往前走 3 秒", allow_llm=True),
    )
    assert len(normalized_motion_steps) == 1
    assert normalized_motion_steps[0].tool == "fleet.motion"
    assert normalized_motion_steps[0].arguments["robot_code"] == "robot_001"
    assert normalized_motion_steps[0].arguments["action"] == "forward"
    assert normalized_motion_steps[0].arguments["duration_seconds"] == 3.0

    generic_motion_steps = service._steps_from_llm(
        [{"tool": "fleet.motion", "arguments": {"duration_seconds": "1s"}}],
        request=LlmTaskPlanRequest(message="让 robot_001 动 1 秒", allow_llm=True),
    )
    assert len(generic_motion_steps) == 1
    assert generic_motion_steps[0].arguments["action"] == "forward"
    assert generic_motion_steps[0].arguments["duration_seconds"] == 1.0

    normalized_stop_steps = service._steps_from_llm(
        [{"tool": "fleet.safety_stop", "arguments": {"robot_code": "robot_001"}}],
        request=LlmTaskPlanRequest(message="robot_001 停车", allow_llm=True),
    )
    assert len(normalized_stop_steps) == 1
    assert normalized_stop_steps[0].tool == "fleet.safety_stop"
    assert normalized_stop_steps[0].arguments["robot_codes"] == ["robot_001"]

    sequential_motion_steps = service._steps_from_llm(
        [
            {"tool": "fleet.motion", "arguments": {"robot_code": "robot_001", "action": "forward", "duration": "3s"}},
            {"tool": "fleet.motion", "arguments": {"robot_code": "robot_001", "action": "move_right", "duration_seconds": "3秒"}},
        ],
        request=LlmTaskPlanRequest(message="robot_001 first forward 3s then right 3s", allow_llm=True),
    )
    assert len(sequential_motion_steps) == 2
    assert sequential_motion_steps[0].arguments["action"] == "forward"
    assert sequential_motion_steps[0].arguments["duration_seconds"] == 3.0
    assert sequential_motion_steps[1].arguments["action"] == "right"
    assert sequential_motion_steps[1].arguments["duration_seconds"] == 3.0

    two_robot_motion_steps = service._steps_from_llm(
        [
            {
                "tool": "fleet.motion",
                "arguments": {
                    "robot_codes": ["robot_001", "robot_002"],
                    "action": "go_backward",
                    "duration_seconds": "2s",
                },
            }
        ],
        request=LlmTaskPlanRequest(
            message="robot_001 and robot_002 move backward together for 2 seconds",
            robot_codes=["robot_001", "robot_002"],
            allow_llm=True,
        ),
    )
    assert len(two_robot_motion_steps) == 1
    assert two_robot_motion_steps[0].arguments["robot_codes"] == ["robot_001", "robot_002"]
    assert two_robot_motion_steps[0].arguments["robot_code"] == "robot_001"
    assert two_robot_motion_steps[0].arguments["action"] == "backward"
    assert two_robot_motion_steps[0].arguments["duration_seconds"] == 2.0

    original_ensure_ready = service._ensure_ready
    service._ensure_ready = lambda robot_codes: None  # type: ignore[method-assign]
    try:
        two_robot_result = service._execute_step(two_robot_motion_steps[0])
    finally:
        service._ensure_ready = original_ensure_ready  # type: ignore[method-assign]
    assert len(two_robot_result["commands"]) == 2
    assert [command["robot_code"] for command in two_robot_result["commands"]] == ["robot_001", "robot_002"]
    assert all(command["command"] == "cmd_vel" for command in two_robot_result["commands"])
    assert two_robot_result["teleop"]["requested_duration"] == 2.0
    assert two_robot_result["teleop"]["effective_duration"] >= 2.0

    from apps.web_api.routers import llm as llm_router

    route_status = llm_router.get_llm_runtime_status()
    assert route_status.llm_configured is True
    route_tools = llm_router.list_llm_tools(["robot_001"])
    assert any(tool.name == "fleet.safety_stop" for tool in route_tools.tools)
    assert any(tool.name == "fleet.motion" for tool in route_tools.tools)
    assert any(tool.name == "fleet.nudge_forward" for tool in route_tools.tools)
    assert any(tool.name == "fleet.corridor_crawl" for tool in route_tools.tools)

    route_plan = await llm_router.plan_llm_task(
        LlmTaskPlanRequest(message="stop robot_001", allow_llm=False),
    )
    assert route_plan.plan_id
    assert route_plan.steps[0].tool == "fleet.safety_stop"
    try:
        llm_router.execute_llm_task(
            route_plan.plan_id,
            LlmTaskExecuteRequest(confirmed=False),
        )
    except sys.modules["fastapi"].HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("execution without confirmation must be rejected")
    route_result = llm_router.execute_llm_task(
        route_plan.plan_id,
        LlmTaskExecuteRequest(confirmed=True),
    )
    assert route_result.steps[0].status == "executed"
    assert route_result.steps[0].result["commands"][0]["status"] == "published"

    redacted = service._safe_error(RuntimeError("bad secret-key-for-test"))
    assert "secret-key-for-test" not in redacted
    print("llm_task_planner_smoke_ok")


if __name__ == "__main__":
    asyncio.run(run_tests())
