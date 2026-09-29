"""First-run guided setup. Existing v0.1 users skip this after migration."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout,
                              QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget)
from .parser import split_wake, parse


class Onboarding(QDialog):
    def __init__(self, controller):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.controller = controller
        self.config = controller.config
        self.manager = controller.manager
        self.setWindowTitle('Настройка Brightness Voice Control')
        self.resize(760, 560)
        self.stack = QStackedWidget()
        outer = QVBoxLayout(self)
        outer.addWidget(self.stack)
        self.assignments = {}
        self._welcome()
        self._monitors()
        self._microphone()
        self._voice_test()
        self._finish()
        footer = QHBoxLayout()
        self.back = QPushButton('Назад')
        self.back.clicked.connect(lambda: self._step(-1))
        self.next = QPushButton('Далее')
        self.next.setObjectName('primary')
        self.next.clicked.connect(lambda: self._step(1))
        footer.addWidget(self.back)
        footer.addStretch()
        footer.addWidget(self.next)
        outer.addLayout(footer)
        self.stack.currentChanged.connect(self._buttons)
        self._buttons(0)
        controller.voice.recognized.connect(self._heard)

    def _page(self, title, description):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        heading = QLabel(title)
        heading.setObjectName('title')
        layout.addWidget(heading)
        layout.addWidget(QLabel(description))
        layout.addSpacing(24)
        self.stack.addWidget(page)
        return layout

    def _welcome(self):
        layout = self._page('Настроим Brightness Voice Control',
                            'Это займёт пару минут. Затем приложение останется в системном трее.')
        layout.addWidget(QLabel('Экраны · Голос · Профили'))
        layout.addStretch()

    def _monitors(self):
        layout = self._page('Ваши мониторы', 'Назначьте каждому экрану понятное имя.')
        for key in self.manager.layers:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"Экран {self.manager.ordinals[key]}  ·  "
                                 f"{self.manager.screens[key].geometry().width()}×"
                                 f"{self.manager.screens[key].geometry().height()}"))
            combo = QComboBox()
            combo.addItems(('Левый', 'Центральный', 'Правый'))
            combo.setCurrentText(self.config['monitors'].get(key, 'Левый'))
            row.addWidget(combo)
            identify = QPushButton('Показать номер')
            identify.clicked.connect(lambda _, k=key: self._identify(k))
            row.addWidget(identify)
            test = QPushButton('Проверить затемнение')
            test.clicked.connect(lambda _, k=key: self._test_monitor(k))
            row.addWidget(test)
            layout.addLayout(row)
            self.assignments[key] = combo
        layout.addStretch()

    def _identify(self, key):
        from .settings_window import Settings
        Settings._identify(self, key)

    def _test_monitor(self, key):
        from .settings_window import Settings
        Settings._test_monitor(self, key)

    def _microphone(self):
        layout = self._page('Микрофон', 'Выберите устройство и проверьте его сигнал.')
        self.microphone = QComboBox()
        self.microphone.addItem('По умолчанию', None)
        try:
            for idx, name in self.controller.voice.devices():
                self.microphone.addItem(name, idx)
        except Exception:
            pass
        self.microphone.setCurrentIndex(max(0, self.microphone.findData(self.config['microphone'])))
        layout.addWidget(self.microphone)
        test = QPushButton('Проверить микрофон')
        self.mic_status = QLabel('Ожидание')
        test.clicked.connect(self._test_microphone)
        layout.addWidget(test)
        layout.addWidget(self.mic_status)
        layout.addStretch()

    def _test_microphone(self):
        from .settings_window import Settings
        Settings._test_microphone(self)

    def _voice_test(self):
        layout = self._page('Проверка голоса', 'Скажите: «Компьютер, яркость 50 процентов».')
        self.test_status = QLabel('Ожидаю ключевую фразу')
        layout.addWidget(self.test_status)
        say = QPushButton('Проверить голосовой ответ')
        say.clicked.connect(lambda: self.controller.speaker.say('Голосовой ответ работает.'))
        layout.addWidget(say)
        skip = QPushButton('Пропустить проверку')
        skip.clicked.connect(lambda: self._step(1))
        layout.addWidget(skip)
        layout.addStretch()

    def _heard(self, phrase, confidence):
        if self.stack.currentIndex() != 3:
            return
        wake, remainder = split_wake(phrase)
        if wake:
            self.test_status.setText('✓ Ключевая фраза услышана')
        if parse(remainder or phrase):
            self.test_status.setText('✓ Команда распознана')

    def _finish(self):
        layout = self._page('Всё готово', 'Приложение будет работать в системном трее.')
        self.autostart = QCheckBox('Запускать вместе с Windows')
        self.autostart.setChecked(self.config['autostart'])
        self.voice_enabled = QCheckBox('Автоматически включать голос')
        self.voice_enabled.setChecked(self.config['voice_enabled'])
        layout.addWidget(self.autostart)
        layout.addWidget(self.voice_enabled)
        layout.addStretch()

    def _buttons(self, index):
        self.back.setEnabled(index > 0)
        self.next.setText('Готово' if index == self.stack.count() - 1 else 'Далее')

    def _step(self, offset):
        current = self.stack.currentIndex()
        if current == 1 and offset > 0:
            names = [box.currentText() for box in self.assignments.values()]
            if len(names) != len(set(names)):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'Мониторы', 'Названия мониторов должны различаться.')
                return
            for key, combo in self.assignments.items():
                self.config['monitors'][key] = combo.currentText()
        if current == 2 and offset > 0:
            self.config['microphone'] = self.microphone.currentData()
            self.config['microphone_name'] = (self.microphone.currentText().split(': ', 1)[-1]
                                              if self.microphone.currentData() is not None else '')
            self.controller.restart_voice()
        if current == self.stack.count() - 1 and offset > 0:
            self.config['first_run_completed'] = True
            self.config['autostart'] = self.autostart.isChecked()
            self.config['voice_enabled'] = self.voice_enabled.isChecked()
            self.controller.settings_saved()
            self.accept()
            return
        self.stack.setCurrentIndex(max(0, min(self.stack.count() - 1, current + offset)))
