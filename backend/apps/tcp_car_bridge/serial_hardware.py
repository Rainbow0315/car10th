from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional, Sequence, Tuple


DEVICE_ID = 0xFC
PACKET_HEAD = 0xFF
CHECKSUM_COMPLEMENT = 257 - DEVICE_ID
FUNC_LIGHT_CTRL = 0x07

LIGHT_OFF = 0
LIGHT_ON = 1
LIGHT_LEFT = 2
LIGHT_RIGHT = 3

LightPattern = Sequence[Tuple[int, float]]

LIGHT_PATTERNS: Dict[int, LightPattern] = {
    1: ((LIGHT_LEFT, 0.28), (LIGHT_RIGHT, 0.28)),
    2: ((LIGHT_ON, 0.18), (LIGHT_OFF, 0.18)),
    3: ((LIGHT_ON, 0.65), (LIGHT_OFF, 0.45)),
    4: (
        (LIGHT_LEFT, 0.24),
        (LIGHT_ON, 0.24),
        (LIGHT_RIGHT, 0.24),
        (LIGHT_OFF, 0.18),
    ),
    5: (
        (LIGHT_LEFT, 0.11),
        (LIGHT_OFF, 0.07),
        (LIGHT_RIGHT, 0.19),
        (LIGHT_ON, 0.09),
        (LIGHT_OFF, 0.14),
        (LIGHT_LEFT, 0.08),
        (LIGHT_RIGHT, 0.16),
        (LIGHT_OFF, 0.10),
    ),
}


def build_packet(function_code: int, data: Sequence[int]) -> bytes:
    command = [PACKET_HEAD, DEVICE_ID, 0, function_code, *data]
    command[2] = len(command) - 1
    command.append((sum(command) + CHECKSUM_COMPLEMENT) & 0xFF)
    return bytes(command)


class SerialCarHardware:
    def __init__(
        self,
        port: str = "/dev/myserial",
        baudrate: int = 115200,
        serial_factory: Optional[Callable[..., object]] = None,
    ) -> None:
        if serial_factory is None:
            import serial

            serial_factory = serial.Serial
        self._serial = serial_factory(port=port, baudrate=baudrate, timeout=1)
        self._write_lock = threading.Lock()

    def set_light_scene(self, scene: int) -> None:
        if scene == LIGHT_OFF:
            self._set_light(0, 0)
        elif scene == LIGHT_ON:
            self._set_light(0, 1)
        elif scene == LIGHT_LEFT:
            self._set_light(0, 0)
            self._set_light(1, 1)
        elif scene == LIGHT_RIGHT:
            self._set_light(0, 0)
            self._set_light(2, 1)
        else:
            raise ValueError(f"unsupported light scene: {scene}")

    def close(self) -> None:
        with self._write_lock:
            if getattr(self._serial, "is_open", True):
                self._serial.close()

    def _set_light(self, side: int, state: int) -> None:
        self._write(build_packet(FUNC_LIGHT_CTRL, (side, state)))

    def _write(self, packet: bytes) -> None:
        with self._write_lock:
            self._serial.write(packet)
            self._serial.flush()
            time.sleep(0.003)


class HeadlightEffectController:
    def __init__(self, hardware: SerialCarHardware) -> None:
        self._hardware = hardware
        self._lock = threading.Lock()
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None

    def set_effect(self, effect: int) -> None:
        self.stop(turn_off=False)
        if effect == 0:
            self._hardware.set_light_scene(LIGHT_OFF)
            return
        pattern = LIGHT_PATTERNS.get(effect)
        if pattern is None:
            raise ValueError(f"unsupported light effect: {effect}")

        stop_event = threading.Event()
        worker = threading.Thread(
            target=self._run,
            args=(pattern, stop_event),
            name="headlight-effect",
            daemon=True,
        )
        with self._lock:
            self._stop_event = stop_event
            self._thread = worker
        worker.start()

    def stop(self, turn_off: bool = True) -> None:
        with self._lock:
            stop_event = self._stop_event
            worker = self._thread
            self._stop_event = None
            self._thread = None
        if stop_event is not None:
            stop_event.set()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        if turn_off:
            self._hardware.set_light_scene(LIGHT_OFF)

    def _run(self, pattern: LightPattern, stop_event: threading.Event) -> None:
        try:
            while not stop_event.is_set():
                for scene, duration in pattern:
                    if stop_event.is_set():
                        return
                    self._hardware.set_light_scene(scene)
                    if stop_event.wait(duration):
                        return
        finally:
            with self._lock:
                if self._stop_event is stop_event:
                    self._stop_event = None
                    self._thread = None
