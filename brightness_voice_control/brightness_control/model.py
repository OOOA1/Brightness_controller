"""Mutable physical brightness state, independent of GUI and audio."""
from dataclasses import dataclass
import re


def clamp(value: float) -> float:
    return min(100., max(0., float(value)))


def default_display_name(index: int, count: int) -> str:
    if count == 1:
        return 'Основной'
    if count == 2:
        return 'Левый' if index == 1 else 'Правый'
    return f'Монитор {index}'


def inferred_name_source(name: str) -> str:
    return ('auto' if name in ('Основной', 'Левый', 'Правый') or
            re.fullmatch(r'Монитор [1-9]\d*', name) else 'user')


def refresh_auto_names(records: dict, ordered_ids: list[str]) -> None:
    """Recalculate only generated names when the active topology changes."""
    for index, monitor_id in enumerate(ordered_ids, 1):
        record = records.setdefault(monitor_id, {
            'display_name': default_display_name(index, len(ordered_ids)),
            'name_source': 'auto', 'voice_aliases': [],
        })
        if record.get('name_source') == 'auto':
            record['display_name'] = default_display_name(index, len(ordered_ids))


def common_brightness(values) -> int | None:
    rounded = [round(value) for value in values]
    return rounded[0] if rounded and all(value == rounded[0] for value in rounded) else None


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
