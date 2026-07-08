from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from apps.ros_bridge.adapters.cmd_vel import CmdVelCommand
from apps.ros_bridge.publishers.cmd_vel import CmdVelPublisher, RosRuntimeUnavailableError


class CmdVelRequest(BaseModel):
    linear_x: float = Field(..., description="Forward/backward velocity in m/s")
    linear_y: float = Field(0.0, description="Lateral velocity in m/s")
    angular_z: float = Field(0.0, description="Angular velocity in rad/s")
    duration: float = Field(0.3, ge=0.0, le=30.0, description="Publish duration in seconds")
    rate_hz: float = Field(10.0, ge=1.0, le=30.0, description="Publish rate while duration is active")


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


@app.get("/health")
def health_check():
    return {
        "status": "ok" if state.publisher is not None else "degraded",
        "service": "ros_bridge",
        "cmd_vel_topic": state.publisher.topic_name if state.publisher is not None else None,
        "startup_error": state.startup_error,
    }


@app.post("/api/teleop/cmd-vel")
def publish_cmd_vel(payload: CmdVelRequest):
    publisher = _require_publisher()
    command = CmdVelCommand(
        linear_x=payload.linear_x,
        linear_y=payload.linear_y,
        angular_z=payload.angular_z,
        duration=payload.duration,
        rate_hz=payload.rate_hz,
    ).normalized()

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
        "command": {
            "linear_x": command.linear_x,
            "linear_y": command.linear_y,
            "angular_z": command.angular_z,
            "duration": command.duration,
            "rate_hz": command.rate_hz,
        },
    }


@app.post("/api/teleop/stop")
def stop_robot():
    publisher = _require_publisher()
    publisher.stop()
    return {"status": "accepted", "command": "stop"}


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
