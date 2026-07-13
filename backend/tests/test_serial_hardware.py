from __future__ import annotations

import unittest

from apps.tcp_car_bridge.serial_hardware import (
    LIGHT_LEFT,
    LIGHT_ON,
    SerialCarHardware,
    build_packet,
)


class FakeSerial:
    def __init__(self, **_kwargs) -> None:
        self.is_open = True
        self.writes = []
        self.flush_count = 0

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.is_open = False


class SerialHardwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.serial = FakeSerial()
        self.hardware = SerialCarHardware(
            serial_factory=lambda **_kwargs: self.serial,
        )

    def test_builds_known_headlight_packet(self) -> None:
        self.assertEqual(
            build_packet(0x07, (0, 1)),
            bytes((0xFF, 0xFC, 0x05, 0x07, 0x00, 0x01, 0x0D)),
        )

    def test_all_lights_on_uses_physical_protocol(self) -> None:
        self.hardware.set_light_scene(LIGHT_ON)
        self.assertEqual(
            self.serial.writes,
            [bytes((0xFF, 0xFC, 0x05, 0x07, 0x00, 0x01, 0x0D))],
        )

    def test_left_only_first_clears_both_lights(self) -> None:
        self.hardware.set_light_scene(LIGHT_LEFT)
        self.assertEqual(len(self.serial.writes), 2)
        self.assertEqual(self.serial.writes[0][4:6], bytes((0, 0)))
        self.assertEqual(self.serial.writes[1][4:6], bytes((1, 1)))

if __name__ == "__main__":
    unittest.main()
