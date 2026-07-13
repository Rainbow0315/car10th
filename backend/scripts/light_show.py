from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.tcp_car_bridge.light_show import LightShow
from apps.tcp_car_bridge.serial_hardware import SerialCarHardware


def main() -> None:
    hardware = SerialCarHardware(
        port=os.getenv("TCP_CAR_SERIAL_PORT", "/dev/myserial"),
        baudrate=int(os.getenv("TCP_CAR_SERIAL_BAUDRATE", "115200")),
    )
    show = LightShow(set_light_scene=hardware.set_light_scene)
    try:
        show.start()
        while show.is_running:
            time.sleep(0.05)
    except KeyboardInterrupt:
        show.stop()
    finally:
        show.stop()
        hardware.close()


if __name__ == "__main__":
    main()
