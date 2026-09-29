"""Structured settings with local controls for all version-1 features."""
import copy
import json
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QScrollArea, QSpinBox, QFileDialog,
    QStackedWidget, QVBoxLayout, QWidget)

from .editors import ProfileEditor, ScheduleEditor
from .voice import model_path
from .config import config_path, migrate


def heading(text):
    label = QLabel(text)
    label.setObjectName('title')
    return label


class Settings(QDialog):
    def __init__(self, manager, config, voice, speaker, controller):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.manager, self.config, self.voice, self.speaker = manager, config, voice, speaker
        self.controller = controller
        self.profiles = copy.deepcopy(config['profiles'])
        self.schedule = copy.deepcopy(config['schedule'])
        self.setWindowTitle('Настройки — Brightness Voice Control')
        self.resize(920, 680)
        self.setMinimumSize(820, 600)
        outer = QVBoxLayout(self)
        content = QHBoxLayout()
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(205)
        self.stack = QStackedWidget()
        names = ('Главная', 'Мониторы', 'Голос', 'Яркость', 'Профили',
                 'Расписание', 'Уведомления', 'Система', 'О программе')
        for name in names:
            self.sidebar.addItem(name)
        pages = (self._home, self._monitors, self._voice, self._brightness,
                 self._profiles, self._schedule, self._notifications, self._system,
                 self._about)
        for factory in pages:
            page = factory()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)
        content.addWidget(self.sidebar)
        content.addWidget(self.stack, 1)
        outer.addLayout(content)
        footer = QHBoxLayout()
        footer.addStretch()
        save = QPushButton('Сохранить')
        save.setObjectName('primary')
        save.clicked.connect(self._save)
        cancel = QPushButton('Отмена')
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        footer.addWidget(save)
        outer.addLayout(footer)

    def _page(self, title):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)
        layout.addWidget(heading(title))
        return widget, layout

    def _home(self):
        page, layout = self._page('Главная')
        layout.addWidget(QLabel(f"Голос: {'включён' if self.config['voice_enabled'] else 'выключен'}"))
        for name, value in self.manager.named().items():
            layout.addWidget(QLabel(f'{name}: {round(value)}%'))
        active = self.config.get('active_profile')
        profile = next((p['name'] for p in self.profiles if p['id'] == active), 'Ручной режим')
        layout.addWidget(QLabel('Профиль: ' + profile))
        layout.addStretch()
        return page

    def _monitors(self):
        page, layout = self._page('Мониторы')
        layout.addWidget(QLabel('Назначьте каждому обнаруженному экрану своё имя.'))
        self.assignments = {}
        self.aliases = {}
        for key, layer in self.manager.layers.items():
            info = self.config['monitor_info'].get(key, {})
            screen = self.manager.screens[key]
            frame = QFrame()
            frame.setObjectName('card')
            box = QVBoxLayout(frame)
            box.addWidget(QLabel(f"{info.get('friendly_name', 'Экран')} · "
                                 f"{screen.geometry().width()}×{screen.geometry().height()} · "
                                 f"Экран {self.manager.ordinals[key]}"))
            line = QHBoxLayout()
            combo = QComboBox()
            combo.addItems(('Левый', 'Центральный', 'Правый'))
            combo.setCurrentText(self.config['monitors'].get(key, 'Левый'))
            line.addWidget(combo)
            identify = QPushButton('Показать номер')
            identify.clicked.connect(lambda _, k=key: self._identify(k))
            line.addWidget(identify)
            test = QPushButton('Проверить')
            test.clicked.connect(lambda _, k=key: self._test_monitor(k))
            line.addWidget(test)
            box.addLayout(line)
            alias = QLineEdit(self.config['monitor_aliases'].get(key, ''))
            alias.setPlaceholderText('Дополнительное голосовое имя (необязательно)')
            box.addWidget(alias)
            layout.addWidget(frame)
            self.assignments[key] = combo
            self.aliases[key] = alias
        layout.addStretch()
        return page

    def _identify(self, key):
        if key not in self.manager.screens:
            return
        screen = self.manager.screens[key]
        label = QLabel(str(self.manager.ordinals[key]), None,
                       Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                       Qt.WindowType.FramelessWindowHint)
        label.setStyleSheet('background:#17191E; color:#F5F7FA; font-size:72px; padding:35px;')
        label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        label.setScreen(screen)
        label.adjustSize()
        label.move(screen.geometry().center() - label.rect().center())
        label.show()
        self._identity_label = label
        QTimer.singleShot(2000, label.close)

    def _test_monitor(self, key):
        previous = self.manager.states[key].target_brightness
        self.manager.set_value(key, 30, .3)
        QTimer.singleShot(1500, lambda: self.manager.set_value(key, previous, .4)
                          if key in self.manager.layers else None)

    def _voice(self):
        page, layout = self._page('Голос')
        form = QFormLayout()
        self.enabled = QCheckBox('Голосовое управление')
        self.enabled.setChecked(self.config['voice_enabled'])
        form.addRow(self.enabled)
        self.microphone = QComboBox()
        self.microphone.addItem('По умолчанию', None)
        try:
            for idx, name in self.voice.devices():
                self.microphone.addItem(name, idx)
        except Exception:
            pass
        self.microphone.setCurrentIndex(max(0, self.microphone.findData(self.config['microphone'])))
        form.addRow('Микрофон', self.microphone)
        check = QPushButton('Проверить микрофон')
        check.clicked.connect(self._test_microphone)
        self.mic_status = QLabel('Скажите несколько слов после нажатия')
        line = QHBoxLayout()
        line.addWidget(check)
        line.addWidget(self.mic_status)
        form.addRow('Уровень', line)
        self.beep = QCheckBox('Тихий сигнал после «Компьютер»')
        self.beep.setChecked(self.config['wake_beep'])
        form.addRow(self.beep)
        self.listening = QCheckBox('Показывать «Слушаю…»')
        self.listening.setChecked(self.config['show_listening'])
        form.addRow(self.listening)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 7)
        self.timeout.setSuffix(' с')
        self.timeout.setValue(self.config['command_timeout'])
        form.addRow('Ждать команду', self.timeout)
        self.responses = QComboBox()
        for label, value in (('Всегда', 'always'), ('Только важные', 'important'),
                             ('Только ошибки', 'errors'), ('Выключено', 'off')):
            self.responses.addItem(label, value)
        self.responses.setCurrentIndex(max(0, self.responses.findData(self.config['tts_response'])))
        form.addRow('Ответы', self.responses)
        self.tts_mode = QComboBox()
        self.tts_mode.addItem('Короткие', 'short')
        self.tts_mode.addItem('Полные', 'full')
        self.tts_mode.setCurrentIndex(max(0, self.tts_mode.findData(self.config['tts_mode'])))
        form.addRow('Формат', self.tts_mode)
        self.voice_name = QComboBox()
        self.voice_name.addItem('Системный русский голос', '')
        try:
            import pythoncom
            import pyttsx3
            pythoncom.CoInitialize()
            try:
                engine = pyttsx3.init('sapi5')
                for voice in engine.getProperty('voices'):
                    self.voice_name.addItem(voice.name, voice.id)
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            pass
        self.voice_name.setCurrentIndex(max(0, self.voice_name.findData(self.config['tts_voice'])))
        form.addRow('Голос', self.voice_name)
        self.volume = QSpinBox()
        self.volume.setRange(0, 100)
        self.volume.setSuffix('%')
        self.volume.setValue(self.config['tts_volume'])
        form.addRow('Громкость', self.volume)
        self.rate = QSpinBox()
        self.rate.setRange(-100, 100)
        self.rate.setValue(self.config['tts_rate'])
        form.addRow('Скорость', self.rate)
        example = QPushButton('Прослушать пример')
        example.clicked.connect(lambda: self.speaker.say('Левый монитор — десять процентов.',
            {'voice': self.voice_name.currentData(), 'volume': self.volume.value(),
             'rate': self.rate.value()}))
        form.addRow(example)
        layout.addLayout(form)
        layout.addStretch()
        return page

    def _test_microphone(self):
        try:
            import numpy  # sounddevice.rec() creates a NumPy array
            import sounddevice as sd
            audio = sd.rec(16000, samplerate=16000, channels=1, dtype='float32',
                           device=self.microphone.currentData())
            sd.wait()
            peak = float(abs(audio).max())
            self.mic_status.setText('Сигнал хороший' if peak > .02 else
                                    'Слишком тихо' if peak > .005 else 'Сигнал не обнаружен')
        except ImportError:
            self.mic_status.setText('Не установлен NumPy. Выполните: pip install -r requirements.txt')
        except Exception as exc:
            self.mic_status.setText('Устройство недоступно: ' + str(exc))

    def _brightness(self):
        page, layout = self._page('Яркость')
        form = QFormLayout()
        self.step = QSpinBox()
        self.step.setRange(1, 100)
        self.step.setSuffix('%')
        self.step.setValue(self.config['relative_step'])
        form.addRow('Шаг «ярче/темнее»', self.step)
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 100)
        self.minimum.setSuffix('%')
        self.minimum.setValue(self.config['minimum_brightness'])
        form.addRow('Минимальная яркость', self.minimum)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0, 5)
        self.duration.setSingleStep(.1)
        self.duration.setSuffix(' с')
        self.duration.setValue(self.config['duration'])
        form.addRow('Плавный переход', self.duration)
        self.remember = QCheckBox('Запоминать последнюю яркость')
        self.remember.setChecked(self.config['remember_brightness'])
        form.addRow(self.remember)
        layout.addLayout(form)
        layout.addStretch()
        return page

    def _profiles(self):
        page, layout = self._page('Профили')
        self.profile_list = QListWidget()
        self._refresh_profiles()
        layout.addWidget(self.profile_list)
        row = QHBoxLayout()
        for title, callback in (('Добавить', self._add_profile), ('Изменить', self._edit_profile),
                                ('Удалить', self._delete_profile), ('Применить', self._apply_profile)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        return page

    def _refresh_profiles(self):
        self.profile_list.clear()
        for profile in self.profiles:
            self.profile_list.addItem(profile['name'])

    def _selected_profile(self):
        index = self.profile_list.currentRow()
        return index if 0 <= index < len(self.profiles) else None

    def _add_profile(self):
        dialog = ProfileEditor(parent=self)
        if dialog.exec():
            self.profiles.append(dialog.result_profile())
            self._refresh_profiles()

    def _edit_profile(self):
        index = self._selected_profile()
        if index is None:
            return
        dialog = ProfileEditor(self.profiles[index], self)
        if dialog.exec():
            self.profiles[index] = dialog.result_profile()
            self._refresh_profiles()

    def _delete_profile(self):
        index = self._selected_profile()
        if index is not None:
            self.profiles.pop(index)
            self._refresh_profiles()

    def _apply_profile(self):
        index = self._selected_profile()
        if index is not None:
            saved = next((p for p in self.config['profiles']
                          if p['id'] == self.profiles[index]['id']), None)
            if saved is None or saved != self.profiles[index]:
                QMessageBox.information(self, 'Профиль', 'Сначала сохраните изменения профиля.')
                return
            self.controller.apply_profile(saved)

    def _schedule(self):
        page, layout = self._page('Расписание')
        self.rule_list = QListWidget()
        self._refresh_schedule()
        layout.addWidget(self.rule_list)
        row = QHBoxLayout()
        for title, callback in (('Добавить', self._add_rule), ('Изменить', self._edit_rule),
                                ('Удалить', self._delete_rule)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        return page

    def _refresh_schedule(self):
        self.rule_list.clear()
        for rule in self.schedule:
            name = next((p['name'] for p in self.profiles if p['id'] == rule.get('profile_id')), '?')
            days = ', '.join(('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')[i]
                             for i in rule.get('days', []) if 0 <= i < 7)
            self.rule_list.addItem(f"{rule.get('time', '--:--')}   {days}   {name}   "
                                   f"{'ON' if rule.get('enabled', True) else 'OFF'}")

    def _add_rule(self):
        dialog = ScheduleEditor(self.profiles, parent=self)
        if dialog.exec():
            self.schedule.append(dialog.result_rule())
            self._refresh_schedule()

    def _edit_rule(self):
        index = self.rule_list.currentRow()
        if index < 0:
            return
        dialog = ScheduleEditor(self.profiles, self.schedule[index], self)
        if dialog.exec():
            self.schedule[index] = dialog.result_rule()
            self._refresh_schedule()

    def _delete_rule(self):
        index = self.rule_list.currentRow()
        if index >= 0:
            self.schedule.pop(index)
            self._refresh_schedule()

    def _notifications(self):
        page, layout = self._page('Уведомления')
        self.notify_boxes = {}
        for key, text in (('success', 'Успешные команды'), ('errors', 'Ошибки'),
                          ('confirmation', 'Уточнения'), ('listening', 'Слушаю…')):
            checkbox = QCheckBox(text)
            checkbox.setChecked(self.config['notifications'][key])
            layout.addWidget(checkbox)
            self.notify_boxes[key] = checkbox
        form = QFormLayout()
        self.notify_duration = QDoubleSpinBox()
        self.notify_duration.setRange(1, 10)
        self.notify_duration.setSingleStep(.5)
        self.notify_duration.setSuffix(' с')
        self.notify_duration.setValue(self.config['notifications']['duration'])
        form.addRow('Время показа', self.notify_duration)
        self.placement = QComboBox()
        for text, value in (('Основной монитор', 'primary'),
                            ('Монитор с курсором', 'cursor')):
            self.placement.addItem(text, value)
        self.placement.setCurrentIndex(max(0, self.placement.findData(
            self.config['notifications']['placement'])))
        form.addRow('Показывать на', self.placement)
        layout.addLayout(form)
        layout.addStretch()
        return page

    def _system(self):
        page, layout = self._page('Система')
        self.autostart = QCheckBox('Запускать вместе с Windows')
        self.autostart.setChecked(self.config['autostart'])
        layout.addWidget(self.autostart)
        self.tray_start = QCheckBox('Запускать свёрнутым в трей')
        self.tray_start.setChecked(self.config['start_in_tray'])
        layout.addWidget(self.tray_start)
        form = QFormLayout()
        self.theme = QComboBox()
        for text, value in (('Как в Windows', 'system'), ('Тёмная', 'dark'),
                            ('Светлая', 'light')):
            self.theme.addItem(text, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(
            self.config['appearance']['theme'])))
        form.addRow('Тема', self.theme)
        layout.addLayout(form)
        row = QHBoxLayout()
        export = QPushButton('Экспорт настроек')
        export.clicked.connect(self._export)
        import_button = QPushButton('Импорт настроек')
        import_button.clicked.connect(self._import)
        row.addWidget(export)
        row.addWidget(import_button)
        layout.addLayout(row)
        layout.addStretch()
        return page

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Экспорт настроек', 'BrightnessVoiceControl.json',
                                               'JSON (*.json)')
        if path:
            try:
                data = migrate({**self.config, 'profiles': self.profiles, 'schedule': self.schedule})
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            except OSError as exc:
                QMessageBox.warning(self, 'Экспорт', str(exc))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Импорт настроек', '', 'JSON (*.json)')
        if not path:
            return
        try:
            raw = json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(raw, dict):
                raise ValueError('Ожидался JSON-объект')
            imported = migrate(raw)
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Импорт', str(exc))
            return
        self.controller.apply_import(imported)
        self.accept()

    def _about(self):
        page, layout = self._page('О программе')
        details = self._diagnostics()
        label = QLabel(details)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        buttons = QHBoxLayout()
        copy = QPushButton('Скопировать диагностику')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self._diagnostics()))
        buttons.addWidget(copy)
        folder = QPushButton('Открыть папку логов')
        folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(config_path().parent / 'logs'))))
        buttons.addWidget(folder)
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def _diagnostics(self):
        return ('Brightness Voice Control 1.0\n'
                f"Схема config: {self.config['schema_version']}\n"
                f"Движок: Vosk, модель: {model_path()}\n"
                f"Микрофон: {self.config['microphone'] or 'по умолчанию'}\n"
                f"Мониторов: {len(self.manager.layers)}\n"
                f"Overlay: {len(self.manager.layers)} активных слоёв\n"
                f"Настройки: {config_path()}")

    def _save(self):
        choices = [box.currentText() for box in self.assignments.values()]
        if len(choices) != len(set(choices)):
            QMessageBox.warning(self, 'Мониторы', 'Названия подключённых мониторов должны различаться.')
            self.sidebar.setCurrentRow(1)
            return
        for key, box in self.assignments.items():
            self.config['monitors'][key] = box.currentText()
            self.config['monitor_aliases'][key] = self.aliases[key].text().strip()
        self.config['voice_enabled'] = self.enabled.isChecked()
        self.config['microphone'] = self.microphone.currentData()
        self.config['microphone_name'] = (self.microphone.currentText().split(': ', 1)[-1]
                                          if self.microphone.currentData() is not None else '')
        self.config['wake_beep'] = self.beep.isChecked()
        self.config['show_listening'] = self.listening.isChecked()
        self.config['command_timeout'] = self.timeout.value()
        self.config['tts_response'] = self.responses.currentData()
        self.config['tts_enabled'] = self.config['tts_response'] != 'off'
        self.config['tts_mode'] = self.tts_mode.currentData()
        self.config['tts_voice'] = self.voice_name.currentData()
        self.config['tts_volume'] = self.volume.value()
        self.config['tts_rate'] = self.rate.value()
        self.config['relative_step'] = self.step.value()
        self.config['minimum_brightness'] = self.minimum.value()
        self.config['duration'] = self.duration.value()
        self.config['remember_brightness'] = self.remember.isChecked()
        self.config['profiles'] = self.profiles
        self.config['schedule'] = self.schedule
        for key, checkbox in self.notify_boxes.items():
            self.config['notifications'][key] = checkbox.isChecked()
        self.config['notifications']['duration'] = self.notify_duration.value()
        self.config['notifications']['placement'] = self.placement.currentData()
        self.config['autostart'] = self.autostart.isChecked()
        self.config['start_in_tray'] = self.tray_start.isChecked()
        self.config['appearance']['theme'] = self.theme.currentData()
        self.controller.settings_saved()
        self.accept()
