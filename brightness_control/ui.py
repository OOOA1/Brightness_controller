from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider,
    QVBoxLayout, QWidget)


class TrayPanel(QDialog):
    settings_requested = Signal()
    voice_toggled = Signal(bool)
    quit_requested = Signal()
    value_changed = Signal(str, int)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Brightness Voice Control")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Brightness Voice Control"))
        self.rows = {}
        self.row_layout = QVBoxLayout()
        layout.addLayout(self.row_layout)
        self.voice_box = QCheckBox("Голосовое управление")
        self.voice_box.toggled.connect(self.voice_toggled.emit)
        layout.addWidget(self.voice_box)
        settings = QPushButton("Настройки")
        settings.clicked.connect(lambda: (self.hide(), self.settings_requested.emit()))
        layout.addWidget(settings)
        quit_button = QPushButton("Выход")
        quit_button.clicked.connect(self.quit_requested.emit)
        layout.addWidget(quit_button)
        self.setMinimumWidth(340)

    def rebuild(self, values):
        while self.row_layout.count():
            item = self.row_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows.clear()
        for name, value in values.items():
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            label = QLabel(name)
            label.setFixedWidth(95)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(value)
            number = QLabel(f"{value}%")
            slider.valueChanged.connect(lambda v, n=name, l=number: (l.setText(f"{v}%"), self.value_changed.emit(n, v)))
            line.addWidget(label)
            line.addWidget(slider)
            line.addWidget(number)
            self.row_layout.addWidget(row)
            self.rows[name] = (slider, number)

    def show_near_cursor(self):
        self.adjustSize()
        pos = QCursor.pos()
        screen = self.screen() or self.windowHandle().screen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(pos.x() - self.width(), area.right() - self.width())),
                  max(area.top(), min(pos.y() - self.height(), area.bottom() - self.height())))
        self.show()


class Notice(QWidget):
    decision = Signal(bool)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("QWidget {background:#24252b;color:white;border-radius:8px} QPushButton {padding:6px;background:#45577d}")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Brightness Voice Control"))
        self.message = QLabel()
        layout.addWidget(self.message)
        row = QHBoxLayout()
        for caption, yes in (("Да", True), ("Нет", False)):
            button = QPushButton(caption)
            button.clicked.connect(lambda _, flag=yes: self.decision.emit(flag))
            row.addWidget(button)
        self.buttons = QWidget()
        self.buttons.setLayout(row)
        layout.addWidget(self.buttons)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_message(self, message, confirm=False, timeout=3500):
        self.message.setText(message)
        self.buttons.setVisible(confirm)
        self.adjustSize()
        screen = self.screen() or self.windowHandle().screen()
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)
        self.show()
        self.timer.stop()
        if not confirm:
            self.timer.start(timeout)


class Settings(QDialog):
    def __init__(self, manager, config, voice, speaker, save_callback):
        super().__init__()
        self.setWindowTitle("Настройки — Brightness Voice Control")
        self.manager, self.config, self.voice, self.speaker = manager, config, voice, speaker
        self.save_callback = save_callback
        outer = QVBoxLayout(self)
        monitors = QGroupBox("Мониторы")
        form = QFormLayout(monitors)
        self.assignments = {}
        for key in manager.layers:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            choice = QComboBox()
            choice.addItems(["Левый", "Центральный", "Правый"])
            choice.setCurrentText(config['monitors'].get(key, 'Левый'))
            test = QPushButton("Тест")
            test.clicked.connect(lambda _, k=key: self._test_monitor(k))
            line.addWidget(choice)
            line.addWidget(test)
            form.addRow(key, row)
            self.assignments[key] = choice
        outer.addWidget(monitors)
        voice_group = QGroupBox("Голос")
        form = QFormLayout(voice_group)
        self.enabled = QCheckBox("Включить распознавание")
        self.enabled.setChecked(config['voice_enabled'])
        form.addRow(self.enabled)
        self.microphone = QComboBox()
        self.microphone.addItem("По умолчанию", None)
        try:
            for index, name in voice.devices():
                self.microphone.addItem(name, index)
        except Exception:
            pass
        index = self.microphone.findData(config['microphone'])
        self.microphone.setCurrentIndex(max(0, index))
        form.addRow("Микрофон", self.microphone)
        mic_row = QWidget()
        mic_line = QHBoxLayout(mic_row)
        mic_line.setContentsMargins(0, 0, 0, 0)
        mic_test = QPushButton('Проверить (1 с)')
        mic_test.clicked.connect(self._test_microphone)
        self.test_mic = QLabel('')
        mic_line.addWidget(mic_test)
        mic_line.addWidget(self.test_mic)
        form.addRow("Проверка микрофона", mic_row)
        outer.addWidget(voice_group)
        speech_group = QGroupBox("Голосовые ответы")
        row = QHBoxLayout(speech_group)
        self.tts = QCheckBox("Включить")
        self.tts.setChecked(config['tts_enabled'])
        row.addWidget(self.tts)
        test_speech = QPushButton("Проверить")
        test_speech.clicked.connect(lambda: speaker.say("Проверка голосового ответа"))
        row.addWidget(test_speech)
        outer.addWidget(speech_group)
        system = QGroupBox("Затемнение и система")
        form = QFormLayout(system)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(.1, 10.)
        self.duration.setSingleStep(.1)
        self.duration.setSuffix(" с")
        self.duration.setValue(config['duration'])
        form.addRow("Длительность перехода", self.duration)
        self.remember = QCheckBox("Сохранять последнюю яркость")
        self.remember.setChecked(config['remember_brightness'])
        form.addRow(self.remember)
        self.autostart = QCheckBox("Запускать вместе с Windows")
        self.autostart.setChecked(config['autostart'])
        form.addRow(self.autostart)
        self.tray_start = QCheckBox("Запускать в трее")
        self.tray_start.setChecked(config['start_in_tray'])
        form.addRow(self.tray_start)
        outer.addWidget(system)
        buttons = QHBoxLayout()
        save = QPushButton("Сохранить")
        save.clicked.connect(self._save)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        outer.addLayout(buttons)

    def _test_monitor(self, key):
        previous = self.manager.values[key]
        self.manager.set_value(key, 30, .25)
        QTimer.singleShot(1800, lambda: self.manager.set_value(key, previous, .4) if key in self.manager.layers else None)

    def _test_microphone(self):
        try:
            import sounddevice as sd
            audio = sd.rec(16000, samplerate=16000, channels=1, dtype='float32',
                           device=self.microphone.currentData())
            sd.wait()
            self.test_mic.setText('Сигнал есть' if float(abs(audio).max()) > .005 else 'Тихо: проверьте микрофон')
        except Exception as exc:
            self.test_mic.setText(f'Ошибка: {exc}')

    def _save(self):
        choices = [box.currentText() for box in self.assignments.values()]
        if len(choices) != len(set(choices)):
            self.test_mic.setText("Названия мониторов должны различаться")
            return
        self.config['monitors'] = {key: box.currentText() for key, box in self.assignments.items()}
        self.config['voice_enabled'] = self.enabled.isChecked()
        self.config['microphone'] = self.microphone.currentData()
        self.config['tts_enabled'] = self.tts.isChecked()
        self.config['duration'] = self.duration.value()
        self.config['remember_brightness'] = self.remember.isChecked()
        self.config['autostart'] = self.autostart.isChecked()
        self.config['start_in_tray'] = self.tray_start.isChecked()
        self.save_callback()
        self.accept()
