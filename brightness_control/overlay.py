import sys
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget


class Dimmer(QWidget):
    def __init__(self, screen):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Paint an opaque black surface. The window compositor applies the
        # brightness-dependent opacity to the entire top-level window below.
        self.setWindowTitle("Brightness Voice Control dimmer")
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.opacity = 0.0
        screen.geometryChanged.connect(self.setGeometry)
        self.show()
        if sys.platform == "win32":
            import ctypes
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get_style = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
            set_style = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
            # Qt controls layered-window opacity; these flags only keep the
            # overlay click-through and prevent it from taking focus.
            set_style(hwnd, -20, get_style(hwnd, -20) | 0x20 | 0x80 | 0x08000000)
        self.hide()  # A 100% screen must not reserve an invisible topmost window.

    def set_brightness(self, value: float):
        self.opacity = .97 * (1 - max(0, min(100, value)) / 100)
        self.setWindowOpacity(self.opacity)
        if self.opacity < .001:
            self.hide()
        else:
            self.setGeometry(self.screen().geometry())
            self.show()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))


class MonitorManager(QObject):
    changed = Signal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.layers = {}
        self.values = {}
        self.animations = {}
        self.timers = {}
        app = QGuiApplication.instance()
        app.screenAdded.connect(self.refresh)
        app.screenRemoved.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        screens = QGuiApplication.screens()[:3]
        active = {s.name() for s in screens}
        for key in list(self.layers):
            if key not in active:
                timer = self.timers.pop(key, None)
                if timer:
                    timer.stop()
                self.animations.pop(key, None)
                self.layers.pop(key).close()
                self.values.pop(key, None)
        for screen in screens:
            key = screen.name()
            if key not in self.layers:
                try:
                    self.layers[key] = Dimmer(screen)
                    raw = self.config["brightness"].get(key, 100) if self.config["remember_brightness"] else 100
                    self.values[key] = max(0, min(100, int(raw)))
                    self.layers[key].set_brightness(self.values[key])
                except Exception:
                    # Other screens continue working if one layer fails.
                    continue
        self._default_names(screens)
        self.changed.emit()

    def _default_names(self, screens):
        mapping = self.config["monitors"]
        used = {mapping[key] for key in self.layers if key in mapping}
        for screen in sorted(screens, key=lambda s: s.geometry().center().x()):
            if screen.name() in self.layers and screen.name() not in mapping:
                for name in ("Левый", "Центральный", "Правый"):
                    if name not in used:
                        mapping[screen.name()] = name
                        used.add(name)
                        break

    def named(self):
        return {self.config["monitors"].get(key, key): value for key, value in self.values.items()}

    def set_value(self, key, value, duration=None):
        if key not in self.layers:
            return
        value = max(0, min(100, int(value)))
        start = float(self.animations.get(key, self.values[key]))
        old = self.timers.pop(key, None)
        if old:
            old.stop()
        seconds = self.config["duration"] if duration is None else duration
        steps = max(1, round(float(seconds) * 60))
        timer = QTimer(self)
        tick = 0

        def advance():
            nonlocal tick
            tick += 1
            fraction = min(1, tick / steps)
            now = start + (value - start) * (fraction * fraction * (3 - 2 * fraction))
            self.animations[key] = now
            self.layers[key].set_brightness(now)
            if tick >= steps:
                timer.stop()
                self.timers.pop(key, None)
                self.animations.pop(key, None)
                self.values[key] = value
                self.config["brightness"][key] = value
                self.changed.emit()

        self.timers[key] = timer
        timer.timeout.connect(advance)
        timer.start(max(10, round(float(seconds) * 1000 / steps)))

    def set_named(self, name, value):
        for key in self.values:
            if name is None or self.config["monitors"].get(key) == name:
                self.set_value(key, value)
