"""Smoke test for the experimental fleet queue-follow controller.

This test avoids FastAPI, MQTT, and ROS. It monkey-patches the controller's
fleet status and teleop calls so the feature can be checked locally.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    from apps.web_api.services import fleet_queue_follow_service as module
    from apps.web_api.services.fleet_queue_follow_service import FleetQueueFollowService

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    poses = {
        "robot_001": {
            "robot_code": "robot_001",
            "status": "online",
            "pose_x": 1.0,
            "pose_y": 0.0,
            "pose_yaw": 0.0,
            "pose_updated_at": now,
        },
        "robot_002": {
            "robot_code": "robot_002",
            "status": "online",
            "pose_x": 0.0,
            "pose_y": 0.0,
            "pose_yaw": 0.0,
            "pose_updated_at": now,
        },
    }

    class FakeFleetService:
        def get_robot(self, robot_code: str):
            return dict(poses[robot_code])

    teleop_calls = []
    stop_calls = []

    def fake_send_cmd_vel_to_ros_bridges(robot_codes, **kwargs):
        teleop_calls.append((list(robot_codes), dict(kwargs)))
        return {
            "target_robots": list(robot_codes),
            "all_ok": True,
            "command": "cmd_vel",
            "members": [{"robot_code": code, "ok": True} for code in robot_codes],
        }

    def fake_stop_ros_bridges(robot_codes):
        stop_calls.append(list(robot_codes))
        return {
            "target_robots": list(robot_codes),
            "all_ok": True,
            "command": "stop",
            "members": [{"robot_code": code, "ok": True} for code in robot_codes],
        }

    module.fleet_service = FakeFleetService()
    module.send_cmd_vel_to_ros_bridges = fake_send_cmd_vel_to_ros_bridges
    module.stop_ros_bridges = fake_stop_ros_bridges

    service = FleetQueueFollowService()
    snapshot = service.start(
        robot_codes=["robot_001", "robot_002"],
        leader_robot_code="robot_001",
        spacing_m=0.5,
        target_lag_sec=0.2,
        interval_sec=0.2,
        max_linear_x=0.16,
        max_angular_z=0.45,
    )
    assert snapshot["active"] is True
    assert snapshot["leader_robot_code"] == "robot_001"

    deadline = time.time() + 2.0
    while time.time() < deadline and not teleop_calls:
        poses["robot_001"]["pose_x"] = float(poses["robot_001"]["pose_x"]) + 0.05
        poses["robot_001"]["pose_updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        poses["robot_002"]["pose_updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        time.sleep(0.05)

    assert teleop_calls, "queue-follow did not command follower"
    robot_codes, command = teleop_calls[-1]
    assert robot_codes == ["robot_002"]
    assert 0.0 <= command["linear_x"] <= 0.16
    assert abs(command["angular_z"]) <= 0.45

    stopped = service.stop(stop_motion=True)
    assert stopped["active"] is False
    assert ["robot_002"] in stop_calls

    teleop_calls.clear()
    stop_calls.clear()
    old_pose_time = datetime(2000, 1, 1)
    poses["robot_001"].update({"pose_x": 1.0, "pose_updated_at": old_pose_time})
    poses["robot_002"].update({"pose_x": 0.0, "pose_updated_at": old_pose_time})

    stale_service = FleetQueueFollowService()
    stale_service.start(
        robot_codes=["robot_001", "robot_002"],
        leader_robot_code="robot_001",
        spacing_m=0.5,
        target_lag_sec=0.2,
        interval_sec=0.2,
        max_linear_x=0.16,
        max_angular_z=0.45,
    )
    deadline = time.time() + 1.0
    while time.time() < deadline and not stop_calls:
        time.sleep(0.05)
    stale_service.stop(stop_motion=True)
    assert not teleop_calls, "stale poses should not command follower motion"
    assert ["robot_002"] in stop_calls
    print("fleet_queue_follow_smoke_ok")


if __name__ == "__main__":
    main()
