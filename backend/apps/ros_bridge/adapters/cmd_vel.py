from __future__ import annotations

from dataclasses import dataclass


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass
class CmdVelCommand:
    linear_x: float
    linear_y: float = 0.0
    angular_z: float = 0.0
    duration: float = 0.0
    rate_hz: float = 10.0

    def normalized(self) -> "CmdVelCommand":
        return CmdVelCommand(
            linear_x=clamp(self.linear_x, -1.0, 1.0),
            linear_y=clamp(self.linear_y, -1.0, 1.0),
            angular_z=clamp(self.angular_z, -5.0, 5.0),
            duration=clamp(self.duration, 0.0, 30.0),
            rate_hz=clamp(self.rate_hz, 1.0, 30.0),
        )
