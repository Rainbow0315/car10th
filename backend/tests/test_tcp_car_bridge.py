from __future__ import annotations

import sys
import time
import unittest

from apps.tcp_car_bridge.main import ExternalCommandError, ProtocolError, TcpCarBridge, parse_frame


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
        self.stop_delay = 0.0
        self.closed = False

    def publish_int32(self, topic_name: str, value: int, repeat: int = 3) -> None:
        self.light_messages.append((topic_name, value, repeat))

    def publish_for_duration(self, **kwargs) -> None:
        self.motion_messages.append(kwargs)

    def stop(self) -> None:
        if self.stop_delay > 0:
            time.sleep(self.stop_delay)
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


class FakeAudio:
    def __init__(self) -> None:
        self.played = []
        self.stopped = 0

    def play(self, track_index: int = 0, volume_percent: int = 80) -> None:
        self.played.append((track_index, volume_percent))

    def stop(self) -> None:
        self.stopped += 1


class TcpCarBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.publisher = FakePublisher()
        self.bridge = TcpCarBridge(publisher=self.publisher)
        self.show = FakeShow()
        self.bridge.show = self.show
        self.audio = FakeAudio()
        self.bridge.audio = self.audio

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

    def test_stop_command_returns_without_waiting_for_ros_stop(self) -> None:
        self.publisher.stop_delay = 0.5
        start = time.monotonic()
        response = self.bridge.handle_frame(frame("15", "00"))
        elapsed = time.monotonic() - start
        self.assertEqual(response, "OK\n")
        self.assertLess(elapsed, 0.2)

    def test_audio_command_does_not_cancel_light_show(self) -> None:
        self.show.is_running = True
        response = self.bridge.handle_frame(frame("33"))
        self.assertEqual(response, "OK\n")
        self.assertEqual(self.audio.played, [(0, 80)])
        self.assertEqual(self.show.stopped, [])

    def test_tracking_start_runs_external_command(self) -> None:
        self.show.is_running = True
        self.bridge.track_stop_command = f'"{sys.executable}" -c "print(\'tracking pre-stop\')"'
        self.bridge.track_start_command = f'"{sys.executable}" -c "print(\'tracking start\')"'
        response = self.bridge.handle_frame(frame("63"))
        if self.bridge._tracking_process is not None:
            self.bridge._tracking_process.wait(timeout=2)
        self.assertEqual(response, "OK\n")
        self.assertEqual(self.show.stopped, [True])

    def test_tracking_stop_runs_external_command_and_stops_ros_motion(self) -> None:
        self.bridge.track_stop_command = f'"{sys.executable}" -c "print(\'tracking stop\')"'
        response = self.bridge.handle_frame(frame("64"))
        self.assertEqual(response, "OK\n")
        self.assertEqual(self.publisher.stop_count, 1)

    def test_empty_tracking_start_command_is_rejected(self) -> None:
        self.bridge.track_stop_command = f'"{sys.executable}" -c "print(\'tracking pre-stop\')"'
        self.bridge.track_start_command = ""
        with self.assertRaisesRegex(ExternalCommandError, "tracking start command is empty"):
            self.bridge.handle_frame(frame("63"))

    def test_audio_command_accepts_track_and_volume(self) -> None:
        response = self.bridge.handle_frame(frame("33", "023C"))
        self.assertEqual(response, "OK\n")
        self.assertEqual(self.audio.played, [(2, 60)])


if __name__ == "__main__":
    unittest.main()
