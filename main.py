import sys
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from brightness_control.config import load, save
from brightness_control.overlay import MonitorManager
from brightness_control.parser import parse, split_wake, describe, spoken
from brightness_control.startup import set_autostart
from brightness_control.ui import Notice, Settings, TrayPanel
from brightness_control.voice import Voice, Speaker


def icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor('#24252b'))
    painter = QPainter(pixmap)
    painter.setBrush(QColor('#f2c84b'))
    painter.setPen(QColor('#f2c84b'))
    painter.drawEllipse(17, 17, 30, 30)
    painter.end()
    return QIcon(pixmap)


class Controller(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.config = load()
        self.manager = MonitorManager(self.config)
        self.manager.changed.connect(self._refresh)
        self.voice = Voice()
        self.voice.recognized.connect(self._recognized)
        self.voice.error.connect(self._voice_error)
        self.speaker = Speaker(self.voice)
        self.state = 'wake'
        self.pending = None
        self.state_timer = QTimer(self)
        self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self._reset_state)
        self.notice = Notice()
        self.notice.decision.connect(self._decision)
        self.panel = TrayPanel()
        self.panel.voice_toggled.connect(self._toggle_voice)
        self.panel.value_changed.connect(self._slider)
        self.panel.settings_requested.connect(self._settings)
        self.panel.quit_requested.connect(self.close)
        self.tray = QSystemTrayIcon(icon(), self.app)
        self.tray.setToolTip('Brightness Voice Control')
        menu = QMenu()
        show = QAction('Яркость и ползунки', menu)
        show.triggered.connect(self._show_panel)
        menu.addAction(show)
        settings = QAction('Настройки', menu)
        settings.triggered.connect(self._settings)
        menu.addAction(settings)
        menu.addSeparator()
        quit_action = QAction('Выход', menu)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._show_panel() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._refresh()
        if self.config['voice_enabled']:
            self.voice.start(self.config['microphone'])
        if not self.config['start_in_tray'] and '--tray' not in sys.argv:
            QTimer.singleShot(0, self._settings)

    def _refresh(self):
        if not hasattr(self, 'panel'):
            return
        self.panel.rebuild(self.manager.named())
        self.panel.voice_box.blockSignals(True)
        self.panel.voice_box.setChecked(self.config['voice_enabled'])
        self.panel.voice_box.blockSignals(False)
        if hasattr(self, 'tray'):
            self.tray.setToolTip('Brightness Voice Control\n' + ', '.join(
                f'{name}: {value}%' for name, value in self.manager.named().items()))
        self._save()

    def _save(self):
        if not self.config['remember_brightness']:
            self.config['brightness'] = {}
        try:
            save(self.config)
        except OSError as exc:
            if hasattr(self, 'tray'):
                self.tray.showMessage('Ошибка сохранения', str(exc))

    def _show_panel(self):
        self._refresh()
        self.panel.show_near_cursor()

    def _slider(self, name, value):
        self.manager.set_named(name, value)

    def _toggle_voice(self, enabled):
        self.config['voice_enabled'] = enabled
        self._save()
        self._reset_state()
        if enabled:
            self.voice.start(self.config['microphone'])
        else:
            self.voice.stop()

    def _settings(self):
        dialog = Settings(self.manager, self.config, self.voice, self.speaker, self._settings_saved)
        dialog.exec()

    def _settings_saved(self):
        try:
            set_autostart(self.config['autostart'])
        except OSError as exc:
            QMessageBox.warning(None, 'Автозапуск', str(exc))
        self._save()
        self._refresh()
        self.voice.stop()
        if self.config['voice_enabled']:
            self.voice.start(self.config['microphone'])

    def _say(self, text):
        if self.config['tts_enabled']:
            self.speaker.say(text)

    def _voice_error(self, message):
        self.config['voice_enabled'] = False
        self._refresh()
        self.notice.show_message(message, timeout=8000)

    def _reset_state(self):
        self.state_timer.stop()
        self.pending = None
        self.state = 'wake'
        self.notice.hide()

    def _recognized(self, phrase, confidence):
        if not self.config['voice_enabled']:
            return
        clean = phrase.strip().lower()
        if self.state == 'confirm':
            if clean in ('да', 'да подтверждаю', 'подтверждаю'):
                self._decision(True)
            elif clean in ('нет', 'нет отмена', 'отмена'):
                self._decision(False)
            return
        found, remainder = split_wake(clean)
        if self.state == 'wake':
            if not found:
                return
            self.state = 'command'
            self.state_timer.start(7000)
            if remainder:
                self._command(remainder, confidence)
            return
        if self.state == 'command':
            self._command(remainder if found else clean, confidence)

    def _command(self, phrase, confidence):
        self.state = 'processing'
        command = parse(phrase, confidence)
        if command is None:
            self.notice.show_message('Команда не распознана', timeout=3000)
            self._say('Не удалось распознать команду.')
            self.state_timer.start(3000)
            return
        values = self.manager.named()
        if command.target and command.target not in values:
            self.notice.show_message('Монитор не подключён')
            self._reset_state_later()
            return
        if command.uncertain:
            self.pending = command
            self.state = 'confirm'
            self.state_timer.start(9000)
            self.notice.show_message(describe(command, values) + '?', confirm=True)
            self._say(spoken(command, values, question=True))
            return
        self._execute(command)

    def _reset_state_later(self):
        self.state_timer.start(3500)

    def _decision(self, yes):
        if self.state != 'confirm' or self.pending is None:
            return
        command = self.pending
        self.pending = None
        if yes:
            self._execute(command)
        else:
            self._say('Отменено.')
            self._reset_state()

    def _execute(self, command):
        self.state = 'executing'
        values = self.manager.named()
        targets = [command.target] if command.target else list(values)
        text = describe(command, values)
        for name in targets:
            key = next((k for k, v in self.config['monitors'].items() if v == name and k in self.manager.values), None)
            if key is not None:
                value = command.value if command.mode == 'set' else values[name] + command.value
                self.manager.set_value(key, value)
        self._say(spoken(command, values))
        self.notice.show_message(text)
        self.state_timer.stop()
        self.pending = None
        self.state = 'wake'

    def close(self):
        self.voice.stop()
        self.speaker.close()
        self._save()
        self.tray.hide()
        self.app.quit()


def main():
    if sys.platform != 'win32':
        raise SystemExit('Программа предназначена для Windows 11.')
    if '--reset-brightness' in sys.argv:
        config = load()
        config['brightness'] = {}
        save(config)
        return 0
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, 'Brightness Voice Control', 'Системный трей недоступен.')
        return 1
    controller = Controller(app)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
