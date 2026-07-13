from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException

from apps.ros_bridge.adapters.cmd_vel import CmdVelCommand
from apps.ros_bridge.publishers.cmd_vel import CmdVelPublisher, RosRuntimeUnavailableError
from apps.ros_bridge.publishers.initial_pose import InitialPosePublisher
from apps.ros_bridge.publishers.nav_goal import NavGoalPublisher
from apps.ros_bridge.subscribers.slam_map import SlamMapSubscriber
from common.schemas.slam import (
    SlamGoalRequest,
    SlamGoalResponse,
    SlamInitialPoseRequest,
    SlamInitialPoseResponse,
    SlamMapResponse,
)
from common.schemas.teleop import CmdVelAcceptedResponse, CmdVelRequest, RosBridgeHealthResponse, StopResponse


class RosBridgeState:
    def __init__(self) -> None:
        self.publisher: Optional[CmdVelPublisher] = None
        self.nav_goal: Optional[NavGoalPublisher] = None
        self.initial_pose: Optional[InitialPosePublisher] = None
        self.slam_map: Optional[SlamMapSubscriber] = None
        self.startup_error: Optional[str] = None
        self.nav_goal_startup_error: Optional[str] = None
        self.initial_pose_startup_error: Optional[str] = None
        self.slam_startup_error: Optional[str] = None


state = RosBridgeState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    topic_name = os.getenv("ROS_CMD_VEL_TOPIC", "/cmd_vel")
    try:
        state.slam_map = SlamMapSubscriber(
            map_topic=os.getenv("ROS_MAP_TOPIC", "/map"),
            odom_topic=os.getenv("ROS_ODOM_TOPIC", "/odom"),
            amcl_topic=os.getenv("ROS_AMCL_TOPIC", "/amcl_pose"),
            scan_topic=os.getenv("ROS_SCAN_TOPIC", "/scan"),
            scan_x_offset=float(os.getenv("ROS_SCAN_X_OFFSET", "-0.0455")),
            scan_y_offset=float(os.getenv("ROS_SCAN_Y_OFFSET", "5.258e-05")),
            scan_yaw_offset=float(os.getenv("ROS_SCAN_YAW_OFFSET", "3.141592653589793")),
        )
    except RosRuntimeUnavailableError as exc:
        state.slam_startup_error = str(exc)
    try:
        state.publisher = CmdVelPublisher(topic_name=topic_name)
    except RosRuntimeUnavailableError as exc:
        state.startup_error = str(exc)
    try:
        state.nav_goal = NavGoalPublisher(topic_name=os.getenv("ROS_GOAL_TOPIC", "/goal_pose"))
    except RosRuntimeUnavailableError as exc:
        state.nav_goal_startup_error = str(exc)
    try:
        state.initial_pose = InitialPosePublisher(topic_name=os.getenv("ROS_INITIAL_POSE_TOPIC", "/initialpose"))
    except RosRuntimeUnavailableError as exc:
        state.initial_pose_startup_error = str(exc)
    try:
        yield
    finally:
        if state.initial_pose is not None:
            state.initial_pose.close()
        if state.nav_goal is not None:
            state.nav_goal.close()
        if state.publisher is not None:
            state.publisher.close()
        if state.slam_map is not None:
            state.slam_map.close()


app = FastAPI(
    title="ROS Bridge API",
    description="Minimal ROS bridge for teleoperation. First goal: publish Twist messages to make the robot move.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=RosBridgeHealthResponse)
def health_check():
    return {
        "status": "ok" if state.publisher is not None else "degraded",
        "service": "ros_bridge",
        "cmd_vel_topic": state.publisher.topic_name if state.publisher is not None else None,
        "subscriber_count": state.publisher.subscription_count() if state.publisher is not None else 0,
        "node_name": state.publisher.node_name if state.publisher is not None else None,
        "startup_error": state.startup_error,
    }


@app.get("/api/slam/map", response_model=SlamMapResponse)
def get_slam_map():
    if state.slam_map is None:
        raise HTTPException(
            status_code=503,
            detail=state.slam_startup_error or "SLAM map subscriber is not ready.",
        )
    return state.slam_map.snapshot()


@app.post("/api/slam/goal", response_model=SlamGoalResponse)
def publish_nav_goal(payload: SlamGoalRequest):
    publisher = _require_nav_goal_publisher()
    publisher.publish_goal(x=payload.x, y=payload.y, yaw=payload.yaw, frame_id=payload.frame_id)
    return {
        "status": "accepted",
        "topic_name": publisher.topic_name,
        "frame_id": payload.frame_id,
        "goal": {
            "x": payload.x,
            "y": payload.y,
            "yaw": payload.yaw,
        },
    }


@app.post("/api/slam/initial-pose", response_model=SlamInitialPoseResponse)
def publish_initial_pose(payload: SlamInitialPoseRequest):
    publisher = _require_initial_pose_publisher()
    publisher.publish_initial_pose(x=payload.x, y=payload.y, yaw=payload.yaw, frame_id=payload.frame_id)
    return {
        "status": "accepted",
        "topic_name": publisher.topic_name,
        "frame_id": payload.frame_id,
        "pose": {
            "x": payload.x,
            "y": payload.y,
            "yaw": payload.yaw,
        },
    }


@app.post("/api/teleop/cmd-vel", response_model=CmdVelAcceptedResponse)
def publish_cmd_vel(payload: CmdVelRequest):
    publisher = _require_publisher()
    command = CmdVelCommand(
        linear_x=payload.linear_x,
        linear_y=payload.linear_y,
        angular_z=payload.angular_z,
        duration=payload.duration,
        rate_hz=payload.rate_hz,
    ).normalized()
    subscriber_count = publisher.wait_for_subscribers(timeout=payload.wait_for_subscriber_timeout)
    if subscriber_count < 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No active subscriber on {publisher.topic_name}. "
                "Please confirm the chassis bringup is running and `ros2 topic info /cmd_vel` shows at least one subscriber."
            ),
        )

    if command.duration > 0:
        publisher.publish_for_duration(
            linear_x=command.linear_x,
            linear_y=command.linear_y,
            angular_z=command.angular_z,
            duration=command.duration,
            rate_hz=command.rate_hz,
        )
        mode = "timed"
    else:
        publisher.publish_once(
            linear_x=command.linear_x,
            linear_y=command.linear_y,
            angular_z=command.angular_z,
        )
        mode = "single"

    return {
        "status": "accepted",
        "mode": mode,
        "topic_name": publisher.topic_name,
        "subscriber_count": subscriber_count,
        "waited_for_subscriber_timeout": payload.wait_for_subscriber_timeout,
        "command": {
            "linear_x": command.linear_x,
            "linear_y": command.linear_y,
            "angular_z": command.angular_z,
            "duration": command.duration,
            "rate_hz": command.rate_hz,
        },
}


@app.post("/api/teleop/stop", response_model=StopResponse)
def stop_robot():
    publisher = _require_publisher()
    publisher.stop()
    return {
        "status": "accepted",
        "command": "stop",
        "topic_name": publisher.topic_name,
        "subscriber_count": publisher.subscription_count(),
    }


def _require_publisher() -> CmdVelPublisher:
    if state.publisher is None:
        raise HTTPException(
            status_code=503,
            detail=state.startup_error or "ROS publisher is not ready. Please source the ROS 2 environment first.",
        )
    return state.publisher


def _require_nav_goal_publisher() -> NavGoalPublisher:
    if state.nav_goal is None:
        raise HTTPException(
            status_code=503,
            detail=state.nav_goal_startup_error or "ROS navigation goal publisher is not ready.",
        )
    return state.nav_goal


def _require_initial_pose_publisher() -> InitialPosePublisher:
    if state.initial_pose is None:
        raise HTTPException(
            status_code=503,
            detail=state.initial_pose_startup_error or "ROS initial pose publisher is not ready.",
        )
    return state.initial_pose


def main():
    uvicorn.run(
        "apps.ros_bridge.main:app",
        host=os.getenv("ROS_BRIDGE_HOST", "0.0.0.0"),
        port=int(os.getenv("ROS_BRIDGE_PORT", "8001")),
        reload=False,
    )


if __name__ == "__main__":
    main()
