from __future__ import annotations

import unittest

from apps.tcp_car_bridge.main import ProtocolError, TcpCarBridge, parse_frame


def frame(command: str, data: str = "") -> str:
    declared_size = len(data) + 2
    body = f"01{command}{declared_size:02X}{data}"
    checksum = sum(int(body[index : index + 2], 16) for index in range(0, len(body), 2)) % 256
    return f"${body}{checksum:02X}#"


class FakePublisher:
    def __init__(self) -> None:
        self.light_messages = []
        self.motion_messages = []
        self.stop_count = 0
        self.closed = False

    def publish_int32(self, topic_name: str, value: int, repeat: int = 3) -> None:
        self.light_messages.append((topic_name, value, repeat))

    def publish_for_duration(self, **kwargs) -> None:
        self.motion_messages.append(kwargs)

    def stop(self) -> None:
        self.stop_count += 1

    def close(self) -> None:
        self.closed = True


class FakeShow:
    def __init__(self) -> None:
        self.is_running = False
        self.started = 0
        self.stopped = []

    def start(self) -> None:
        self.started += 1
        self.is_running = True

    def stop(self, turn_off_lights: bool = True) -> None:
        self.stopped.append(turn_off_lights)
        self.is_running = False


class TcpCarBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.publisher = FakePublisher()
        self.bridge = TcpCarBridge(publisher=self.publisher)
        self.show = FakeShow()
        self.bridge.show = self.show

    def test_parse_light_frame(self) -> None:
        parsed = parse_frame(frame("30", "05"))
        self.assertEqual(parsed.command, "30")
        self.assertEqual(parsed.data, "05")

    def test_light_effect_is_published_to_rgb_topic(self) -> None:
        response = self.bridge.handle_frame(frame("30", "03"))
        self.assertEqual(response, "OK\n")
        self.assertEqual(self.publisher.light_messages, [("/RGBLight", 3, 3)])

    def test_invalid_light_effect_is_rejected(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "unsupported light effect"):
            self.bridge.handle_frame(frame("30", "07"))

    def test_show_start_and_stop_commands(self) -> None:
        self.bridge.handle_frame(frame("31"))
        self.bridge.handle_frame(frame("32"))
        self.assertEqual(self.show.started, 1)
        self.assertEqual(self.show.stopped, [True])

    def test_manual_motion_cancels_show(self) -> None:
        self.show.is_running = True
        self.bridge.handle_frame(frame("15", "01"))
        self.assertEqual(self.show.stopped, [True])
        self.assertEqual(len(self.publisher.motion_messages), 1)


if __name__ == "__main__":
    unittest.main()
