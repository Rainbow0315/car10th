from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from apps.web_api.services.fleet_service import fleet_service


DEFAULT_ROS_BRIDGE_BY_ROBOT = {
    "robot_001": "http://192.168.137.239:8001",
    "robot_002": "http://192.168.137.89:8001",
}

MULTI_ROBOT_DURATION_COMPENSATION_SEC = 0.35
MIN_DURATION_FOR_COMPENSATION_SEC = 1.0
MULTI_ROBOT_MIN_RATE_HZ = 15.0


def send_cmd_vel_to_ros_bridges(
    robot_codes: list[str],
    *,
    linear_x: float,
    linear_y: float,
    angular_z: float,
    duration: float,
    rate_hz: float,
    wait_for_subscriber_timeout: float,
) -> dict[str, Any]:
    effective_duration = compensated_duration(duration, robot_count=len(robot_codes))
    effective_rate_hz = compensated_rate_hz(
        rate_hz,
        robot_count=len(robot_codes),
        duration=duration,
    )
    payload = {
        "linear_x": linear_x,
        "linear_y": linear_y,
        "angular_z": angular_z,
        "duration": effective_duration,
        "rate_hz": effective_rate_hz,
        "wait_for_subscriber_timeout": wait_for_subscriber_timeout,
    }
    members = call_ros_bridges_concurrently(
        robot_codes,
        path="/api/teleop/cmd-vel",
        payload=payload,
        timeout_sec=max(5.0, effective_duration + 3.0),
    )
    return {
        "target_robots": robot_codes,
        "all_ok": all(item["ok"] for item in members),
        "command": "cmd_vel",
        "requested_duration": duration,
        "effective_duration": effective_duration,
        "duration_compensation": round(effective_duration - duration, 3),
        "requested_rate_hz": rate_hz,
        "effective_rate_hz": effective_rate_hz,
        "members": members,
    }


def stop_ros_bridges(robot_codes: list[str]) -> dict[str, Any]:
    members = call_ros_bridges_concurrently(
        robot_codes,
        path="/api/teleop/stop",
        payload=None,
        timeout_sec=5.0,
    )
    return {
        "target_robots": robot_codes,
        "all_ok": all(item["ok"] for item in members),
        "command": "stop",
        "members": members,
    }


def compensated_duration(duration: float, *, robot_count: int) -> float:
    if robot_count <= 1 or duration < MIN_DURATION_FOR_COMPENSATION_SEC:
        return round(duration, 3)
    return round(min(10.0, duration + MULTI_ROBOT_DURATION_COMPENSATION_SEC), 3)


def compensated_rate_hz(rate_hz: float, *, robot_count: int, duration: float) -> float:
    if robot_count <= 1 or duration < MIN_DURATION_FOR_COMPENSATION_SEC:
        return round(rate_hz, 3)
    return round(max(rate_hz, MULTI_ROBOT_MIN_RATE_HZ), 3)


def robot_ros_bridge_url(robot_code: str) -> str:
    robot = fleet_service.get_robot(robot_code)
    agent_ip = str(robot.get("agent_ip") or "").strip()
    if agent_ip:
        return f"http://{agent_ip}:8001"
    fallback = DEFAULT_ROS_BRIDGE_BY_ROBOT.get(robot_code)
    if fallback:
        return fallback
    raise ValueError(f"{robot_code} has no agent_ip in fleet status")


def call_ros_bridge(
    robot_code: str,
    path: str,
    payload: dict[str, Any] | None,
    timeout_sec: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    base_url = ""
    try:
        base_url = robot_ros_bridge_url(robot_code).rstrip("/")
        url = f"{base_url}{path}"
        with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=2.0)) as client:
            response = client.post(url, json=payload)
    except Exception as exc:
        return {
            "robot_code": robot_code,
            "ros_bridge_url": base_url,
            "ok": False,
            "status_code": None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "response": None,
            "error": str(exc),
        }

    try:
        body: Any = response.json()
    except ValueError:
        body = {"raw": response.text}
    return {
        "robot_code": robot_code,
        "ros_bridge_url": base_url,
        "ok": response.is_success,
        "status_code": response.status_code,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "response": body if isinstance(body, dict) else {"value": body},
        "error": None if response.is_success else response.text,
    }


def call_ros_bridges_concurrently(
    robot_codes: list[str],
    path: str,
    payload: dict[str, Any] | None,
    timeout_sec: float,
) -> list[dict[str, Any]]:
    results_by_robot: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(robot_codes))) as executor:
        futures = {
            executor.submit(call_ros_bridge, robot_code, path, payload, timeout_sec): robot_code
            for robot_code in robot_codes
        }
        for future in as_completed(futures):
            robot_code = futures[future]
            try:
                results_by_robot[robot_code] = future.result()
            except Exception as exc:
                results_by_robot[robot_code] = {
                    "robot_code": robot_code,
                    "ros_bridge_url": "",
                    "ok": False,
                    "status_code": None,
                    "elapsed_ms": 0.0,
                    "response": None,
                    "error": str(exc),
                }
    return [results_by_robot[robot_code] for robot_code in robot_codes]
