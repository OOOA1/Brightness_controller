from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                              QSlider, QVBoxLayout, QWidget)


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
        self.rows_layout = QVBoxLayout()
        self.outer.addLayout(self.rows_layout)
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

    def rebuild(self, values, profiles=()):
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.sliders.clear()
        for name in ('Левый', 'Центральный', 'Правый', 'Все мониторы'):
            if name not in values and name != 'Все мониторы':
                # Keep disconnected screens visible instead of silently hiding them.
                online = False
                value = 100
            else:
                online = True
                value = values.get(name, min(values.values(), default=100))
            frame = QFrame()
            frame.setObjectName('card')
            block = QVBoxLayout(frame)
            block.setContentsMargins(15, 10, 15, 10)
            line = QHBoxLayout()
            line.addWidget(QLabel(name))
            line.addStretch()
            amount = QLabel(f'{round(value)}%' if online else 'Не подключён')
            line.addWidget(amount)
            block.addLayout(line)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(round(value))
            slider.setEnabled(online)
            slider.sliderPressed.connect(lambda n=name: self.preview_started.emit(n))
            slider.sliderMoved.connect(lambda v, n=name, a=amount: (
                a.setText(f'{v}%'), self.preview_moved.emit(n, v)))
            slider.sliderReleased.connect(lambda n=name: self.preview_finished.emit(n))
            slider.valueChanged.connect(lambda v, n=name, s=slider, a=amount:
                self._keyboard_changed(n, v, s, a))
            block.addWidget(slider)
            self.rows_layout.addWidget(frame)
            self.sliders[name] = slider
        while self.profiles.count():
            item = self.profiles.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for profile in profiles[:3]:
            button = QPushButton(profile.get('name', 'Профиль'))
            button.clicked.connect(lambda _, pid=profile['id']: self.profile_requested.emit(pid))
            self.profiles.addWidget(button)

    def update_level(self, name, value):
        slider = self.sliders.get(name)
        if slider and not slider.isSliderDown():
            slider.blockSignals(True)
            slider.setValue(round(value))
            slider.blockSignals(False)
            frame = slider.parent()
            label = frame.layout().itemAt(0).layout().itemAt(2).widget()
            label.setText(f'{round(value)}%')

    def _keyboard_changed(self, name, value, slider, label):
        if slider.hasFocus() and not slider.isSliderDown():
            label.setText(f'{value}%')
            self.preview_started.emit(name)
            self.preview_moved.emit(name, value)
            self.preview_finished.emit(name)

    def show_near_cursor(self):
        self.adjustSize()
        cursor = QCursor.pos()
        area = self.screen().availableGeometry()
        self.move(max(area.left(), min(cursor.x() - self.width(), area.right() - self.width())),
                  max(area.top(), min(cursor.y() - self.height(), area.bottom() - self.height())))
        self.show()
