from __future__ import annotations

import time
import unittest

from apps.tcp_car_bridge.light_show import (
    IRREGULAR_STEPS,
    REGULAR_STEPS,
    LightShow,
    LightStep,
)


class LightShowTests(unittest.TestCase):
    def test_show_contains_regular_and_irregular_light_beats(self) -> None:
        self.assertEqual({step.duration for step in REGULAR_STEPS}, {0.24})
        self.assertGreater(len({step.duration for step in IRREGULAR_STEPS}), 8)
        self.assertEqual(
            {step.light_scene for step in (*REGULAR_STEPS, *IRREGULAR_STEPS)},
            {0, 1, 2, 3},
        )

    def test_show_finishes_with_lights_off(self) -> None:
        scenes = []
        show = LightShow(
            set_light_scene=scenes.append,
            steps=(LightStep(1, 0.01),),
        )
        show.start()
        deadline = time.monotonic() + 1.0
        while show.is_running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(show.is_running)
        self.assertEqual(scenes, [0, 1, 0])

    def test_stop_interrupts_and_turns_lights_off(self) -> None:
        scenes = []
        show = LightShow(
            set_light_scene=scenes.append,
            steps=(LightStep(1, 5.0),),
        )
        show.start()
        time.sleep(0.02)
        show.stop()
        self.assertFalse(show.is_running)
        self.assertEqual(scenes[-1], 0)


if __name__ == "__main__":
    unittest.main()
