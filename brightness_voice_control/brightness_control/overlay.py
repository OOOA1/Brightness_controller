"""Independent click-through screen overlays and interruptible animations."""
import logging
import sys
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from .identity import device_details
from .model import MonitorState, clamp, default_display_name, fill_default_profiles

LOG = logging.getLogger(__name__)


class Dimmer(QWidget):
    def __init__(self, screen):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowTitle('Brightness Voice Control dimmer')
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        screen.geometryChanged.connect(self.setGeometry)
        self.show()
        if sys.platform == 'win32':
            import ctypes
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get_style = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
            set_style = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
            set_style(hwnd, -20, get_style(hwnd, -20) | 0x20 | 0x80 | 0x08000000)
        self.hide()

    def set_brightness(self, value: float):
        opacity = .98 * (1 - clamp(value) / 100)
        self.setWindowOpacity(opacity)
        if opacity < .001:
            self.hide()
        else:
            self.setGeometry(self.screen().geometry())
            if not self.isVisible():
                self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))


class MonitorManager(QObject):
    changed = Signal()
    level_changed = Signal(str, float)
    overlay_shown = Signal()
    unassigned = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.layers = {}        # stable ID -> Dimmer
        self.states = {}        # stable ID -> MonitorState
        self.screens = {}       # stable ID -> QScreen
        self.timers = {}
        self._preview_original = {}
        self.ordinals = {}      # stable ID -> Windows/QScreen ordinal
        self._ambiguous = set()
        app = QGuiApplication.instance()
        app.screenAdded.connect(self.refresh)
        app.screenRemoved.connect(self.refresh)
        self.refresh()

    @property
    def values(self):
        return {key: state.current_brightness for key, state in self.states.items()}

    def refresh(self, *_):
        screens = sorted(QGuiApplication.screens(), key=lambda s: (s.geometry().x(), s.geometry().y()))
        details = [device_details(screen) for screen in screens]
        counts = {}
        for item in details:
            counts[item['stable_id']] = counts.get(item['stable_id'], 0) + 1
        active = set()
        self.ordinals = {}
        self._ambiguous.clear()
        for index, (screen, info) in enumerate(zip(screens, details), 1):
            stable = info['stable_id']
            if counts[stable] > 1:
                # Duplicate EDID/path cannot identify the same physical device
                # after a port swap; keep UI available but require reassignment.
                stable = f"ambiguous:{stable}:{screen.name()}:{index}"
                self._ambiguous.add(stable)
            active.add(stable)
            self.ordinals[stable] = index
            self.config['monitor_info'][stable] = info
            previous_screen = self.screens.get(stable)
            self.screens[stable] = screen
            if stable in self.layers and previous_screen != screen:
                self.layers[stable].close()
                try:
                    self.layers[stable] = Dimmer(screen)
                    self.layers[stable].set_brightness(self.states[stable].current_brightness)
                except Exception:
                    LOG.exception('Could not rebind overlay for %s', stable)
                    self._stop_timer(stable)
                    self.layers.pop(stable, None)
                    self.states.pop(stable, None)
            if stable not in self.layers:
                try:
                    layer = Dimmer(screen)
                    raw = self.config['brightness'].get(stable,
                        self.config['brightness'].get(screen.name(), 100))
                    if not self.config['remember_brightness']:
                        raw = 100
                    value = clamp(raw)
                    previous = self.config['previous_nonzero'].get(
                        stable, self.config['previous_nonzero'].get(screen.name(), value or 100))
                    self.states[stable] = MonitorState(value, value, clamp(previous))
                    self.layers[stable] = layer
                    layer.set_brightness(value)
                    LOG.info('Monitor connected: %s, %s', stable, info['friendly_name'])
                    if stable not in self.config['monitors'] and screen.name() in self.config['monitors']:
                        self.config['monitors'][stable] = self.config['monitors'].pop(screen.name())
                        if screen.name() in self.config['brightness']:
                            self.config['brightness'][stable] = self.config['brightness'].pop(screen.name())
                        if screen.name() in self.config['previous_nonzero']:
                            self.config['previous_nonzero'][stable] = self.config['previous_nonzero'].pop(screen.name())
                        for profile in self.config['profiles']:
                            values = profile.get('monitor_values', {})
                            if screen.name() in values:
                                values[stable] = values.pop(screen.name())
                except Exception:
                    LOG.exception('Could not create overlay for %s', stable)
        for key in list(self.layers):
            if key not in active:
                timer = self.timers.pop(key, None)
                if timer:
                    timer.stop()
                self.layers.pop(key).close()
                self.states.pop(key, None)
                self.screens.pop(key, None)
                LOG.info('Monitor disconnected: %s', key)
        self._default_names()
        self.changed.emit()

    def _default_names(self):
        mapping = self.config['monitors']
        ordered = self.active_monitor_ids()
        for index, key in enumerate(ordered, 1):
            if key in self._ambiguous:
                self.unassigned.emit(key)
                continue
            if key not in mapping:
                name = default_display_name(index, len(ordered))
                mapping[key] = {'display_name': name, 'voice_aliases': []}
            for profile in self.config['profiles']:
                values = profile.get('monitor_values', {})
                legacy = profile.get('legacy_monitor_values', {})
                name = self.display_name(key)
                if name in legacy and key not in values:
                    values[key] = legacy.pop(name)
        fill_default_profiles(self.config['profiles'], ordered)

    def active_monitor_ids(self):
        return sorted(self.states, key=lambda k: (self.screens[k].geometry().x(),
                                                 self.screens[k].geometry().y()))

    def ordered_monitors(self):
        return [(key, self.display_name(key), self.states[key].current_brightness)
                for key in self.active_monitor_ids()]

    def display_name(self, key):
        return self.config['monitors'].get(key, {}).get('display_name', f'Монитор {self.ordinals.get(key, 0)}')

    def aliases(self, key):
        return self.config['monitors'].get(key, {}).get('voice_aliases', [])

    def named(self):
        return {self.display_name(k): self.states[k].current_brightness for k in self.active_monitor_ids()}

    def key_for(self, target):
        if target is None:
            return self.active_monitor_ids()
        if target.startswith('#'):
            return [key for key, idx in self.ordinals.items() if idx == int(target[1:])]
        if target in self.states:
            return [target]
        return [key for key in self.states if self.display_name(key) == target]

    def target_values(self, target):
        return {key: self.states[key].target_brightness for key in self.key_for(target)}

    def _persist(self, key):
        state = self.states[key]
        self.config['brightness'][key] = round(state.target_brightness)
        self.config['previous_nonzero'][key] = round(state.previous_nonzero_brightness)

    def _stop_timer(self, key):
        timer = self.timers.pop(key, None)
        if timer:
            timer.stop()
            timer.deleteLater()

    def preview(self, key, value):
        if key not in self.states:
            return
        self._stop_timer(key)
        state = self.states[key]
        state.preview(value)
        if key in self._preview_original:
            initial, previous = self._preview_original[key]
            state.previous_nonzero_brightness = (initial if initial > 0 else previous) if state.target_brightness == 0 else state.target_brightness
        was_hidden = not self.layers[key].isVisible()
        self.layers[key].set_brightness(self.states[key].current_brightness)
        if was_hidden and self.layers[key].isVisible():
            self.overlay_shown.emit()
        self.level_changed.emit(key, self.states[key].current_brightness)

    def begin_preview(self, key):
        if key in self.states:
            state = self.states[key]
            self._preview_original[key] = (state.target_brightness, state.previous_nonzero_brightness)

    def commit_preview(self, key):
        if key in self.states:
            self._preview_original.pop(key, None)
            self._persist(key)

    def set_value(self, key, value, duration=None):
        if key not in self.states:
            return
        self._stop_timer(key)
        state = self.states[key]
        start = state.current_brightness
        state.set_target(value)
        self._persist(key)
        seconds = self.config['duration'] if duration is None else duration
        if seconds <= 0 or abs(start - state.target_brightness) < .001:
            self.preview(key, state.target_brightness)
            self.changed.emit()
            return
        steps = max(1, round(seconds * 60))
        timer = QTimer(self)
        tick = 0

        def advance():
            nonlocal tick
            if key not in self.states:
                timer.stop()
                return
            tick += 1
            fraction = min(1., tick / steps)
            smooth = fraction * fraction * (3 - 2 * fraction)
            state.current_brightness = start + (state.target_brightness - start) * smooth
            was_hidden = not self.layers[key].isVisible()
            self.layers[key].set_brightness(state.current_brightness)
            if was_hidden and self.layers[key].isVisible():
                self.overlay_shown.emit()
            self.level_changed.emit(key, state.current_brightness)
            if tick >= steps:
                self._stop_timer(key)
                state.current_brightness = state.target_brightness
                self.changed.emit()

        self.timers[key] = timer
        timer.timeout.connect(advance)
        timer.start(max(10, round(seconds * 1000 / steps)))

    def set_named(self, name, value, duration=None):
        for key in self.key_for(name):
            self.set_value(key, value, duration)

    def shutdown(self):
        for key in list(self.timers):
            self._stop_timer(key)
        for layer in self.layers.values():
            layer.close()
        self.layers.clear()
