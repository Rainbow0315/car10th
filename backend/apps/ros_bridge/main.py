from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException

from apps.ros_bridge.adapters.cmd_vel import CmdVelCommand
from apps.ros_bridge.publishers.cmd_vel import CmdVelPublisher, RosRuntimeUnavailableError
from common.schemas.teleop import CmdVelAcceptedResponse, CmdVelRequest, RosBridgeHealthResponse, StopResponse


class RosBridgeState:
    def __init__(self) -> None:
        self.publisher: Optional[CmdVelPublisher] = None
        self.startup_error: Optional[str] = None


state = RosBridgeState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    topic_name = os.getenv("ROS_CMD_VEL_TOPIC", "/cmd_vel")
    try:
        state.publisher = CmdVelPublisher(topic_name=topic_name)
    except RosRuntimeUnavailableError as exc:
        state.startup_error = str(exc)
    try:
        yield
    finally:
        if state.publisher is not None:
            state.publisher.close()


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


def main():
    uvicorn.run(
        "apps.ros_bridge.main:app",
        host=os.getenv("ROS_BRIDGE_HOST", "0.0.0.0"),
        port=int(os.getenv("ROS_BRIDGE_PORT", "8001")),
        reload=False,
    )


if __name__ == "__main__":
    main()
