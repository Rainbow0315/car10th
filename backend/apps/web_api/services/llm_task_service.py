from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

from apps.web_api.services.fleet_service import fleet_service
from common.config.settings import settings
from common.mqtt import fleet_command_topic, mqtt_manager
from common.schemas.fleet import FleetReadinessResponse
from common.schemas.llm import (
    LlmRobotContext,
    LlmTaskExecuteResponse,
    LlmTaskPlanRequest,
    LlmTaskPlanResponse,
    LlmTaskPlanStep,
    LlmRuntimeStatusResponse,
    LlmToolListResponse,
    LlmToolSpec,
)


class LlmTaskService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._plans: dict[str, LlmTaskPlanResponse] = {}
        self._tools = self._build_tools()
        self._plan_store_path = Path.cwd() / ".run" / "llm_plans.json"
        self._load_plans()

    def list_tools(self, robot_codes: Optional[list[str]] = None) -> LlmToolListResponse:
        return LlmToolListResponse(tools=self._tools_with_availability(robot_codes or ["robot_001"]))

    def runtime_status(self) -> LlmRuntimeStatusResponse:
        configured = bool(settings.llm_api_key and settings.llm_api_base)
        api_base_host = self._api_base_host(settings.llm_api_base)
        return LlmRuntimeStatusResponse(
            llm_configured=configured,
            api_base_host=api_base_host,
            model=settings.llm_model,
            planner_mode="llm" if configured else "rule_fallback",
            message="真实 LLM 网关已配置。" if configured else "未配置 LLM_API_BASE 或 LLM_API_KEY，当前使用规则兜底。",
        )

    async def plan(self, request: LlmTaskPlanRequest) -> LlmTaskPlanResponse:
        robot_context = self._robot_context(request.robot_codes)
        steps: list[LlmTaskPlanStep] = []
        source = "rule_fallback"
        llm_error: Optional[str] = None

        if self._is_direct_motion_request(request.message) or self._is_stop_request(request.message):
            steps = self._plan_with_rules(request)
        elif request.allow_llm and settings.llm_api_key and settings.llm_api_base:
            try:
                steps = await self._plan_with_llm(request, robot_context)
                source = "llm"
            except Exception as exc:
                llm_error = self._safe_error(exc)
                steps = []

        if not steps:
            steps = self._plan_with_rules(request)

        safety_notes = self._safety_notes(steps)
        if llm_error:
            safety_notes.append(f"LLM 调用失败，已自动使用规则兜底：{llm_error}")
        plan = LlmTaskPlanResponse(
            plan_id=uuid.uuid4().hex,
            assistant_message=self._assistant_message(steps, source),
            source=source,  # type: ignore[arg-type]
            created_at=datetime.now(),
            requires_confirmation=any(step.requires_confirmation for step in steps),
            safety_notes=safety_notes,
            robot_context=robot_context,
            steps=steps,
        )

        if request.auto_execute:
            plan = self._execute_plan(plan, confirmed=not plan.requires_confirmation)

        with self._lock:
            self._plans[plan.plan_id] = plan
            self._plans = dict(list(self._plans.items())[-100:])
            self._save_plans()
        return plan

    def execute(self, plan_id: str, confirmed: bool) -> LlmTaskExecuteResponse:
        with self._lock:
            plan = self._plans.get(plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM plan not found")
        executed = self._execute_plan(plan, confirmed=confirmed)
        with self._lock:
            self._plans[plan_id] = executed
            self._save_plans()
        return LlmTaskExecuteResponse(
            plan_id=plan_id,
            executed_at=datetime.now(),
            steps=executed.steps,
            safety_notes=executed.safety_notes,
        )

    def _execute_plan(self, plan: LlmTaskPlanResponse, confirmed: bool) -> LlmTaskPlanResponse:
        if plan.requires_confirmation and not confirmed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This LLM plan requires explicit user confirmation before execution",
            )

        updated_steps = []
        for step in plan.steps:
            if step.status != "planned":
                updated_steps.append(step)
                continue
            try:
                result = self._execute_step(step)
                updated_steps.append(step.model_copy(update={"status": "executed", "result": result, "error": None}))
            except Exception as exc:
                updated_steps.append(step.model_copy(update={"status": "failed", "error": str(exc)}))
        return plan.model_copy(update={"steps": updated_steps})

    def _execute_step(self, step: LlmTaskPlanStep) -> Dict[str, Any]:
        spec = self._tools.get(step.tool)
        if spec is None:
            raise ValueError(f"Unsupported LLM tool: {step.tool}")
        missing = self._missing_required_arguments(spec, step.arguments)
        if missing:
            raise ValueError(f"LLM tool {step.tool} missing required arguments: {', '.join(missing)}")

        if step.tool == "fleet.summary":
            return fleet_service.get_summary()
        if step.tool == "fleet.list_robots":
            return {"robots": fleet_service.list_robots()}
        if step.tool == "fleet.readiness":
            robot_codes = self._string_list(step.arguments.get("robot_codes")) or ["robot_001"]
            return fleet_service.check_readiness(robot_codes)
        if step.tool == "fleet.safety_stop":
            robot_codes = self._string_list(step.arguments.get("robot_codes")) or ["robot_001"]
            commands = [
                self._publish_command(
                    robot_code,
                    "emergency_stop",
                    {
                        "reason": step.arguments.get("reason") or "LLM task safety stop",
                        "scenario": "llm_task_safety_control",
                    },
                )
                for robot_code in robot_codes
            ]
            return {"commands": commands}
        if step.tool == "fleet.motion":
            robot_code = str(step.arguments.get("robot_code") or "robot_001").strip()
            self._ensure_ready([robot_code])
            action = str(step.arguments.get("action") or "").strip().lower()
            motion = self._motion_for_action(action)
            duration = self._float_in_range(
                step.arguments.get("duration_seconds") or step.arguments.get("duration"),
                1.0,
                0.2,
                30.0,
            )
            motion["duration"] = duration
            command = self._publish_command(
                robot_code,
                "llm_motion",
                {
                    "action": action,
                    "reason": step.arguments.get("reason") or f"LLM requested {action} motion",
                    "source": "llm_task_planner",
                    "motion": motion,
                },
            )
            return {"command": command}
        if step.tool == "fleet.nudge_forward":
            robot_code = str(step.arguments.get("robot_code") or "robot_001").strip()
            self._ensure_ready([robot_code])
            duration = self._float_in_range(
                step.arguments.get("duration_seconds") or step.arguments.get("duration"),
                1.0,
                0.2,
                30.0,
            )
            command = self._publish_command(
                robot_code,
                "nudge_forward",
                {
                    "reason": step.arguments.get("reason") or "LLM requested a brief forward movement",
                    "source": "llm_task_planner",
                    "motion": {
                        "linear_x": 0.18,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration": duration,
                        "rate_hz": 10.0,
                    },
                },
            )
            return {"command": command}
        if step.tool == "fleet.rescue_approach":
            robot_code = str(step.arguments.get("responder_robot_code") or "robot_001").strip()
            self._ensure_ready([robot_code])
            command = self._publish_command(
                robot_code,
                "rescue_approach",
                {
                    "incident_id": step.arguments.get("incident_id") or uuid.uuid4().hex,
                    "disabled_robot_code": step.arguments.get("disabled_robot_code"),
                    "source": "llm_task_planner",
                    "motion": {
                        "linear_x": 0.08,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration": 0.8,
                        "rate_hz": 10.0,
                    },
                },
            )
            return {"command": command}
        if step.tool == "fleet.rescue_search":
            robot_code = str(step.arguments.get("responder_robot_code") or "robot_001").strip()
            self._ensure_ready([robot_code])
            command = self._publish_command(
                robot_code,
                "rescue_search",
                {
                    "incident_id": step.arguments.get("incident_id") or uuid.uuid4().hex,
                    "disabled_robot_code": step.arguments.get("disabled_robot_code"),
                    "source": "llm_task_planner",
                    "motion": {
                        "linear_x": 0.0,
                        "linear_y": 0.0,
                        "angular_z": 0.25,
                        "duration": 1.5,
                        "rate_hz": 10.0,
                    },
                },
            )
            return {"command": command}
        if step.tool == "fleet.corridor_crawl":
            robot_codes = self._string_list(step.arguments.get("robot_codes")) or ["robot_001"]
            self._ensure_ready(robot_codes)
            commands = []
            for slot_index, robot_code in enumerate(robot_codes):
                commands.append(
                    self._publish_command(
                        robot_code,
                        "corridor_crawl",
                        {
                            "corridor_id": step.arguments.get("corridor_id"),
                            "slot_index": slot_index,
                            "spacing_m": 1.0,
                            "traffic_rule": "llm_staggered_single_lane_passage",
                            "schedule": {
                                "start_delay_sec": float(slot_index),
                                "start_interval_sec": 1.0,
                            },
                            "source": "llm_task_planner",
                            "motion": {
                                "linear_x": 0.06,
                                "linear_y": 0.0,
                                "angular_z": 0.0,
                                "duration": 1.0,
                                "rate_hz": 10.0,
                            },
                        },
                    )
                )
            return {"commands": commands}
        if step.tool == "fleet.corridor_yield":
            robot_code = str(step.arguments.get("yielding_robot_code") or "robot_001").strip()
            self._ensure_ready([robot_code])
            command = self._publish_command(
                robot_code,
                "corridor_yield",
                {
                    "corridor_id": step.arguments.get("corridor_id"),
                    "priority_robot_code": step.arguments.get("priority_robot_code"),
                    "reason": step.arguments.get("reason") or "LLM requested corridor yield",
                    "source": "llm_task_planner",
                    "motion": {
                        "linear_x": -0.05,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration": 0.8,
                        "rate_hz": 10.0,
                    },
                },
            )
            return {"command": command}
        if step.tool == "fleet.hazard_avoidance":
            robot_codes = self._string_list(step.arguments.get("robot_codes")) or ["robot_001"]
            self._ensure_ready(robot_codes)
            avoid_direction = str(step.arguments.get("avoid_direction") or "left").lower()
            angular_z = -0.22 if avoid_direction == "right" else 0.22
            commands = [
                self._publish_command(
                    robot_code,
                    "hazard_avoid",
                    {
                        "hazard_id": step.arguments.get("hazard_id") or uuid.uuid4().hex,
                        "reported_by_robot_code": step.arguments.get("reported_by_robot_code"),
                        "avoid_direction": "right" if avoid_direction == "right" else "left",
                        "reason": step.arguments.get("reason") or "LLM requested hazard avoidance",
                        "source": "llm_task_planner",
                        "motion": {
                            "linear_x": 0.04,
                            "linear_y": 0.0,
                            "angular_z": angular_z,
                            "duration": 1.0,
                            "rate_hz": 10.0,
                        },
                    },
                )
                for robot_code in robot_codes
            ]
            return {"commands": commands}
        if step.tool == "fleet.formation":
            robot_codes = self._string_list(step.arguments.get("robot_codes")) or ["robot_001"]
            self._ensure_ready(robot_codes)
            formation_id = uuid.uuid4().hex
            commands = []
            members = []
            for slot_index, robot_code in enumerate(robot_codes):
                role = "leader" if slot_index == 0 else "follower"
                payload = {
                    "formation_id": formation_id,
                    "formation_type": step.arguments.get("formation_type") or "line",
                    "role": role,
                    "slot_index": slot_index,
                    "offset_x": -slot_index,
                    "offset_y": 0.0,
                    "mode": step.arguments.get("mode") or "patrol",
                    "source": "llm_task_planner",
                }
                command = self._publish_command(robot_code, "set_formation", payload)
                commands.append(command)
                members.append(
                    {
                        "robot_code": robot_code,
                        "role": role,
                        "slot_index": slot_index,
                        "offset_x": payload["offset_x"],
                        "offset_y": payload["offset_y"],
                        "command_id": command["command_id"],
                    }
                )
            fleet_service.register_formation(
                formation_id=formation_id,
                formation_type=str(step.arguments.get("formation_type") or "line"),
                mode=str(step.arguments.get("mode") or "patrol"),
                members=members,
            )
            return {"formation_id": formation_id, "commands": commands}
        if step.tool == "fleet.plate_verify":
            robot_code = str(step.arguments.get("verifier_robot_code") or "robot_001").strip()
            self._ensure_ready([robot_code])
            command = self._publish_command(
                robot_code,
                "plate_verify_scan",
                {
                    "verification_id": uuid.uuid4().hex,
                    "plate_number": step.arguments.get("plate_number") or "UNKNOWN",
                    "recognition_confidence": float(step.arguments.get("recognition_confidence") or 0.8),
                    "zone_id": step.arguments.get("zone_id"),
                    "source": "llm_task_planner",
                    "motion": {
                        "linear_x": 0.0,
                        "linear_y": 0.0,
                        "angular_z": 0.22,
                        "duration": 1.5,
                        "rate_hz": 10.0,
                    },
                },
            )
            return {"command": command}
        if step.tool == "fleet.escort_return":
            escort_robot_code = str(step.arguments.get("escort_robot_code") or "robot_001").strip()
            self._ensure_ready([escort_robot_code])
            command = self._publish_command(
                escort_robot_code,
                "escort_return",
                {
                    "mission_id": uuid.uuid4().hex,
                    "target_robot_code": step.arguments.get("target_robot_code") or "unknown_target",
                    "target_plate_number": step.arguments.get("target_plate_number"),
                    "maintenance_zone_id": step.arguments.get("maintenance_zone_id"),
                    "escort_position": "rear",
                    "reason": step.arguments.get("reason") or "LLM task escort return",
                    "source": "llm_task_planner",
                    "motion": {
                        "linear_x": 0.05,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration": 1.0,
                        "rate_hz": 10.0,
                    },
                },
            )
            return {"command": command}
        raise ValueError(f"Unsupported LLM tool: {step.tool}")

    def _load_plans(self) -> None:
        try:
            if not self._plan_store_path.exists():
                return
            raw = json.loads(self._plan_store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            plans = {}
            for item in raw[-100:]:
                try:
                    plan = LlmTaskPlanResponse.model_validate(item)
                except Exception:
                    continue
                plans[plan.plan_id] = plan
            self._plans = plans
        except Exception:
            self._plans = {}

    def _save_plans(self) -> None:
        try:
            self._plan_store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [plan.model_dump(mode="json") for plan in self._plans.values()]
            self._plan_store_path.write_text(
                json.dumps(payload[-100:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _publish_command(self, robot_code: str, command: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic = fleet_command_topic(robot_code)
        command_item = fleet_service.create_command(robot_code, command, payload, topic)
        envelope = {
            "command_id": command_item["command_id"],
            "command": command,
            "payload": payload,
            "issued_at": command_item["issued_at"].isoformat(),
        }
        published = mqtt_manager.publish_json(topic, envelope, qos=1, retain=False)
        command_item = fleet_service.mark_command_published(
            command_item["command_id"],
            published,
            None if published else mqtt_manager.last_error or "MQTT publish failed",
        )
        return command_item

    async def _plan_with_llm(
        self,
        request: LlmTaskPlanRequest,
        robot_context: list[LlmRobotContext],
    ) -> list[LlmTaskPlanStep]:
        base = settings.llm_api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            url = base
        elif base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"
        prompt = {
            "user_message": request.message,
            "available_tools": [
                tool.model_dump(mode="json") for tool in self._tools_with_availability(request.robot_codes)
            ],
            "robot_context": [item.model_dump(mode="json") for item in robot_context],
            "output_schema": {
                "steps": [
                    {
                        "tool": "fleet.safety_stop",
                        "arguments": {"robot_codes": ["robot_001"]},
                    }
                ]
            },
            "rules": [
                "Only use tools from available_tools.",
                "Do not output direct cmd_vel or raw chassis commands.",
                "For direct app-like motion requests such as forward, backward, left, right, rotate left, or rotate right, use fleet.motion with action and the requested duration_seconds.",
                "Use fleet.safety_stop only when the user asks to stop, brake, halt, or emergency-stop.",
                "For formation, corridor, rescue, yield, and hazard requests, prefer the matching fleet.* tool.",
                "Motion commands require confirmation.",
                "Return JSON only.",
            ],
        }
        body = {
            "model": settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a safe robot fleet task planner. Return compact JSON only.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "car10th-llm-task-planner/1.0",
                },
                json=body,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(self._strip_json_fence(content))
        return self._steps_from_llm(parsed.get("steps") or [])

    def _steps_from_llm(self, raw_steps: list[Any]) -> list[LlmTaskPlanStep]:
        steps = []
        for index, item in enumerate(raw_steps, start=1):
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool") or "").strip()
            spec = self._tools.get(tool_name)
            if spec is None:
                continue
            arguments = item.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            if self._missing_required_arguments(spec, arguments):
                continue
            steps.append(
                LlmTaskPlanStep(
                    step_id=f"step_{index}",
                    tool=spec.name,
                    title=spec.title,
                    arguments=arguments,
                    safety_level=spec.safety_level,
                    requires_confirmation=spec.requires_confirmation,
                )
            )
        return steps

    def _plan_with_rules(self, request: LlmTaskPlanRequest) -> list[LlmTaskPlanStep]:
        text = request.message.strip()
        explicit_robot_code = self._first_robot_code(text)
        robot_code = explicit_robot_code or self._best_ready_robot_code(request.robot_codes)
        plate_number = self._plate_number(text)
        zone_id = self._zone_id(text)

        if any(keyword in text for keyword in ["list robots", "robots", "小车列表", "有哪些小车", "列出小车"]):
            return [self._step(1, "fleet.list_robots", {})]
        if any(keyword in text for keyword in ["rescue approach", "approach rescue", "靠近救援", "接近故障车"]):
            return [
                self._step(
                    1,
                    "fleet.rescue_approach",
                    {"responder_robot_code": robot_code, "disabled_robot_code": "target_robot_unknown"},
                )
            ]
        if any(keyword in text for keyword in ["rescue search", "search rescue", "旋转搜索", "原地搜索", "搜索救援"]):
            return [
                self._step(
                    1,
                    "fleet.rescue_search",
                    {"responder_robot_code": robot_code, "disabled_robot_code": "target_robot_unknown"},
                )
            ]
        if any(keyword in text for keyword in ["corridor", "narrow passage", "狭窄通道", "通道慢行", "走廊慢行"]):
            return [self._step(1, "fleet.corridor_crawl", {"robot_codes": [robot_code]})]
        if any(keyword in text for keyword in ["yield", "让行", "让路", "后退让路", "退让"]):
            return [self._step(1, "fleet.corridor_yield", {"yielding_robot_code": robot_code})]
        if any(keyword in text for keyword in ["hazard", "avoid", "obstacle", "避障", "避让", "绕开障碍", "障碍"]):
            return [self._step(1, "fleet.hazard_avoidance", {"robot_codes": [robot_code]})]
        if any(keyword in text for keyword in ["formation", "编队", "队形", "排成一队"]):
            robot_codes = request.robot_codes if request.robot_codes else [robot_code]
            return [self._step(1, "fleet.formation", {"robot_codes": robot_codes, "formation_type": "line"})]

        direct_motion = self._direct_motion_arguments(text, robot_code)
        if direct_motion is not None:
            return [
                self._step(
                    1,
                    "fleet.motion",
                    direct_motion,
                )
            ]

        if any(keyword in text for keyword in ["急停", "停止", "stop", "刹车"]):
            return [
                self._step(
                    1,
                    "fleet.safety_stop",
                    {"robot_codes": [robot_code], "reason": f"LLM parsed from: {text[:80]}"},
                )
            ]
        if any(keyword in text for keyword in ["车牌", "核验", "确认", "扫描"]) or plate_number:
            return [
                self._step(
                    1,
                    "fleet.plate_verify",
                    {
                        "verifier_robot_code": robot_code,
                        "plate_number": plate_number or "UNKNOWN",
                        "recognition_confidence": 0.8,
                        "zone_id": zone_id,
                    },
                )
            ]
        if any(keyword in text for keyword in ["护送", "返航", "维修区"]):
            return [
                self._step(
                    1,
                    "fleet.escort_return",
                    {
                        "escort_robot_code": robot_code,
                        "target_robot_code": "target_robot_unknown",
                        "target_plate_number": plate_number,
                        "maintenance_zone_id": zone_id or "maintenance_zone",
                    },
                )
            ]
        if any(keyword in text for keyword in ["状态", "在线", "ready", "准备"]):
            return [self._step(1, "fleet.readiness", {"robot_codes": [robot_code]})]
        return [self._step(1, "fleet.summary", {})]

    def _is_direct_motion_request(self, text: str) -> bool:
        normalized = text.strip().lower()
        return self._motion_action_from_text(normalized) is not None

    def _is_stop_request(self, text: str) -> bool:
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in ["stop", "halt", "brake", "停止", "停车", "刹车", "急停"])

    def _direct_motion_arguments(self, text: str, robot_code: str) -> Optional[Dict[str, Any]]:
        normalized = text.strip().lower()
        action = self._motion_action_from_text(normalized)
        if action is None:
            return None
        return {
            "robot_code": robot_code,
            "action": action,
            "duration_seconds": self._duration_seconds(text),
            "reason": f"LLM parsed from: {text[:80]}",
        }

    def _motion_action_from_text(self, normalized: str) -> Optional[str]:
        stop_words = ["stop", "halt", "brake", "停止", "停车", "刹车", "急停"]
        if any(word in normalized for word in stop_words):
            return None

        checks = [
            ("rotate_left", ["rotate left", "turn left", "spin left", "左转", "向左转", "逆时针"]),
            ("rotate_right", ["rotate right", "turn right", "spin right", "右转", "向右转", "顺时针"]),
            ("backward", ["move backward", "backward", "reverse", "back up", "后退", "倒车", "向后", "往后"]),
            ("left", ["move left", "strafe left", "shift left", "向左移动", "左移", "往左", "向左平移"]),
            ("right", ["move right", "strafe right", "shift right", "向右移动", "右移", "往右", "向右平移"]),
            ("forward", ["move forward", "forward", "go forward", "前进", "向前", "往前"]),
        ]
        for action, keywords in checks:
            if any(keyword in normalized for keyword in keywords):
                return action
        return None

    def _motion_for_action(self, action: str) -> Dict[str, float]:
        defaults = {
            "forward": {"linear_x": 0.18, "linear_y": 0.0, "angular_z": 0.0, "rate_hz": 10.0},
            "backward": {"linear_x": -0.18, "linear_y": 0.0, "angular_z": 0.0, "rate_hz": 10.0},
            "left": {"linear_x": 0.0, "linear_y": 0.18, "angular_z": 0.0, "rate_hz": 10.0},
            "right": {"linear_x": 0.0, "linear_y": -0.18, "angular_z": 0.0, "rate_hz": 10.0},
            "rotate_left": {"linear_x": 0.0, "linear_y": 0.0, "angular_z": 0.9, "rate_hz": 10.0},
            "rotate_right": {"linear_x": 0.0, "linear_y": 0.0, "angular_z": -0.9, "rate_hz": 10.0},
        }
        motion = defaults.get(action)
        if motion is None:
            raise ValueError(f"Unsupported LLM motion action: {action}")
        return dict(motion)

    def _step(self, index: int, tool_name: str, arguments: Dict[str, Any]) -> LlmTaskPlanStep:
        spec = self._tools[tool_name]
        return LlmTaskPlanStep(
            step_id=f"step_{index}",
            tool=spec.name,
            title=spec.title,
            arguments=arguments,
            safety_level=spec.safety_level,
            requires_confirmation=spec.requires_confirmation,
        )

    def _robot_context(self, robot_codes: list[str]) -> list[LlmRobotContext]:
        codes = robot_codes or ["robot_001"]
        readiness = FleetReadinessResponse.model_validate(fleet_service.check_readiness(codes))
        return [
            LlmRobotContext(
                robot_code=member.robot_code,
                status=member.status,
                mode=member.robot.mode,
                ready_to_command=member.ready_to_command,
                reason=member.reason,
            )
            for member in readiness.members
        ]

    def _ensure_ready(self, robot_codes: list[str]) -> None:
        readiness = FleetReadinessResponse.model_validate(fleet_service.check_readiness(robot_codes))
        if not readiness.all_ready:
            raise ValueError("robot is not ready for LLM planned command")

    def _best_ready_robot_code(self, requested_robot_codes: list[str]) -> str:
        requested = [code.strip() for code in requested_robot_codes if code.strip()]
        readiness = FleetReadinessResponse.model_validate(
            fleet_service.check_readiness(requested or ["robot_001"])
        )
        for member in readiness.members:
            if member.ready_to_command:
                return member.robot_code

        online_robots = [
            str(item.get("robot_code") or "").strip()
            for item in fleet_service.list_robots()
            if item.get("status") == "online" and str(item.get("robot_code") or "").strip()
        ]
        if online_robots:
            online_robots.sort()
            return online_robots[0]
        return requested[0] if requested else "robot_001"

    def _tools_with_availability(self, robot_codes: list[str]) -> list[LlmToolSpec]:
        readiness = FleetReadinessResponse.model_validate(fleet_service.check_readiness(robot_codes or ["robot_001"]))
        mqtt_connected = bool(mqtt_manager.is_connected)
        tools = []
        for tool in self._tools.values():
            available = True
            unavailable_reason = None
            if tool.safety_level != "read_only" and not mqtt_connected:
                available = False
                unavailable_reason = "MQTT broker is not connected"
            elif tool.readiness_required and not readiness.all_ready:
                available = False
                unavailable_reason = "not all target robots are ready"
            tools.append(
                tool.model_copy(
                    update={
                        "available": available,
                        "unavailable_reason": unavailable_reason,
                    }
                )
            )
        return tools

    def _missing_required_arguments(self, spec: LlmToolSpec, arguments: Dict[str, Any]) -> list[str]:
        missing = []
        for name in spec.required_arguments:
            value = arguments.get(name)
            if name == "robot_codes":
                if not self._string_list(value):
                    missing.append(name)
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)
        return missing

    def _safety_notes(self, steps: list[LlmTaskPlanStep]) -> list[str]:
        notes = [
            "LLM 只生成任务计划，后端按工具白名单和机器人状态执行。",
            "不会允许 LLM 直接下发 /cmd_vel 或任意底盘速度。",
        ]
        if any(step.safety_level == "motion_command" for step in steps):
            notes.append("包含运动类任务，必须用户确认后执行，并可随时调用 safety_stop。")
        return notes

    def _assistant_message(self, steps: list[LlmTaskPlanStep], source: str) -> str:
        if not steps:
            return "我没有生成可执行计划，请换一种更明确的说法。"
        lines = ["我已生成一个安全任务计划：" if source == "llm" else "我用规则兜底生成了一个任务计划："]
        for index, step in enumerate(steps, start=1):
            lines.append(f"{index}. {step.title}")
        lines.append("请确认后再执行。")
        return "\n".join(lines)

    def _build_tools(self) -> dict[str, LlmToolSpec]:
        tools = [
            LlmToolSpec(
                name="fleet.summary",
                title="查询车队总览",
                description="读取车队在线数量、命令数量和编队状态，不会控制小车。",
                backend_route="GET /api/fleet/summary",
                safety_level="read_only",
                requires_confirmation=False,
            ),
            LlmToolSpec(
                name="fleet.list_robots",
                title="列出小车",
                description="读取当前后端已知的小车列表和在线状态，不会控制小车。",
                backend_route="GET /api/fleet/robots",
                safety_level="read_only",
                requires_confirmation=False,
            ),
            LlmToolSpec(
                name="fleet.readiness",
                title="检查小车是否可执行任务",
                description="检查指定 robot_code 是否在线且可接收任务。",
                backend_route="POST /api/fleet/readiness",
                required_arguments=["robot_codes"],
                safety_level="read_only",
                requires_confirmation=False,
            ),
            LlmToolSpec(
                name="fleet.safety_stop",
                title="安全停止小车",
                description="向指定小车下发 emergency_stop。",
                backend_route="POST /api/fleet/safety/stop",
                command_name="emergency_stop",
                required_arguments=["robot_codes"],
                safety_level="safe_command",
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.motion",
                title="单车短时运动",
                description="模仿 App 单车控制按钮，只允许 forward/backward/left/right/rotate_left/rotate_right 六种动作；可选 duration_seconds，按用户要求的秒数下发。",
                backend_route="MQTT fleet/command/{robot_code}",
                command_name="llm_motion",
                required_arguments=["robot_code", "action"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.nudge_forward",
                title="安全短距离前进",
                description="向指定小车下发 nudge_forward，直线前进；可选 duration_seconds，按用户要求的秒数下发。",
                backend_route="MQTT fleet/command/{robot_code}",
                command_name="nudge_forward",
                required_arguments=["robot_code"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.rescue_approach",
                title="救援接近",
                description="让救援车低速短时向故障车方向接近。",
                backend_route="POST /api/fleet/rescue/approach",
                command_name="rescue_approach",
                required_arguments=["responder_robot_code"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.rescue_search",
                title="救援搜索",
                description="让救援车原地低速旋转搜索目标。",
                backend_route="POST /api/fleet/rescue/search",
                command_name="rescue_search",
                required_arguments=["responder_robot_code"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.corridor_crawl",
                title="狭窄通道慢行",
                description="让一辆或多辆小车低速、错峰通过狭窄通道。",
                backend_route="POST /api/fleet/corridor/crawl",
                command_name="corridor_crawl",
                required_arguments=["robot_codes"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.corridor_yield",
                title="通道让行",
                description="让指定小车短时低速后退，为优先小车让路。",
                backend_route="POST /api/fleet/corridor/yield",
                command_name="corridor_yield",
                required_arguments=["yielding_robot_code"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.hazard_avoidance",
                title="障碍避让",
                description="让小车低速小弧线绕开障碍。",
                backend_route="POST /api/fleet/hazards/avoidance",
                command_name="hazard_avoid",
                required_arguments=["robot_codes"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.formation",
                title="创建编队",
                description="给多辆小车分配 leader/follower 编队角色和队形偏移。",
                backend_route="POST /api/fleet/formations",
                command_name="set_formation",
                required_arguments=["robot_codes"],
                safety_level="safe_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.plate_verify",
                title="派车核验车牌目标",
                description="向指定小车下发 plate_verify_scan，短时低速原地扫描。",
                backend_route="POST /api/fleet/vision/plate/verify",
                command_name="plate_verify_scan",
                required_arguments=["verifier_robot_code", "plate_number"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
            LlmToolSpec(
                name="fleet.escort_return",
                title="派车护送返航",
                description="向护送车下发 escort_return，低速短时跟随/护送动作。",
                backend_route="POST /api/fleet/escort/return",
                command_name="escort_return",
                required_arguments=["escort_robot_code", "target_robot_code"],
                safety_level="motion_command",
                readiness_required=True,
                requires_confirmation=True,
            ),
        ]
        return {tool.name: tool for tool in tools}

    def _strip_json_fence(self, content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        return cleaned

    def _first_robot_code(self, text: str) -> Optional[str]:
        match = re.search(r"robot[_-]\d+", text, flags=re.IGNORECASE)
        return match.group(0) if match else None

    def _plate_number(self, text: str) -> Optional[str]:
        match = re.search(r"[\u4e00-\u9fa5][A-Z][A-Z0-9]{5,6}", text.upper())
        if match:
            return match.group(0)
        match = re.search(r"PLATE[-_A-Z0-9]+", text.upper())
        return match.group(0) if match else None

    def _zone_id(self, text: str) -> Optional[str]:
        match = re.search(r"[A-Z]\d[-_A-Z0-9]*", text.upper())
        return match.group(0) if match else None

    def _duration_seconds(self, text: str) -> float:
        normalized = text.strip().lower()
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds|秒)", normalized)
        if match:
            return self._float_in_range(match.group(1), 1.0, 0.2, 30.0)

        word_seconds = {
            "one": 1.0,
            "two": 2.0,
            "three": 3.0,
            "一": 1.0,
            "二": 2.0,
            "两": 2.0,
            "三": 3.0,
            "四": 4.0,
            "五": 5.0,
            "六": 6.0,
            "七": 7.0,
            "八": 8.0,
            "九": 9.0,
            "十": 10.0,
        }
        for word, seconds in word_seconds.items():
            if word in normalized:
                return seconds
        return 1.0

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _safe_error(self, exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        api_key = settings.llm_api_key
        if api_key:
            message = message.replace(api_key, "***")
        return message[:240]

    @staticmethod
    def _float_in_range(value: Any, fallback: float, lower: float, upper: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = fallback
        return max(lower, min(upper, parsed))

    def _api_base_host(self, api_base: str) -> Optional[str]:
        if not api_base:
            return None
        parsed = urlparse(api_base)
        if parsed.hostname:
            return parsed.hostname
        return "configured"


llm_task_service = LlmTaskService()
