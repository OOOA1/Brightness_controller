"""Mutable physical brightness state, independent of GUI and audio."""
from dataclasses import dataclass


def clamp(value: float) -> float:
    return min(100., max(0., float(value)))


def default_display_name(index: int, count: int) -> str:
    if count == 1:
        return 'Основной'
    if count == 2:
        return 'Левый' if index == 1 else 'Правый'
    return f'Монитор {index}'


def fill_default_profiles(profiles: list[dict], monitor_ids: list[str]) -> None:
    for profile in profiles:
        value = {'sleep': 10, 'work': 100}.get(profile.get('id'))
        if value is not None:
            for monitor_id in monitor_ids:
                profile.setdefault('monitor_values', {}).setdefault(monitor_id, value)


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
