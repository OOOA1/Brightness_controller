"""Mutable physical brightness state, independent of GUI and audio."""
from dataclasses import dataclass


def clamp(value: float) -> float:
    return min(100., max(0., float(value)))


@dataclass
class MonitorState:
    current_brightness: float = 100.
    target_brightness: float = 100.
    previous_nonzero_brightness: float = 100.

    def set_target(self, value: float) -> None:
        new = clamp(value)
        if new == 0 and self.target_brightness > 0:
            self.previous_nonzero_brightness = self.target_brightness
        elif new > 0:
            self.previous_nonzero_brightness = new
        self.target_brightness = new

    def preview(self, value: float) -> None:
        self.set_target(value)
        self.current_brightness = self.target_brightness

    def restore(self) -> float:
        return clamp(self.previous_nonzero_brightness or 100)
