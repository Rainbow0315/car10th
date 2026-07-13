from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional, Sequence


@dataclass(frozen=True)
class LightStep:
    light_scene: int
    duration: float


# Equal beats first, then deliberately uneven flashes.
REGULAR_STEPS: Sequence[LightStep] = (
    LightStep(2, 0.24),
    LightStep(3, 0.24),
    LightStep(1, 0.24),
    LightStep(0, 0.24),
    LightStep(2, 0.24),
    LightStep(3, 0.24),
    LightStep(1, 0.24),
    LightStep(0, 0.24),
)

IRREGULAR_STEPS: Sequence[LightStep] = (
    LightStep(2, 0.11),
    LightStep(0, 0.07),
    LightStep(3, 0.19),
    LightStep(1, 0.09),
    LightStep(0, 0.14),
    LightStep(2, 0.08),
    LightStep(3, 0.16),
    LightStep(0, 0.10),
    LightStep(1, 0.22),
    LightStep(0, 0.06),
    LightStep(2, 0.13),
    LightStep(3, 0.18),
    LightStep(0, 0.12),
)


class LightShow:
    def __init__(
        self,
        set_light_scene: Callable[[int], None],
        steps: Sequence[LightStep] = (*REGULAR_STEPS, *IRREGULAR_STEPS),
    ) -> None:
        self._set_light_scene = set_light_scene
        self._steps = tuple(steps)
        self._lock = threading.Lock()
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self.stop()
        stop_event = threading.Event()
        worker = threading.Thread(
            target=self._run,
            args=(stop_event,),
            name="light-show",
            daemon=True,
        )
        with self._lock:
            self._stop_event = stop_event
            self._thread = worker
        worker.start()

    def stop(self, turn_off_lights: bool = True) -> None:
        with self._lock:
            stop_event = self._stop_event
            worker = self._thread
            self._stop_event = None
            self._thread = None
        if stop_event is not None:
            stop_event.set()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        if turn_off_lights:
            self._set_light_scene(0)

    def _run(self, stop_event: threading.Event) -> None:
        try:
            for step in self._steps:
                if stop_event.is_set():
                    break
                self._set_light_scene(step.light_scene)
                if stop_event.wait(step.duration):
                    break
        finally:
            self._set_light_scene(0)
            with self._lock:
                if self._stop_event is stop_event:
                    self._stop_event = None
                    self._thread = None
