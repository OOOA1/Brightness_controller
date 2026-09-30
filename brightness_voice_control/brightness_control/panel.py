from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                              QSlider, QVBoxLayout, QWidget, QScrollArea)
from .model import common_brightness


class TrayPanel(QDialog):
    settings_requested = Signal()
    voice_toggled = Signal(bool)
    quit_requested = Signal()
    preview_started = Signal(str)
    preview_moved = Signal(str, int)
    preview_finished = Signal(str)
    preset_requested = Signal(int)
    profile_requested = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName('panel')
        self.setWindowTitle('Brightness Voice Control')
        self.setFixedWidth(405)
        self.outer = QVBoxLayout(self)
        self.outer.setSpacing(14)
        self.outer.setContentsMargins(20, 20, 20, 20)
        header = QHBoxLayout()
        title = QLabel('Brightness Voice Control')
        title.setObjectName('section')
        header.addWidget(title)
        settings = QPushButton('Настройки')
        settings.clicked.connect(lambda: (self.hide(), self.settings_requested.emit()))
        header.addWidget(settings)
        self.outer.addLayout(header)
        self.status = QLabel('● Голос активен')
        self.status.setObjectName('muted')
        self.outer.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMaximumHeight(440)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rows_widget = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.rows_widget)
        self.outer.addWidget(self.scroll)
        self.sliders = {}
        presets = QHBoxLayout()
        for value in (10, 25, 50, 100):
            button = QPushButton(f'{value}%')
            button.clicked.connect(lambda _, v=value: self.preset_requested.emit(v))
            presets.addWidget(button)
        self.outer.addLayout(presets)
        self.profiles = QHBoxLayout()
        self.outer.addLayout(self.profiles)
        footer = QHBoxLayout()
        self.voice_button = QPushButton('Выключить голос')
        self.voice_button.clicked.connect(self._toggle)
        footer.addWidget(self.voice_button)
        exit_button = QPushButton('Выход')
        exit_button.clicked.connect(self.quit_requested.emit)
        footer.addWidget(exit_button)
        self.outer.addLayout(footer)
        self.voice_enabled = True

    def _toggle(self):
        self.voice_toggled.emit(not self.voice_enabled)

    def set_voice_status(self, text, enabled):
        self.status.setText(text)
        self.voice_enabled = enabled
        self.voice_button.setText('Выключить голос' if enabled else 'Включить голос')

    def rebuild(self, monitors, profiles=()):
        position = self.scroll.verticalScrollBar().value()
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.sliders.clear()
        rows = list(monitors)
        if len(rows) > 1:
            rows.append(('__all__', 'Все мониторы', common_brightness(v for _, _, v in monitors)))
        for monitor_id, name, value in rows:
            frame = QFrame()
            frame.setObjectName('card')
            block = QVBoxLayout(frame)
            block.setContentsMargins(15, 10, 15, 10)
            line = QHBoxLayout()
            line.addWidget(QLabel(name))
            line.addStretch()
            amount = QLabel(f'{round(value)}%' if value is not None else '—')
            line.addWidget(amount)
            block.addLayout(line)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(round(value) if value is not None else 50)
            slider.sliderPressed.connect(lambda k=monitor_id: self.preview_started.emit(k))
            slider.sliderMoved.connect(lambda v, k=monitor_id, a=amount: (
                a.setText(f'{v}%'), self.preview_moved.emit(k, v)))
            slider.sliderReleased.connect(lambda k=monitor_id: self.preview_finished.emit(k))
            slider.valueChanged.connect(lambda v, k=monitor_id, s=slider, a=amount:
                self._keyboard_changed(k, v, s, a))
            block.addWidget(slider)
            self.rows_layout.addWidget(frame)
            self.sliders[monitor_id] = slider
        self.scroll.verticalScrollBar().setValue(position)
        while self.profiles.count():
            item = self.profiles.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for profile in profiles[:3]:
            button = QPushButton(profile.get('name', 'Профиль'))
            button.clicked.connect(lambda _, pid=profile['id']: self.profile_requested.emit(pid))
            self.profiles.addWidget(button)

    def update_level(self, monitor_id, value):
        slider = self.sliders.get(monitor_id)
        if slider and not slider.isSliderDown():
            slider.blockSignals(True)
            slider.setValue(round(value))
            slider.blockSignals(False)
            frame = slider.parent()
            label = frame.layout().itemAt(0).layout().itemAt(2).widget()
            label.setText(f'{round(value)}%')
        common = self.sliders.get('__all__')
        individual = [item for key, item in self.sliders.items() if key != '__all__']
        if common and individual and not common.isSliderDown():
            values = [item.value() for item in individual]
            shared = common_brightness(values)
            common.blockSignals(True)
            if shared is not None:
                common.setValue(shared)
            common.blockSignals(False)
            frame = common.parent()
            frame.layout().itemAt(0).layout().itemAt(2).widget().setText(
                f'{shared}%' if shared is not None else '—')

    def _keyboard_changed(self, name, value, slider, label):
        if slider.hasFocus() and not slider.isSliderDown():
            label.setText(f'{value}%')
            self.preview_started.emit(name)
            self.preview_moved.emit(name, value)
            self.preview_finished.emit(name)

    def show_near_cursor(self):
        self.adjustSize()
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        self.setScreen(screen)
        area = screen.availableGeometry()
        self.move(max(area.left(), min(cursor.x() - self.width(), area.right() - self.width())),
                  max(area.top(), min(cursor.y() - self.height(), area.bottom() - self.height())))
        self.show()
