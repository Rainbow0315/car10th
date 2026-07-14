import threading
import unittest
from unittest.mock import patch

from apps.web_api.services.patrol_service import PatrolService


class PatrolReturnToStartTests(unittest.TestCase):
    def test_run_task_returns_to_recorded_start_pose_when_enabled(self):
        service = PatrolService()
        goals = []
        waypoints = [
            {"seq": 1, "x": 0.0, "y": 0.0, "yaw": 0.0},
            {"seq": 2, "x": 1.0, "y": 0.0, "yaw": 0.0},
            {"seq": 3, "x": 1.0, "y": 1.0, "yaw": 1.57},
        ]
        start_goal = {"seq": 0, "x": -0.5, "y": 0.25, "yaw": 0.0, "name": "return_to_start"}

        with patch("apps.web_api.services.patrol_service.slam_service.publish_goal") as publish_goal, \
            patch.object(service, "_wait_until_arrived"), \
            patch.object(service, "_mark_db_completed"), \
            patch.object(service, "_finish_runtime"):
            publish_goal.side_effect = lambda payload: goals.append(payload)
            service._run_task("task_1", "robot_001", 1, waypoints, threading.Event(), start_goal)

        self.assertEqual([goal["x"] for goal in goals], [0.0, 1.0, 1.0, -0.5])
        self.assertEqual([goal["y"] for goal in goals], [0.0, 0.0, 1.0, 0.25])

    def test_run_task_does_not_return_when_disabled(self):
        service = PatrolService()
        goals = []
        waypoints = [
            {"seq": 1, "x": 0.0, "y": 0.0, "yaw": 0.0},
            {"seq": 2, "x": 1.0, "y": 0.0, "yaw": 0.0},
        ]

        with patch("apps.web_api.services.patrol_service.slam_service.publish_goal") as publish_goal, \
            patch.object(service, "_wait_until_arrived"), \
            patch.object(service, "_mark_db_completed"), \
            patch.object(service, "_finish_runtime"):
            publish_goal.side_effect = lambda payload: goals.append(payload)
            service._run_task("task_1", "robot_001", 1, waypoints, threading.Event(), None)

        self.assertEqual([goal["x"] for goal in goals], [0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
